import os
from typing import List, Any, Optional, Dict, Literal

from llama_index.graph_stores.neo4j import Neo4jPropertyGraphStore
from llama_index.vector_stores.neo4jvector import Neo4jVectorStore
from llama_index.tools.neo4j import Neo4jQueryToolSpec
from src.common.models.manager import ModelManager
from src.common.logging.logger import DebugLogger
from config.settings import settings

NEO4J_URL = settings.neo4j.url
NEO4J_USERNAME = settings.neo4j.username
NEO4J_PASSWORD = settings.neo4j.password
NEO4J_DATABASE = settings.neo4j.database
MODELS_INFO_DICT = settings.models_info.model_dump()


class Neo4jDBManager:
    """
    Manages configuration and creation of Neo4j graph/vector stores.
    :param url: Neo4j connection URL. Defaults to environment variable "NEO4J_URL" or "bolt://localhost:7687".
    :type url: str, optional
    :param username: Neo4j username. Defaults to environment variable "NEO4J_USERNAME" or "neo4j".
    :type username: str, optional
    :param password: Neo4j password. Defaults to environment variable "NEO4J_PASSWORD".
    :type password: str, optional
    :param database: Neo4j database name. Defaults to environment variable "NEO4J_DATABASE" or "neo4j".
    :type database: str, optional
    :param logger: Logger instance for debugging and error logging. Defaults to a new DebugLogger instance.
    :type logger: DebugLogger, optional
    :param llm_service: LLMService instance for LLM integration. Defaults to a new LLMService instance.
    :type llm_service: LLMService, optional
    :param query_tool: Custom Neo4jQueryToolSpec for executing queries. Defaults to a new Neo4jQueryToolSpec instance.
    :type query_tool: Neo4jQueryToolSpec, optional
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        """
        Override __new__ to implement the singleton pattern.
        Ensures only one instance of Neo4jDBManager is ever created
        """
        if cls._instance is None:
            cls._instance = super(Neo4jDBManager, cls).__new__(cls)
        return cls._instance


    def __init__(
            self,
            url: str = None,
            username: str = None,
            password: str = None,
            database: str = None,
            logger: DebugLogger = None,
    ):
        # Check if instance is already initialized
        if hasattr(self, '_initialized') and self._initialized:
            return

        self.logger = logger or DebugLogger(class_name=self.__class__.__name__, main_feature="DATABASE", use_panel_for_errors=True)
        self.url = url or NEO4J_URL
        self.username = username or NEO4J_USERNAME
        self.password = password or NEO4J_PASSWORD
        self.database = database or NEO4J_DATABASE
        self.model_manager = ModelManager()
        self.llm = self.model_manager.get_model(model_data=MODELS_INFO_DICT["helper_model"])
        self.RunQueryTool = Neo4jQueryToolSpec(
            url=self.url,
            user=self.username,
            password=self.password,
            llm=self.llm,
            database=self.database,
        )

        self.logger.info("Establishing new Neo4J connection...")
        self._validate_password()

        self.logger.success(
            f"Neo4jDBManager connected with URL: '{self.url}', Database: '{self.database}'."
        )

        # Set flag to indicate initialization is complete
        self._initialized = True


    def _validate_password(self):
        """
        Validates that the Neo4j password is provided.

        :raises ValueError: If the password is not set.
        """
        if not self.password:
            error_message = "Neo4j password is required."
            self.logger.error(error_message)
            raise ValueError(error_message)


    def config_log(self, user: Optional[str]):
        """Set user logs for loggers"""
        self.logger.set_user(user)
        self.model_manager.config_log(user)


    def create_graph_store(self) -> Neo4jPropertyGraphStore:
        """
        Creates and returns a Neo4jPropertyGraphStore instance.

        :return: Instance of Neo4jPropertyGraphStore.
        :rtype: Neo4jPropertyGraphStore
        """
        return self._initialize_store(Neo4jPropertyGraphStore, "Neo4jPropertyGraphStore")


    def create_vector_store(self, embedding_dimensions: int = 1536, hybrid_search: bool = True) -> Neo4jVectorStore:
        """
        Creates and returns a Neo4jVectorStore instance.
        :param embedding_dimensions: Dimension of the embeddings. Defaults to 1536.
        :type embedding_dimensions: int, optional
        :param hybrid_search: Whether to enable hybrid search. Defaults to True.
        :type hybrid_search: bool, optional
        :return: Instance of Neo4jVectorStore.
        :rtype: Neo4jVectorStore
        """
        return self._initialize_store(
            Neo4jVectorStore,
            "Neo4jVectorStore",
            embedding_dimension=embedding_dimensions,
            hybrid_search=hybrid_search,
        )


    def _initialize_store(self, store_class: type, store_name: str, **kwargs):
        """
        Initializes a store instance with the given class and parameters.

        :param store_class: Class of the store to initialize.
        :type store_class: type
        :param store_name: Name of the store for logging purposes.
        :type store_name: str
        :param kwargs: Additional parameters for store initialization.
        :return: Instance of the specified store class.
        :rtype: Any
        :raises RuntimeError: If store creation fails.
        """
        try:
            store_instance = store_class(
                username=self.username,
                password=self.password,
                url=self.url,
                database=self.database,
                **kwargs,
            )
            self.logger.success(f"{store_name} instance created successfully.")
            return store_instance
        except Exception as e:
            error_message = f"Failed to create {store_name}: {e}"
            self.logger.error(error_message)
            raise RuntimeError(error_message) from e
        

    def _run_query(self, neo4j_query: str) -> List[Dict[str, Any]]:
        resp = self.RunQueryTool.query_graph_db(neo4j_query)
        keys = resp[0]
        values = resp[1:]
        list_of_dicts = [dict(zip(keys, item)) for item in values]
        return list_of_dicts


    def delete_document(self, s3_bucket: str, s3_path: str, filename: str) -> None:
        """
        Deletes a document from the Neo4j database by filename and s3_path.
        """
        try:
            neo4j_query = (
                "MATCH (n:Chunk) WHERE n.s3_bucket=$s3_bucket AND n.s3_path=$s3_path AND n.filename=$filename "
                "CALL { WITH n DETACH DELETE n } IN TRANSACTIONS OF 10000 ROWS;"
            )
            params = {"s3_bucket": s3_bucket, "s3_path": s3_path, "filename": filename}
            self.RunQueryTool.query_graph_db(neo4j_query, params=params)
        except Exception as e:
            self.logger.error(str(e))
            raise e
    

    def get_list_docs(self, s3_bucket: Literal["users", "shared", "system"], s3_path: str, required_metadata: Optional[List[str]]) -> List[Dict[str, Any]]:
        """
        Retrieves documents metadata from the Neo4j database.
        :param folder: s3 folder path.
        :param required_metadata: List of metadata to extract for each document.
        :return: List of dictionaries with retrieved document metadata.
        """

        neo4j_query = (
            "MATCH (n:Chunk) WHERE n.s3_bucket=$s3_bucket AND n.s3_path=$s3_path "
            "RETURN DISTINCT n.filename AS filename"
        )
        if required_metadata:   
            neo4j_query += ", " + ", ".join([f"n.{metadata} AS {metadata}" for metadata in required_metadata])

        params = {"s3_bucket": s3_bucket, "s3_path": s3_path}
        resp = self.RunQueryTool.query_graph_db(neo4j_query, params=params)
        keys = resp[0]
        values = resp[1:]
        list_of_dicts = [dict(zip(keys, item)) for item in values]
        return list_of_dicts


    def retrieve_documents(self, visibility_groups: List[str]) -> list[dict[Any, Any]]:
        """
        Retrieves documents matching the given 'visibility_groups' from the Neo4j database.
        :param visibility_groups: List of 'visibility_groups' to match.
        :return: List of dictionaries with retrieved document filenames and number of tokens
        :rtype: list[dict[Any, Any]]
        """
        neo4j_query = (
            "MATCH (n:Chunk) "
            "WHERE ANY(group IN n.visibility_groups WHERE group IN $groups) "
            "RETURN n.filename AS filename, "
                "n.s3_bucket AS s3_bucket, "
                "n.s3_path AS s3_path, "
                "n.upload_datetime AS upload_datetime, "
                "n.uploaded_by AS uploaded_by, "
                "sum(COALESCE(n.table_tokens, n.tokens)) AS totalTokens," \
                "n.og_uri AS og_uri"
        )
        resp = self.RunQueryTool.query_graph_db(neo4j_query, params={"groups": visibility_groups})
        keys = resp[0]
        values = resp[1:]
        list_of_dicts = [dict(zip(keys, item)) for item in values]
        return list_of_dicts
    

    def get_private_docs(self, user_email: str) -> list[dict[Any, Any]]:
        neo4j_query = (
            "MATCH (n:Chunk) "
            "WHERE ANY(group IN n.visibility_groups WHERE group IN $groups) "
            "RETURN DISTINCT n.filename AS filename"
        )
        resp = self.RunQueryTool.query_graph_db(neo4j_query, params={"groups": [user_email]})
        keys = resp[0]
        values = resp[1:]
        list_of_dicts = [dict(zip(keys, item)) for item in values]
        return list_of_dicts
    

    def check_duplicate_doc(self, s3_bucket: str, s3_path: str, filename: str) -> bool:
        neo4j_query = (
            "MATCH (n:Chunk) "
            "WHERE n.s3_bucket = $s3_bucket AND n.s3_path = $s3_path AND n.filename = $filename "
            "RETURN COUNT(n) AS duplicate_count"
        )
        resp = self.RunQueryTool.query_graph_db(neo4j_query,
                                                params={"s3_bucket": s3_bucket,
                                                        "s3_path": s3_path,
                                                        "filename": filename})
        if resp and len(resp) > 1:
            duplicate_count = resp[1][0]
            return duplicate_count > 0
        return False