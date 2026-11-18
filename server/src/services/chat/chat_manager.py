from dataclasses import dataclass, field
from typing import Optional, Dict, List, Union, AsyncGenerator, Any

from llama_index.core.postprocessor import SimilarityPostprocessor
from llama_index.core.base.llms.types import ChatMessage
from llama_index.llms.azure_openai import AzureOpenAI
from llama_index.llms.google_genai import GoogleGenAI
from llama_index.llms.openai import OpenAI
from llama_index.llms.ollama import Ollama

from src.services.chat.chat_history import ChatHistoryManager
from src.common.connectors.neo4j.manager import Neo4jDBManager
from src.common.connectors.postgres.base import PostgresManager
from src.services.chat.schema import AgentProgress, Source, Response
from src.services.chat.qa_manager import QAManager
from src.common.logging.logger import DebugLogger
from src.services.rag.vector_rag import VectorRAG
from src.services.rag.graph_rag import GraphRAG
from config.settings import settings

CHAT_HISTORY_BUFFER_SIZE = settings.CHAT_HISTORY_BUFFER_SIZE


@dataclass
class ChatManager:
    """
    Manages chat sessions, including user interaction, chat history, and LLM queries.
    """
    vector_rag: VectorRAG
    graph_rag: GraphRAG
    db_manager_neo4j: Neo4jDBManager
    db_manager: PostgresManager
    helper_llm: Union[OpenAI, AzureOpenAI, Ollama, GoogleGenAI]
    similarity_postprocessor: SimilarityPostprocessor = field(
        default_factory=lambda: SimilarityPostprocessor(similarity_cutoff=0))
    chat_history_manager: Optional[ChatHistoryManager] = field(init=False, default=None)
    logger: DebugLogger = field(default_factory=DebugLogger)
    qa_manager: Optional[QAManager] = field(init=False, default=None)
    user: Optional[str] = field(init=True, default=None)
    chat_name: Optional[int] = field(init=False, default=None)


    def __post_init__(self) -> None:
        """
        Initializes ChatManager after dataclass instantiation.
        """
        self.logger.set_user(user=self.user)
        self.logger.set_main_feature(main_feature="CHAT")
        self.logger.set_class_name(self.__class__.__name__)
        self.logger.info("Initializing ChatManager...")
        self.chat_history_manager = ChatHistoryManager(buffer_size=CHAT_HISTORY_BUFFER_SIZE, user=self.user)
        self.logger.success("ChatManager initialized successfully.")


    def get_chat_history(self) -> List[ChatMessage]:
        """Fetches the current chat history."""
        self.logger.info("Retrieving chat history...")
        return self.chat_history_manager.get_history()


    def initialize_chat(self, chat_history: List[ChatMessage]) -> None:
        """
        Initializes the chat session with a given chat history.
        """
        self.logger.info("Initializing chat session...")
        self.initialize_chat_history(chat_history)
        self.qa_manager = QAManager(
            graph_rag=self.graph_rag,
            db_manager_neo4j=self.db_manager_neo4j,
            db_manager=self.db_manager,
            user=self.user,
        )
        self.logger.success("Chat session initialized successfully.")


    def initialize_chat_history(self, chat_history: List[ChatMessage]) -> None:
        """
        Initializes the chat history.
        """
        try:
            self.logger.info(f"Initializing chat history with {len(chat_history)} messages.")
            self.chat_history_manager.initialize_history(chat_history)
            self.logger.success("Chat history initialized successfully.")
        except Exception as e:
            self.logger.error(f"Error initializing chat history: {e}", exc_info=True)
            raise e
    

    async def get_answer(self,
                         llm: Union[OpenAI, AzureOpenAI, Ollama, GoogleGenAI],
                         req_info: Dict = None,
                         ) -> AsyncGenerator[Any, None]:
        """
        Queries the LLM and updates the chat history with the response.
        :param llm: llm to use
        :param req_info: request info
        :return: answer and sources.
        """
        self.logger.info("Getting answer...")
        try:
            response_generator = self.qa_manager.invoke(llm=llm,
                                                        helper_llm=self.helper_llm,
                                                        req_info=req_info,
                                                        )
            async for response in response_generator:
                if isinstance(response, AgentProgress):
                    yield response, 200
                elif isinstance(response, str):
                    yield response
                elif isinstance(response, Response):
                    yield {
                        "answer": str(response.response),
                        "sources": self.format_sources(response.sources),
                        "recorded_notes": response.recorded_notes,
                        "metadata": response.metadata,
                    }, 200
                else:
                    yield response, 200
        except Exception as e:
            raise e


    def format_sources(self, sources: List[Source]) -> List[Dict[str, Any]]:
        """
        Formats sources by grouping pages for each file, 
        sorted by type then filename.
        """
        if not sources:
            return []
        self.logger.info("Formatting sources...")

        if False:
            sources_json = []
            for s in sources:
                s.pop("text", None)
                sources_json.append(s.model_dump())
            return sorted(sources_json, key=lambda x: (x["type"].lower(), x["filename"].lower(), x["reference_id"]))

        grouped_sources = {}
        for s in sources:
            source = s.model_dump()
            filename = source.pop("filename")
            source_type = source["type"] # TODO Replace with pop to avoid redundancy: source_type = source.pop("type")
            source.pop("text", None)

            if filename not in grouped_sources:
                grouped_sources[filename] = {"type": source_type,
                                             "filename": filename, 
                                             "references": []}
            grouped_sources[filename]["references"].append(source)

        sorted_list = sorted(grouped_sources.values(), key=lambda x: (x["type"].lower(), x["filename"].lower()))
        for entry in sorted_list:
            entry['references'] = sorted(entry["references"], key=lambda item: item["reference_id"])
        return sorted_list