import os
import shutil
import hashlib
import inspect
import tempfile
import subprocess
from ddgs import DDGS
from pathlib import Path
from pydantic import BaseModel, Field
from llama_index.core.workflow import Context, Event
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.workflow.handler import WorkflowHandler
from typing import List, Dict, Optional, Callable, Any, Annotated, get_type_hints, get_args

from src.services.chat.schema import Source
from src.services.chat.mcp_tools import MCPToolClient
from src.common.privacy.pii_redactor import get_default_redactor, redact_nested
from src.services.chat.workflows.base import BaseWorkflow, StreamingEvent


class AgentStream(Event):
    msg: str = Field(default=None, description="Directly streamed to the user.")
    step: str = Field(default=None, description="Tries to load the corresponding step_id str, if found streams that.")


class StepTool(BaseModel):
    tool_name: str = Field(description="Name of the tool to be invoked.")
    tool_input: Dict[str, Any] = Field(default_factory=dict, description="Arguments for the tool.")

class PlanTools(BaseModel):
    steps: List[StepTool]

class StepAgent(BaseModel):
    agent_name: str = Field(description="Name of the agent (e.g. AnswerAgent).")
    agent_task: str = Field(description="Detailed instructions for the agent.")

class PlanAgents(BaseModel):
    steps: List[StepAgent]


class BaseAgentWorkflow(BaseWorkflow):
    def __init__(self,
                 available_agents: List[str] = None,
                 available_tools: List[str] = None,
                 mcp_tool_client: Optional[MCPToolClient] = None,
                 **kwargs) \
                 -> None:
        super().__init__(**kwargs)
        self.logger.set_class_name(self.__class__.__name__)
        self.current_agents: Dict[str, FunctionAgent] = dict()
        self._initialized_agents = False
        self.curr_stream = ""
        self.available_agents = available_agents
        self.mcp_tool_client = mcp_tool_client or MCPToolClient()
        if self.available_agents:
            self.set_current_agents(self.available_agents) 


    # --- Tools -------------------------------------------------------------------------------------------------------
    def get_json_type(self, python_type: Any) -> str:
        """Maps Python types to JSON Schema types."""
        type_map = {
            str: "string",
            int: "number",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object"
        }
        return type_map.get(python_type, "string")


    def tool_parser(self, func):
        """Converts any Python function into an LLM-readable JSON schema."""
        # 1. Get Metadata
        type_hints = get_type_hints(func, include_extras=True)
        signature = inspect.signature(func)
        docstring = inspect.getdoc(func) or "No description provided."
        
        properties = {}
        required_params = []

        # 2. Iterate through parameters
        for param_name, param in signature.parameters.items():
            # Skip internal context/orchestration arguments
            if param_name in ['self', 'cls', 'state', 'context']:
                continue
                
            hint = type_hints.get(param_name)
            param_info = {}
            
            # Handle Annotated types: Annotated[type, "description"]
            if hasattr(hint, "__metadata__"):
                origin_type = get_args(hint)[0]
                param_info["type"] = self.get_json_type(origin_type)
                param_info["description"] = hint.__metadata__[0]
            else:
                param_info["type"] = self.get_json_type(hint)
                param_info["description"] = f"The {param_name} parameter."

            # Handle Default Values / Optionality
            if param.default is inspect.Parameter.empty:
                required_params.append(param_name)
            else:
                param_info["default"] = param.default

            properties[param_name] = param_info
        return {
            "name": func.__name__,
            "description": docstring,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required_params
            }
        }

    def get_tools(self, tool_list: List[Callable]) -> Dict[str, Dict[str, Any]]:
        return {t.__name__: {"schema": self.tool_parser(t), "fn": t} for t in tool_list}

    async def add_mcp_tools(
        self,
        tools: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        for tool in await self.mcp_tool_client.list_allowed_tools():
            if tool.qualified_name in tools:
                raise ValueError(f"Duplicate MCP tool name: {tool.qualified_name}")

            async def invoke_mcp_tool(
                state: Dict,
                _server_name=tool.server_name,
                _tool_name=tool.name,
                **arguments,
            ):
                safe_arguments = redact_nested(arguments, get_default_redactor())
                result = await self.mcp_tool_client.call_tool(
                    _server_name,
                    _tool_name,
                    safe_arguments,
                )
                return get_default_redactor().redact(result)

            invoke_mcp_tool.__name__ = tool.qualified_name
            tools[tool.qualified_name] = {
                "schema": {
                    "name": tool.qualified_name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                },
                "fn": invoke_mcp_tool,
            }
        return tools

    # Research
    async def search_web(self,
                         state: Dict,
                         query: Annotated[str, "A web search query"], 
                         ) -> str:
        """Useful get web sources to answer questions. It has no access to any document."""
        try:
            sources = DDGS().text(query, max_results=3)
            if sources:
                normalized_sources = [Source(type="web",
                                             filename=s["title"],
                                             chunk_number=1,
                                             uri=s["href"],
                                             text=s["body"],
                                             id=hashlib.md5((s["href"] or s["body"]).encode()).hexdigest())  for s in sources]
                new_sources = [s for s in normalized_sources if s not in state["retrieved_sources"] and s not in state["new_sources"]]
                state["new_sources"].extend(new_sources)
                tool_response = f"New sources found: {len(new_sources)}"
            else:
                tool_response = "No new sources found."
            self.logger.success(tool_response)
        except Exception as e:
            tool_response = f"Error in tool search_web: {e}"
            self.logger.warning(tool_response)
        return tool_response


    async def search_docs(self,
                          state: Dict,
                          query: Annotated[str, "A RAG query based on cosine similarity search"],
                          ) -> str:
        """Useful get document sources from the database to answer questions. It has no access to the web."""
        try:
            nodes = await self._get_nodes(query=query,
                                          max_nodes=5)
            if nodes:
                normalized_sources = self.normalize_nodes_to_sources(nodes=nodes)
                new_sources = [s for s in normalized_sources if s not in state["retrieved_sources"] and s not in state["new_sources"]]
                state["new_sources"].extend(new_sources)
                self._retriever.add_excluded_ids([s.id for s in new_sources])  # Exclude found sources for next iterations
                tool_response = f"New sources found: {len(new_sources)}"
            else:
                tool_response = "No new sources found."
            self.logger.success(tool_response)
        except Exception as e:
            tool_response = f"Error in tool search_docs: {e}"
            self.logger.error(tool_response, exc_info=True)
        return tool_response


    async def read_document(self, 
                            state: Dict,
                            filename: Annotated[str, "The complete name, with extension, of the document you want to read (e.g. 'report.txt')"], 
                            ) -> str:
        """Useful to read the content of a file."""
        filepath = self.chat_folder / filename
        if not os.path.exists(filepath):
            return f"I cannot find '{filepath}'. Here are all the accessible files: {os.listdir(self.chat_folder)}"
        try:
            if filename.endswith(".jpeg") or filename.endswith(".png"):
                return f"Here's the content of '{filename}': ```\nIt's an image of {filename.split('.')[0]}\n```"
            #document_content = self.doc_manager.read_file(filepath=filepath) # TODO Implement
            document_content = open(filepath, 'r').read()
            #if len(document_content) // 4 > 2000: # TODO I don't like this, think about something better
            #    document_content = document_content[:4*1000] + "\n[...]\n" + document_content[-4*1000:]
            #    add_info = "(truncated because over 2k tokens)"
            #else:
            #    add_info = ""
            return f"Here's the content of '{filename}': ```\n{document_content}\n```"
        except Exception as e:
            error_str = f"Error reading the file '{filename}': {e}"
            self.logger.error(error_str)
            return error_str


    async def write_document(self,
                             state: Dict,
                             content: Annotated[str, "Full text of the document to be written (NOT an instruction or request)."]
                             ) -> str:
        """
        Used to write the given text as the document content.

        The 'content' argument should be the actual text of the document, NOT an instruction or request.
        Example (correct): write_document(content="This is the full report on climate change...")
        Example (incorrect): write_document(content="Write a report on climate change.")
        """
        state["content"] = content
        return f"The document has been written, but not saved yet. Proceed to save it."            


    async def save_document(self,
                             state: Dict,
                             filename: Annotated[str, "A complete descriptive name with extension for the file (e.g. 'Market_Analysis_2024.md')"], 
                             #content: Annotated[str, "The full actual text content of the document."]
                             ) -> str:
        """ Useful last the previously written document. Enter only the filename. Saves the provided content into an accessible storage persistent over the chat. """

        content = state.get("content")
        if not content:
            return "A document needs to be written before being able to save it."

        prev_info = ""
        name, ext = os.path.splitext(filename)  

        os.makedirs(self.chat_folder, exist_ok=True)
        filepath = os.path.join(self.chat_folder, filename)
        available_extensions = [".md", ".txt", ".tex", ".json"]

        try:
            if not ext in available_extensions: # TODO Add more
                return f"'{ext}' is not a supported extension. Supported extensions: {available_extensions}.\n"

            is_overwriting_file = os.path.exists(filepath)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)

            if is_overwriting_file:
                prev_info += f"\nPrevious '{filename}' has been overwritten.\n"
                for i, s in enumerate(state["produced_content"][:]):  # iterate over a copy
                    if s.reference_index == filepath and s.type == "produced":
                        del state["produced_content"][i]

            state["produced_content"] = Source(type="produced",
                                               filename=filename,
                                               reference_index=filepath,
                                               text=content)
            return f"{prev_info}Document saved as '{filename}'."            
        except Exception as e:
            return f"Error saving file: {str(e)}"


    async def compile_pdf_from_tex(self, 
                                   state: Dict,
                                   filename: Annotated[str, "The complete name with extension of the .tex file to be compiled as pdf (e.g. 'report.tex')"], 
                                   ) -> str:
        """ Compiles the given .tex file twice using '-pdflatex' to create the final report in PDF. To include any other file write inside the .tex file, you can use './filename.ext' . """
        if not filename.endswith(".tex"):
            return f"A valid filename must end with '.tex'."

        self.chat_folder.mkdir(parents=True, exist_ok=True)
        tex_filepath = self.chat_folder / filename
        if not os.path.exists(tex_filepath):
            return f"I cannot find '{tex_filepath}'. Here are all the accessible files: {os.listdir(self.chat_folder)}"
        
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)
                subprocess.run(["pdflatex", "-interaction=nonstopmode", f"-output-directory={tmpdir_path}", tex_filepath.name], check=True, cwd=str(tex_filepath.parent))
                subprocess.run(["pdflatex", "-interaction=nonstopmode", f"-output-directory={tmpdir_path}", tex_filepath.name], check=True, cwd=str(tex_filepath.parent))
                pdf_path = tmpdir_path / (tex_filepath.stem + ".pdf")
                log_path = tmpdir_path / (tex_filepath.stem + ".log")
                if pdf_path.exists():
                    shutil.copy2(pdf_path, self.chat_folder)
                if log_path.exists():
                    shutil.copy2(log_path, self.chat_folder)
            return f"PDF compiled successfully! Here are all the current files: {os.listdir(self.chat_folder)}"
        except subprocess.CalledProcessError as e:
            return f"PDF compilation failed: {e}"
        

    # Recorded notes
    async def record_note(self, state: Dict, note_title: str, note_content: str) -> str:
        """Useful for recording notes on a given topic. Your input should be notes with a title to save the notes under. You can overwrite a note by entering the same title."""
        if "recorded_notes" not in state:
            state["recorded_notes"] = {}
        state["recorded_notes"][note_title] = note_content
        return f"Note '{note_title}' has been recorded."
    
    
    async def delete_note(self, state: Dict, note_title: str) -> str:
        """Useful for deleting previously recorded notes. Your input should be the title of a recorded note you want to delete."""
        if "recorded_notes" not in state:
            return "There are no recorded notes."
        
        if note_title not in state["recorded_notes"]:
            return f"There are no notes by the title '{note_title}'."
        
        del state["recorded_notes"][note_title]
        return f"Note '{note_title}' has been deleted."

    # Ticket
    def new_empty_ticket(self, state: Dict) -> str:
        """Get a new empty ticket."""
        state["content"] = state["ticket_model"]()
        required_fields = [field for field, value in state["content"].model_dump().items() if value is None]
        return f"A new empty ticket has been created. Please provide: {', '.join(required_fields)}"


    def update_ticket(self, state: Dict, **kwargs) -> str:
        """
        Update ticket properties. 
        Input should be key-value pairs of the fields to update.
        Example: {"category": "Hardware", "urgency": "High"}
        """
        ticket = state["content"]
        updates = []
        for key, value in kwargs.items():
            if hasattr(ticket, key):
                setattr(ticket, key, value)
                updates.append(f"{key} -> {value}")
            else:
                return f"Error: '{key}' is not a valid ticket field."
        return f"Ticket updated: {', '.join(updates)}"    


    def confirm_and_save_ticket(self, state: Dict) -> str:
        """Confirm and save ticket."""
        try:
            ticket = state["content"].model_dump()
        except:
            return "The current ticket is not valid, please start anew."
        
        empty_fields = [field for field, value in ticket.items() if value is None]
        if empty_fields:
            return f"Please compile the following fields: {', '.join(empty_fields)}"

        ticket_structure = state["ticket_structure"]
        t_category = ticket.get("category")
        t_subcategory = ticket.get("subcategory")
        t_type = ticket.get("type")
        if t_category not in ticket_structure.keys():
            return f"'{t_category}' is not a valid ticket category."
        elif t_subcategory not in ticket_structure[t_category]["subcategories"]:
            return f"'{t_subcategory}' is not a valid subcategory for {t_category}."
        elif t_type not in ticket_structure[t_category]["subcategories"][t_subcategory]["ticket_type"]:
            return f"'{t_type}' is not a valid ticket type."
        else:
            try:
                state["content"] = ticket.model_dump()
                save_response = self.save_document(state=state, filename="ticket.json") # Adds ticket to CHAT_STORAGE
                return ("Ticket has been confirmed."
                        f"{save_response}")
            except Exception as e:
                self.logger.error(f"Error saving the ticket: {e}")
                return "The ticket was confirmed, however there's been an error saving it."


    # --- Agents ------------------------------------------------------------------------------------------------------
    @staticmethod
    def _get_agent(agent_name: str, **kwargs) -> FunctionAgent:
        if agent_name == "AnswerAgent":
            from src.services.chat.agents.answer_agent import AnswerAgent
            return AnswerAgent(**kwargs)
        elif agent_name == "ResearchAgent":
            from src.services.chat.agents.research_agent import ResearchAgent
            return ResearchAgent(**kwargs)
        elif agent_name == "TicketAgent":
            from src.services.chat.agents.ticket_agent import TicketAgent
            return TicketAgent(**kwargs)
        elif agent_name == "ReportAgent":
            from src.services.chat.agents.report_agent import ReportAgent
            return ReportAgent(**kwargs)
        elif agent_name == "NotesAgent":
            from src.services.chat.agents.notes_agent import NotesAgent
            return NotesAgent(**kwargs)
        else:
            raise ValueError(f"Unknown agent: {agent_name}")


    async def stream_agent(self, ctx: Context, handler: WorkflowHandler):
        async for event in handler.stream_events():
            if isinstance(event, AgentStream):
                if event.step: # Tool calling streaming
                    self.curr_stream += event.step
                    ctx.write_event_to_stream(StreamingEvent(msg=self.curr_stream)) 
                elif event.msg: # Response streaming
                    ctx.write_event_to_stream(StreamingEvent(msg=self.curr_stream + "\n---\n" + event.msg))
        result = await handler
        return result


    async def _call_agent(self, agent_name: str, ctx: Context, input_text: str = None) -> Dict[str, Any]:
        """Generic agent calling function."""
        async with ctx.store.edit_state() as ctx_state:
            agent_instance = self.current_agents[agent_name]
            handler = agent_instance.run(state=ctx_state["state"], input_text=input_text)
            result = await self.stream_agent(ctx=ctx, handler=handler)

            # Update state based on agent's output
            if hasattr(result, "cited_sources"):
                ctx_state["state"]["cited_sources"] = result.cited_sources
            if hasattr(result, "new_sources"):
                current_sources = ctx_state["state"]["retrieved_sources"]
                ctx_state["state"]["retrieved_sources"] = current_sources + [source 
                                                                             for source in result.new_sources
                                                                             if source not in current_sources]
            if hasattr(result, "produced_content") and result.produced_content:
                ctx_state["state"]["produced_contents"].append(result.produced_content)
            if hasattr(result, "recorded_notes"):
                ctx_state["state"]["recorded_notes"] = result.recorded_notes

            return result


    async def call_agent_workflow(self, agent_name: str, ctx: Context, input_text: Optional[str] = None) -> str:
        if agent_name not in self.current_agents:
            self.logger.error(f"Agent has not been setup: {agent_name}\n")
            raise ValueError(f"Unknown agent name '{agent_name}'")

        try:
            agent_resp = await self._call_agent(agent_name=agent_name, ctx=ctx, input_text=input_text)
            self.input_tokens += agent_resp.input_tokens
            self.output_tokens += agent_resp.output_tokens
            return str(agent_resp.response)
        except Exception as e:
            error_str = f"Error running agent '{agent_name}': {e}"
            self.logger.error(error_str)
            return error_str



    def set_current_agents(self, agents_names: List[str]) -> None:
        """Sets the agents that are currently active for the workflow."""
        self.current_agents = {}
        for name in agents_names:
            try:
                agent_instance = self._get_agent(agent_name=name,
                                                 chat_id=self.chat_id,
                                                 llm=self._llm,
                                                 helper_llm=self.helper_llm,
                                                 retriever=self._retriever,
                                                 db_manager=self.db_manager,
                                                 provider=self._provider,
                                                 user=self.user)
                self.current_agents[name] = agent_instance
            except Exception as e:
                self.logger.error(f"Error setting up agent '{name}': {e}")
                raise e
        self.logger.success(f"Active agents have been set: {list(self.current_agents.keys())}")