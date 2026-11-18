from dataclasses import dataclass, field
from typing import List, Any, Dict, Optional, Callable

from src.services.chat.chat_manager import ChatManager
from src.knowledge.graph.manager import GraphManager
from src.knowledge.vector.manager import VectorManager
from src.services.rag.graph_rag import GraphRAG
from src.services.rag.vector_rag import VectorRAG
from src.common.connectors.postgres.base import PostgresManager
from src.common.connectors.neo4j.manager import Neo4jDBManager
from src.common.connectors.s3.manager import S3DBManager
from src.common.logging.logger import DebugLogger
from src.common.models.manager import ModelManager
from src.common.connectors.postgres.chat import ChatRepo
from config.settings import settings

MODELS_INFO_DICT = settings.models_info.model_dump()
main_agent = None


@dataclass
class MainAgent:
    """
    Orchestrates core components for knowledge management and conversational AI,
    integrating graph and vector knowledge systems with ingestion and chat handling.
    """
    logger: DebugLogger = field(default_factory=DebugLogger)
    db_manager: Optional[PostgresManager] = None
    db_manager_neo4j: Optional[Neo4jDBManager] = None
    db_manager_s3: Optional[S3DBManager] = None
    vector_rag: Optional[VectorRAG] = None
    graph_rag: Optional[GraphRAG] = None
    vector_manager: Optional[VectorManager] = None
    graph_manager: Optional[GraphManager] = None
    model_manager: Optional[ModelManager] = None
    user: str = None

    def __post_init__(self):
        """
        Initialize the main agent
        """
        self.logger.set_class_name(self.__class__.__name__)
        self.logger.set_main_feature("SYSTEM")

        """
        Initialize components after dataclass instantiation.
        """
        self.logger.info("Initializing MainAgent...")
        try:
            # Initialize database managers if not provided
            self.logger.info("Initializing databases...")
            self.db_manager = self.db_manager or PostgresManager()
            self.db_manager.initialize()
            self.db_manager_neo4j = self.db_manager_neo4j or Neo4jDBManager()
            self.db_manager_s3 = self.db_manager_s3 or S3DBManager()
            self.logger.success("Databases ready.")

            # Initialize RAG systems if not provided
            self.logger.info("Initializing Knowledge...")
            self.vector_rag = self.vector_rag or VectorRAG(db_manager=self.db_manager_neo4j)
            self.graph_rag = self.graph_rag or GraphRAG(db_manager=self.db_manager_neo4j)
            self.logger.success("Knowledge ready.")

            # Initialize document ingestor
            self.logger.info("Initializing model manager...")
            self.model_manager = self.model_manager or ModelManager()
            self.logger.success("Model manager ready.")

            # Initialize document ingestor
            self.logger.info("Initializing ingestor pipeline...")

            self.logger.success("MainAgent initialized successfully.")
        except Exception as e:
            self.logger.error("Error initializing MainAgent.", exc_info=True)
            raise

    def initialize(self, user: str):
        """
        Sets the current user for the current logger.
        :param user: the user
        """
        self.user = user
        self.logger.set_user(user)
        self.db_manager_s3.config_log(user)
        self.db_manager.config_log(user)
        self.db_manager_neo4j.config_log(user)
        self.model_manager.config_log(user)

    def get_new_chat_manager(self) -> ChatManager:
        """
        Return a new chat manager for conversational interactions.
        :return: ChatManager instance.
        """
        helper_llm = self.model_manager.get_model(model_data=MODELS_INFO_DICT["helper_model"])
        chat_manager = ChatRepo(self.db_manager)
        chat_manager = ChatManager(vector_rag=self.vector_rag,
                                   graph_rag=self.graph_rag,
                                   db_manager_neo4j=self.db_manager_neo4j,
                                   db_manager=chat_manager,
                                   helper_llm=helper_llm,
                                   user=self.user)
        return chat_manager

    def get_neo4j_connection(self) -> Neo4jDBManager:
        """
        Retrieve the Neo4j database manager.
        :return: Neo4jDBManager instance.
        """
        return self.db_manager_neo4j

    def get_postgres_connection(self) -> PostgresManager:
        """
        Retrieve the PostgreSQL database manager.
        """
        return self.db_manager

    def get_s3_connection(self) -> S3DBManager:
        """
        Retrieve the S3 database managers.
        :return: S3DBManager instance.
        """
        return self.db_manager_s3

    def get_embedding_model(self) -> Any:
        """
        Placeholder for retrieving the embedding model.
        """
        self.logger.warning("get_model is not yet implemented.")
        pass


def get_main_agent(logger: DebugLogger = None,
                   db_manager: PostgresManager = None,
                   db_manager_neo4j: Neo4jDBManager = None,
                   db_manager_s3: S3DBManager = None,
                   user: Optional[str] = "undefined"):
    """
    Get or create the singleton MainAgent instance. Allows for dependency injection during testing.
    :param logger: Optional DebugLogger instance.
    :param db_manager: Optional PostgreSQL manager instance.
    :param db_manager_neo4j: Optional Neo4jDBManager instance.
    :param db_manager_s3: Optional S3DBManager instance.
    :param user: Optional username.
    :return: MainAgent instance.
    """
    global main_agent
    if main_agent is None:
        main_agent = MainAgent(
            logger=logger or DebugLogger(),
            db_manager=db_manager,
            db_manager_neo4j=db_manager_neo4j,
            db_manager_s3=db_manager_s3
        )
        main_agent.initialize(user)
    return main_agent
