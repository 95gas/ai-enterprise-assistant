from abc import ABC, abstractmethod
from typing import Optional, Sequence, Union
from llama_index.core import StorageContext
from llama_index.core.base.base_query_engine import BaseQueryEngine

from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.schema import BaseNode
from llama_index.core.indices.base import BaseIndex
from llama_index.core.vector_stores.types import BasePydanticVectorStore
from llama_index.graph_stores.neo4j import Neo4jPropertyGraphStore

from src.common.logging.logger import DebugLogger


class KnowledgeManager(ABC):
    """
    Abstract base class for managing indexing, retrieval, and querying of knowledge data.
    Provides methods for indexing documents, creating a chat engine, and executing queries.
    """

    def __init__(self,
                 store: Union[BasePydanticVectorStore, Neo4jPropertyGraphStore],
                 storage_context: StorageContext,
                 logger: Optional[DebugLogger] = None) \
            -> None:
        """
        Initialize the KnowledgeManager with a store and storage context.

        :param store: The storage backend for managing knowledge data.
        :param storage_context: Configuration context for the storage backend.
        """
        self.store = store
        self.storage_context = storage_context
        self.index: Optional[BaseIndex] = None
        self.query_engine: Optional[BaseQueryEngine] = None
        self.retriever: Optional[BaseRetriever] = None
        self.logger = logger or DebugLogger(class_name=self.__class__.__name__,
                                            main_feature="SYSTEM")

    def config_log(self, user: Optional[str]):
        """
        Sets the current user for the current logger and the class name to print.
        :param user: the user
        """
        self.logger.set_user(user)

    def get_index(self) -> Optional[BaseIndex]:
        """
        Get the current index, if available.

        :return: The current index or None if not initialized.
        """
        return self.index

    def insert_nodes(self, nodes: Sequence[BaseNode], filename: str) -> None:
        """
        Index a list of nodes into the knowledge store.

        :param filename: filename of file being processed
        :param nodes: List of nodes objects to be indexed.
        :raises Exception: If an error occurs during indexing.
        """
        if not self.index:
            error_message = f"Cannot insert documents {filename}: Index is not initialized."
            self.logger.error(error_message)
            raise ValueError(error_message)

        BATCH_SIZE = 200
        try:
            self.logger.info(f"Storing document {filename} in the knowledge base")
            for i in range(0, len(nodes), BATCH_SIZE):
                batch = nodes[i : i + BATCH_SIZE]
                self.logger.info(f"Inserting batch {i} to {i + len(batch)}...")
                self.index.insert_nodes(batch)
            self.logger.success(f"Stored document {filename} in the knowledge base successfully.")
        except Exception as e:
            self.logger.error(f"Error during document insertion {filename}:", exc_info=True)
            raise

    @abstractmethod
    def load_index(self) -> bool:
        """
        Abstract method to load an existing index from storage.

        :return: True if the index was loaded successfully, False otherwise.
        """
        pass
