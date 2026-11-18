from typing import Optional, Union
from abc import ABC, abstractmethod

from src.common.connectors.neo4j.manager import Neo4jDBManager
from src.common.logging.logger import DebugLogger

class RAG(ABC):
    """
    A hybrid retrieval pipeline utilizing Neo4j for both vector-based document retrieval
    and knowledge graph storage. Supports structured and unstructured query handling.
    """

    def __init__(self,
                 logger: Optional[DebugLogger] = None,
                 db_manager: Optional[Neo4jDBManager] = None) -> None:
        """
        Initializes the RAG pipeline with components for graph and vector-based retrieval.

        :param db_manager: Instance of Neo4jDBManager for database interaction (optional).
        """
        self.logger = logger or DebugLogger(class_name=self.__class__.__name__,
                                            main_feature="SYSTEM")
        self.db_manager = db_manager or Neo4jDBManager()
        self.knowledge_manager = None
        self._initialize_managers()

    def config_log(self, user: Optional[str]):
        """
        Sets the current user for the current logger and the class name to print.
        :param user: the user
        """
        self.logger.set_user(user)

    @abstractmethod
    def _initialize_managers(self) -> None:
        """
        Initializes necessary managers (e.g., RAG Manager).
        Placeholder for future initialization logic.
        """
        pass