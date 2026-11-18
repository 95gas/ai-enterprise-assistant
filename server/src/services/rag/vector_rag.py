from typing import Optional

from llama_index.core import StorageContext

from src.knowledge.vector.manager import VectorManager
from src.common.connectors.neo4j.manager import Neo4jDBManager
from config.settings import settings
from src.services.rag.base import RAG

MODELS_INFO_DICT = settings.models_info.model_dump()


class VectorRAG(RAG):
    """
    A specialized implementation of the Retrieval-Augmented Generation (RAG) pipeline
    that focuses on vector-based document retrieval.

    This class integrates vector-based storage and retrieval functionality, supporting
    efficient query execution and management of vector embeddings.
    """

    def __init__(self, db_manager: Optional[Neo4jDBManager] = None) -> None:
        """
        Initializes the VectorRAG pipeline by setting up components for vector-based retrieval.
        """
        self.embedding_dimensions = self._get_embedding_dimensions(MODELS_INFO_DICT)
        super().__init__(db_manager=db_manager)


    def _get_embedding_dimensions(self, models_info_dict) -> int:
        try:
            custom_name = models_info_dict["embedder_model"]["custom_name"]
            provider = models_info_dict["embedder_model"]["provider"]
            return models_info_dict["providers"][provider][custom_name]["embedding_dimensions"]
        except Exception as e:
            self.logger.error(
                f"Embedding dimensions not configured correctly: make sure you have set as embedder_model a model with an embedding_dimensions [int].\n\
                Error: {e}")


    def _initialize_managers(self) -> None:
        """
        Configures the vector manager and its associated storage context.

        This method sets up the vector store and initializes the vector manager,
        enabling efficient storage, retrieval, and management of vector embeddings.

        :raises Exception:
            Logs any errors encountered during the initialization process.
        """
        try:
            self.logger.info("Initializing vector manager...")

            # Create the vector store and its associated storage context
            vector_store = self.db_manager.create_vector_store(embedding_dimensions=self.embedding_dimensions)
            vector_storage_context = StorageContext.from_defaults(vector_store=vector_store)
            # Initialize the VectorManager with the configured store and context
            self.knowledge_manager = VectorManager(vector_store, vector_storage_context)

            self.logger.success("Vector manager initialized successfully.")
        except Exception as e:
            self.logger.error(f"Failed to initialize vector manager: {e}", exc_info=True)