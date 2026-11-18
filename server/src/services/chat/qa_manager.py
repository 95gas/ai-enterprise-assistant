from typing import AsyncGenerator, Dict, Optional, Union, Any, List
import uuid
from llama_index.core.postprocessor import SimilarityPostprocessor
from llama_index.llms.azure_openai import AzureOpenAI
from llama_index.llms.google_genai import GoogleGenAI
from llama_index.llms.openai import OpenAI
from llama_index.llms.ollama import Ollama

from src.services.chat.workflows.example_questions import ExampleQuestionsWorkflow
from src.services.chat.workflows.base import BaseWorkflow, StreamingEvent
from src.services.chat.agents.usersupport_agent import UserSupportAgent
from src.services.chat.workflows.focus import FocusModeWorkflow
from src.services.chat.schema import AgentProgress, Source, Metadata, Response
from src.common.connectors.neo4j.manager import Neo4jDBManager
from src.services.chat.agents.chat_agent import ChatAgent
from src.common.connectors.postgres.base import PostgresManager
from src.services.rag.retriever import CustomRetriever
from src.common.logging.logger import DebugLogger
from src.services.rag.graph_rag import GraphRAG
from config.settings import settings

STEP_STRING_DICT = settings.step_streaming


class QAManager:
    def __init__(self,
                 db_manager_neo4j: Neo4jDBManager,
                 db_manager: PostgresManager,
                 graph_rag: GraphRAG,
                 user: Optional[str] = None,
                 logger: Optional[DebugLogger] = None,
                 ):
        self.db_manager_neo4j = db_manager_neo4j
        self.db_manager = db_manager
        self.graph_rag = graph_rag
        self.user = user
        self.logger = logger or DebugLogger(user=self.user,
                                            class_name=self.__class__.__name__,
                                            main_feature="CHAT")
        self.logger.success("QAManager initialized")


    def get_retriever(self,
                      llm: Union[OpenAI, AzureOpenAI, Ollama, GoogleGenAI],
                      groups: Optional[list[str]] = None,
                      selected_documents: Optional[List[Dict[str, int]]] = None,
                      selected_chunk_numbers: Optional[list[int]] = None,
                      selected_page_numbers: Optional[list[int]] = None
                      ) -> CustomRetriever:
        """ Set up the retriever limiting its scope by groups and selected documents. """
        retriever = CustomRetriever(
            database_manager=self.db_manager_neo4j,
            graph_store=self.graph_rag.get_graph_store(),
            llm=llm,
            node_postprocessors=[SimilarityPostprocessor(similarity_cutoff=0.8)],
            user=self.user
        )
        retriever.set_groups(groups)
        if selected_documents:
            selected_documents = [file["filename"] for file in selected_documents]
            retriever.set_selected_documents(selected_documents)
        if selected_chunk_numbers:
            retriever.set_selected_chunk_numbers(selected_chunk_numbers)
        if selected_page_numbers:
            retriever.set_selected_page_numbers(selected_page_numbers)
        return retriever
    

    async def invoke(self,
                     llm: Union[OpenAI, AzureOpenAI, Ollama, GoogleGenAI],
                     helper_llm: Union[OpenAI, AzureOpenAI, Ollama, GoogleGenAI],
                     req_info: Dict[str, Any]
                     ) -> AsyncGenerator[str, Response]:
        """
        Makes the agent question the llm
        :param user_query: the query to send to the llm
        :param rag: whether to use RAG pipeline or not, for any workflow
        :param focus_mode: whether to use FocusModeWorkflow or not
        :param prev_answer: the previous answer to the question (whether to use ExpandWorkflow or not)
        :param llm: the llm to use
        :param provider: the provider offering the llm
        :param helper_llm: backup llm
        :param chat_history: the chat history
        :param groups: list of user's groups (groups)
        :param selected_documents: the selected documents within which to search
        :param generate_chat_name: if a chat name should be generated.
        :return: the response to the query by the agent
        """
        try:
            retriever = self.get_retriever(llm=llm,
                                           groups=req_info.get("user_roles", []),
                                           selected_documents=req_info.get("selected_documents", []),
                                           selected_page_numbers=req_info.get("selected_page_numbers", []),
                                           selected_chunk_numbers=req_info.get("selected_chunk_numbers", []))

            workflow_name = req_info["workflow"]
            self.logger.info("Selecting the workflow...")
            if workflow_name == "ExampleQuestions":
                retriever.set_random_mode(True)
            elif workflow_name == "FocusMode":
                retriever.set_focus_mode(True)
            workflow_options = {
                "chat_id": req_info["chat_id"],
                "llm": llm,
                "helper_llm": helper_llm,
                "retriever": retriever,
                "db_manager": self.db_manager,
                "provider": req_info["provider"],
                "user": self.user,
            }
            workflow_types = {
                "ExampleQuestions": (ExampleQuestionsWorkflow, workflow_options),
                "FocusMode": (FocusModeWorkflow, workflow_options),
                "UserSupport": (
                    UserSupportAgent,
                    {
                        **workflow_options,
                        "available_agents": [
                            "AnswerAgent", "NotesAgent", "ResearchAgent", "TicketAgent"
                        ],
                    },
                ),
                "QA": (
                    ChatAgent,
                    {
                        **workflow_options,
                        "available_agents": [
                            "AnswerAgent", "NotesAgent", "ResearchAgent"
                        ],
                    },
                ),
                "General": (
                    ChatAgent,
                    {
                        **workflow_options,
                        "available_agents": [
                            "AnswerAgent", "NotesAgent", "ResearchAgent"
                        ],
                    },
                ),
                "Report": (
                    ChatAgent,
                    {
                        **workflow_options,
                        "available_agents": [
                            "AnswerAgent", "NotesAgent", "ReportAgent"
                        ],
                    },
                ),
                "AllForOne": (
                    ChatAgent,
                    {
                        **workflow_options,
                        "available_agents": [
                            "AnswerAgent", "NotesAgent", "ReportAgent"
                        ],
                    },
                ),
                "DeepResearch": (
                    ChatAgent,
                    {
                        **workflow_options,
                        "available_agents": [
                            "AnswerAgent", "NotesAgent", "ResearchAgent", "ReportAgent"
                        ],
                    },
                ),
            }
            workflow_definition = workflow_types.get(workflow_name)
            if workflow_definition is None:
                self.logger.error(f"Unknown workflow type: {req_info['workflow']}")
                raise NotImplementedError(f"Unknown workflow type: {workflow_name}")
            workflow_type, options = workflow_definition
            w = workflow_type(**options)

            async for result in self.run_workflow(workflow=w,
                                                  req_info=req_info,
                                                  ):
                yield result
        except Exception as e:
            raise e
        
        
    async def run_workflow(self,
                           workflow: BaseWorkflow,
                           req_info: Dict) \
                           -> AsyncGenerator:

        self.logger.info(f"Running workflow {req_info['workflow']}...")

        handler = workflow.run(chat_history=req_info.get("chat_history"),
                               doc_search=req_info.get("doc_search"),
                               web_search=req_info.get("web_search"), # TODO Passed by FE
                               internal_knowledge=req_info.get("internal_knowledge"), # TODO Passed by FE
                               prev_answer=req_info.get("prev_answer"),
                               generate_chat_name=req_info.get("generate_chat_name"),
                               selected_language=req_info.get("selected_language"),
                               recorded_notes=req_info.get("recorded_notes"),
                               provided_sources=await self.process_provided_sources(chat_id=req_info["chat_id"]), # req_info.get("provided_sources")),
                               report_type=req_info.get("report_type", "free"), # TODO Change default to "free"
                               )
        async for ev in handler.stream_events():
            if isinstance(ev, StreamingEvent):
                language = req_info.get("selected_language", "en")
                if ev.progress_id and ev.progress_phase and ev.progress_agent:
                    yield AgentProgress(
                        id=ev.progress_id,
                        phase=ev.progress_phase,
                        tool_name="agent_step",
                        label="Agent",
                        message=f"{ev.progress_agent}: {ev.progress_phase}",
                        language=language,
                        duration_ms=ev.duration_ms,
                    )
                if ev.step_id:
                    step_messages = STEP_STRING_DICT.get(str(ev.step_id), {})
                    message = step_messages.get(language)
                    if message:
                        yield AgentProgress(
                            id=str(uuid.uuid4()),
                            phase="complete",
                            tool_name="reasoning",
                            label="Progress",
                            message=message,
                            language=language,
                        )
                    else:
                        self.logger.warning(f"Missing step string with step_id: {ev.step_id}")

        response = await handler
        self.logger.success(f"Workflow {req_info['workflow']} has finished.")
        #self.logger.debug(f"Workflow answer:\n{str(response)}")

        if hasattr(response, 'response'):
            yield Response(response=response.response,
                           sources=response.sources,
                           recorded_notes=response.recorded_notes,
                           metadata=Metadata(input_tokens=response.input_tokens,
                                             output_tokens=response.output_tokens,
                                             llm_model=response.llm_model,
                                             chat_name=response.chat_name))
        else:
            yield response.output




    # TODO Move away everything below
    async def process_provided_sources(self, chat_id: str) -> List[Source]:
        """
        Process all files provided for a given chat session.
        """
        import asyncio
        from pathlib import Path

        self.chat_id = chat_id
        root_dir = Path(r"C:/Users/ASK/Desktop/ASK_Repo/kami/experiments/input")
        chat_dir = settings.STORAGE_CHATS / self.chat_id

        # Gather all files recursively from both directories
        provided_sources = [f for f in root_dir.rglob('*') if f.is_file()]
        provided_sources += [f for f in chat_dir.rglob('*') if f.is_file()]

        if not provided_sources:
            return []

        # Process files concurrently
        tasks = [self.extract_data_from_source_path(s) for s in provided_sources]
        results = await asyncio.gather(*tasks)

        # Return only valid sources
        return [r for r in results if r]


    async def extract_data_from_source_path(self, source_path) -> Source:
        """
        Extract data from a given file path depending on its extension.
        If file already exists in the chat directory, reuse it instead of copying.
        """
        import os, fitz, shutil
        chat_dir = settings.STORAGE_CHATS / self.chat_id
        images_dir = chat_dir / "images"
        os.makedirs(images_dir, exist_ok=True)

        destination_path = chat_dir / source_path.name

        # If file already exists, do not copy again
        if destination_path.exists():
            self.logger.info(f"File already exists: {destination_path}, reusing it.")
            return Source(
                type="provided",
                filename=destination_path.name,
                reference_index=str(destination_path),
                text=f"Existing content for {destination_path.name}."
            )

        # Handle PNG files
        elif source_path.suffix.lower() == ".png" or source_path.suffix.lower() == ".jpeg":
            destination_path = chat_dir / images_dir / source_path.name
            if destination_path.exists():
                self.logger.info(f"File already exists: {destination_path}, reusing it.")
            else:
                shutil.copy2(source_path, destination_path)
                self.logger.success(f"Image copied: {destination_path}")
            return Source(
                type="provided",
                filename="images/" + destination_path.name,
                reference_index=str(destination_path),
                text=f"Image of {source_path.stem}."
            )

        # Handle PDF files
        elif source_path.suffix.lower() == ".pdf":
            try:
                doc = fitz.open(source_path)
                extracted_text = ""

                for page_number in range(doc.page_count):
                    page = doc.load_page(page_number)
                    page_dict = page.get_text("dict")
                    page_text = ""

                    for block in page_dict.get("blocks", []):
                        if block.get("type") == 1 and "image" in block:
                            image_bytes = block["image"]
                            img_index = block["number"]
                            image_ext = block["ext"]
                            image_filename = f"page_{page_number+1}_img_{img_index}.{image_ext}"
                            image_path = chat_dir / "images" / image_filename
                            with open(image_path, "wb") as f:
                                f.write(image_bytes)
                            page_text += f"<img src='images/{image_filename}'> "
                        elif "lines" in block:
                            for line in block["lines"]:
                                for span in line.get("spans", []):
                                    page_text += span["text"] + " "
                            page_text += "\n"

                    extracted_text += f"\n--- Page {page_number+1} ---\n{page_text}\n"

                doc.close()

                # Save extracted text as .md
                markdown_path = chat_dir / f"{source_path.stem}.md"
                with open(markdown_path, "w", encoding="utf-8") as f:
                    f.write(extracted_text)

                self.logger.success(f"PDF converted and saved at: {markdown_path}")

                return Source(
                    type="provided",
                    filename=markdown_path.name,
                    reference_index=str(markdown_path),
                    text=extracted_text
                )

            except Exception as e:
                self.logger.error(f"Error processing PDF {source_path}: {e}")
                return None

        # Handle unsupported files (copy as-is)
        else:
            self.logger.warning(f"Unrecognized file type: {source_path.name}")
            shutil.copy2(source_path, destination_path)
            return Source(
                type="provided",
                filename=destination_path.name,
                reference_index=str(destination_path),
                text=f"Content of {source_path.name}."
            )