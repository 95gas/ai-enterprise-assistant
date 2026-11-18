from llama_index.core import VectorStoreIndex, StorageContext
from llama_index.core.vector_stores.types import VectorStore

from src.knowledge.base import KnowledgeManager
from src.common.logging.logger import DebugLogger

class VectorManager(KnowledgeManager):
    """
    Manages vector store operations, including document indexing, retrieval,
    and querying within a vector-based storage system.
    """

    def __init__(self, store: VectorStore,
                 storage_context: StorageContext,
                 logger: DebugLogger = None
                 ) -> None:
        """
        Initialize the VectorManager with a vector storage backend and context configuration.

        :param store: The vector store used for managing indexed data.
        :param storage_context: Context or configuration for managing vector storage.
        """
        super().__init__(store, storage_context)
        self.logger.info("VectorManager initialized with vector storage backend.")


    def load_index(self) -> bool:
        """
        Load the index from the vector store if available.

        :return: True if the index was successfully loaded, False otherwise.
        """

        try:
            self.logger.info("Attempting to load the index from the vector store.")
            self.index = VectorStoreIndex.from_vector_store(
                vector_store=self.store,
                storage_context=self.storage_context,
                show_progress=True,
                store_nodes_override=True,
            )
            self.logger.success("Index loaded successfully from the vector store.")
            return True
        except Exception as e:
            self.logger.error("Error occurred while loading the index:", exc_info=True)
            return False