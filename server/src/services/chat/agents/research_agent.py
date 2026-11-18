import inspect, uuid
from typing import List, Dict
from pydantic import BaseModel

from llama_index.core.llms import ChatMessage
from llama_index.core.workflow import (
    Context,
    Event,
    StartEvent,
    StopEvent,
    step,
)

from src.services.chat.schema import Source
from src.services.chat.agents.base_agent import BaseAgentWorkflow, AgentStream, PlanTools


class Review(BaseModel):
    assessment: str
    sources_to_delete: List[int]


class InputEvent(Event):
    chat_history: List[ChatMessage]

class ExecuteEvent(Event):
    curr_plan: PlanTools
    chat_history: List[ChatMessage]

class ReviewEvent(Event):
    chat_history: List[ChatMessage]

class OutputEvent(Event):
    response: str

class CustomStopEvent(StopEvent):
    response: str
    new_sources: List[Source]
    input_tokens: int
    output_tokens: int


class ResearchAgent(BaseAgentWorkflow):
    name = "ResearchAgent"
    description = "Useful to retrieve new sources from the knowledge base (documents) and/or the web." \
                  "It's required to expand your context. " \
                  "Cannot inspect provided sources. " 

    @step
    async def agent_start(self, ctx: Context, ev: StartEvent) -> InputEvent:
        chat_history = [ChatMessage(role="user", content=ev.input_text)] 
        retrieved_sources: List[Source] = ev.state["retrieved_sources"]
        recorded_notes: Dict[str, str] = ev.state["recorded_notes"]
        web_search: bool = ev.state["web_search"]
        doc_search: bool = ev.state["doc_search"]
        tools = []
        
        self._retriever.add_excluded_ids([s.id for s in retrieved_sources if s.type == "docs"])
        
        if web_search:
            tools.append(self.search_web)
        if doc_search:
            tools.append(self.search_docs)
        tools = await self.add_mcp_tools(self.get_tools(tools))
        if not tools: 
            raise RuntimeError("No tools available")
        
        state = {"new_sources": [],
                 "retrieved_sources": retrieved_sources}
        await ctx.store.set("recorded_notes", recorded_notes)
        await ctx.store.set("instruction", "")
        await ctx.store.set("state", state)
        await ctx.store.set("tools", tools)
        await ctx.store.set("steps_taken", 0)
        await ctx.store.set("max_steps", 0)
        self.logger.info(f"{self.name} with {len(state['retrieved_sources'])} existing sources.")
        return InputEvent(chat_history=chat_history)
    
    
    @step
    async def agent_input(self, ctx: Context, ev: InputEvent) -> ExecuteEvent | OutputEvent:
        chat_history = ev.chat_history
        tools = await ctx.store.get("tools")
        instruction = await ctx.store.get("instruction")
        recorded_notes = await ctx.store.get("recorded_notes")

        try:
            _prompt = self.prompt_manager.get_prompt(prompt_name="PLANNER_TOOLS", 
                                                     tools_str=self.format_tools_to_str(tools),
                                                     instruction=instruction,
                                                     recorded_notes_str=self.format_recorded_notes_to_str(recorded_notes))
            response = await self._chat(prompt=_prompt, 
                                        messages=chat_history,
                                        output_model=PlanTools,
                                        streaming=False)
            chat_history.append(ChatMessage(role="assistant", content=str(response)))

            self.logger.debug(f"{self.name} chat_history:")
            for i,m in enumerate(chat_history):
                self.logger.debug(f"[{i}]:\t{m}")

            return ExecuteEvent(curr_plan=response, chat_history=chat_history)

        except Exception as e:
            error_str = f"Error encounted during task completion: {e}"
            self.logger.error(error_str)
            assessment = chat_history[-1].content
            return OutputEvent(response=assessment if isinstance(ev, ReviewEvent) else error_str) # error response is the last assessment


    @step
    async def agent_execute(self, ctx: Context, ev: ExecuteEvent) -> ReviewEvent:
        chat_history = ev.chat_history
        curr_plan = ev.curr_plan
        tools = await ctx.store.get("tools", default=[])

        for step in curr_plan.steps:
            tool_name = step.tool_name.lower()
            tool_input = step.tool_input or {}
            tool_call_id = str(uuid.uuid4())[:4]

            selected_tool = tools.get(tool_name.lower())
            if selected_tool:
                chat_history.append(ChatMessage(role="assistant",
                                                content=None,
                                                additional_kwargs={"tool_calls": [{"id": tool_call_id,
                                                                                   "type": "function",
                                                                                   "function": {"name": tool_name,
                                                                                                "arguments": str(tool_input)}}]}))
            else:
                error_str = f"Unrecognized tool_name: '{tool_name}'"
                self.logger.warning(error_str)
                chat_history.append(ChatMessage(role="assistant", content=error_str))
                continue

            streaming_msg = f"Tool: {tool_name} - Input: {tool_input}\n"
            ctx.write_event_to_stream(AgentStream(step=streaming_msg))
            try:
                async with ctx.store.edit_state() as ctx_state:
                    result = selected_tool["fn"](state=ctx_state["state"], **tool_input)
                    response = await result if inspect.isawaitable(result) else result
            except Exception as e:
                response = f"Error running tool '{tool_name}': {str(e)}"
                self.logger.warning(response)
                
            chat_history.append(ChatMessage(role="tool", 
                                            content=response,
                                            additional_kwargs={"name": tool_name, "tool_call_id": tool_call_id}))
        return ReviewEvent(chat_history=chat_history)


    @step
    async def agent_review(self, ctx: Context, ev: ReviewEvent) -> InputEvent | OutputEvent:
        chat_history = ev.chat_history
        new_sources = (await ctx.store.get("state"))["new_sources"]
        if not new_sources:
            response = "No relevant sources found."
            ctx.write_event_to_stream(AgentStream(msg=response))
            return OutputEvent(response=response)

        sources_with_ids = self.add_id_to_sources(lst_sources=new_sources, chat_history=chat_history)
        sources_str = self.format_sources_to_str(sources_with_ids=sources_with_ids)
        sources_msg = ChatMessage(role="assistant", content=f"Here are the gathered sources:\n[{sources_str}]")

        _prompt = self.prompt_manager.get_prompt(prompt_name="REVIEW_SOURCES")
        response_stream = await self._chat(prompt=_prompt,
                                           messages=chat_history + [sources_msg], 
                                           streaming=True)
        answer = ""
        ctx.write_event_to_stream(AgentStream(msg=f"Review sources: "))
        async for response_completion in response_stream:
            answer = response_completion
            if isinstance(response_completion, str):
                ctx.write_event_to_stream(AgentStream(msg=response_completion))
        ctx.write_event_to_stream(AgentStream(msg="\n"))
        ctx.write_event_to_stream(AgentStream(step=f"Review sources: {str(answer)}\n"))

        return OutputEvent(response=str(answer))


    @step
    async def agent_response(self, ctx: Context, ev: OutputEvent) -> CustomStopEvent:
        new_sources = (await ctx.store.get("state"))["new_sources"] 
        self.logger.success(f"Sending back {len(new_sources)} sources.")
        return CustomStopEvent(response=ev.response,
                               new_sources=new_sources,
                               input_tokens=self.input_tokens,
                               output_tokens=self.output_tokens)