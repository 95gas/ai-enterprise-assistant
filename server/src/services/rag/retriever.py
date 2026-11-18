from typing import List, Optional, Any, Union, Dict
from llama_index.core import QueryBundle, Settings
from llama_index.core.retrievers import BaseRetriever, VectorIndexRetriever
from llama_index.core.schema import BaseNode, ImageNode, IndexNode, TextNode, NodeWithScore
from llama_index.core.base.embeddings.base import BaseEmbedding
from src.common.connectors.neo4j.manager import Neo4jDBManager
from src.common.logging.logger import DebugLogger
import re, json
from llama_index.graph_stores.neo4j import Neo4jPropertyGraphStore
from llama_index.llms.azure_openai import AzureOpenAI
from llama_index.llms.openai import OpenAI
from llama_index.llms.ollama import Ollama
from llama_index.llms.google_genai import GoogleGenAI
from llama_index.core.postprocessor.types import BaseNodePostprocessor
from llama_index.core.callbacks import CallbackManager
from src.knowledge.graph.manager import GraphManager
from src.services.rag.filters import build_start_query


class CustomRetriever(BaseRetriever):
    """
    Custom retriever that performs semantic and hybrid searches using a vector index and Neo4j database.
    """

    def __init__(
            self,
            database_manager: Neo4jDBManager,
            graph_store: Neo4jPropertyGraphStore,
            hybrid_mode: bool = True,
            similarity_top_k: int = 25,
            text_node_property: str = "text",
            embedding_node_property: str = "embedding",
            keyword_index_name: str = "keyword",
            index_name: str = "vector",
            logger: Optional[DebugLogger] = None,
            embed_model: Optional[BaseEmbedding] = None,
            ## text-to-cypher params
            llm: Union[OpenAI, AzureOpenAI, Ollama, GoogleGenAI] = None,
            node_postprocessors: Optional[List[BaseNodePostprocessor]] = None,
            user: Optional[str] = None
    ) -> None:
        """
        Initialize the custom retriever with parameters for search configuration.
        :param database_manager: Neo4j database manager.
        :param hybrid_mode: Enables hybrid search if True.
        :param similarity_top_k: Number of top results to retrieve based on similarity.
        :param text_node_property: Property name for the text content in the nodes.
        :param embedding_node_property: Property name for the embedding content in the nodes.
        :param keyword_index_name: Name of the keyword index for full-text search.
        :param index_name: Name of the vector index for similarity search.
        :param logger: (Optional) Injected DebugLogger instance for easier testing.
        """
        super().__init__()
        self.logger = logger or DebugLogger(user=user,
                                            class_name=self.__class__.__name__,
                                            main_feature="CHAT")
        self.logger.info("Initializing CustomRetriever...")

        self.database = database_manager
        self._hybrid_search = hybrid_mode
        self._similarity_top_k = similarity_top_k
        self.graph_store = graph_store
        self.llm = llm
        self._embed_model = embed_model or Settings.embed_model
        self._node_postprocessors = node_postprocessors or []
        self.callback_manager = CallbackManager([])
        for node_postprocessor in self._node_postprocessors:
            node_postprocessor.callback_manager = self.callback_manager
        self.text_node_property = text_node_property
        self.embedding_node_property = embedding_node_property
        self._keyword_index_name = keyword_index_name
        self._index_name = index_name
        # modes
        self.focus_mode = False
        self.random_mode = False
        # filters
        self.groups = None
        self.selected_documents = None
        self.excluded_ids = set()
        self.selected_chunk_numbers = None
        self.selected_page_numbers = None
        self.logger.success("CustomRetriever initialized successfully.")

    def set_groups(self, groups: List[str]) -> None:
        """
        Set groups for filtering nodes during retrieval.
        :param groups: List of visibility_groups strings.
        """
        self.logger.info("Setting groups for the retriever...")
        self.groups = groups

    def set_selected_documents(self, file_names: List[str]) -> None:
        self.selected_documents = file_names
        self.logger.success(f"Selected docs: {len(self.selected_documents)}")

    def set_selected_chunk_numbers(self, chunk_numbers: List[int]) -> None:
        self.selected_chunk_numbers = chunk_numbers
        self.logger.success(f"Selected chunk numbers: {len(self.selected_chunk_numbers)}")

    def set_selected_page_numbers(self, page_numbers: List[int]) -> None:
        self.selected_page_numbers = page_numbers
        self.logger.success(f"Selected page numbers: {len(self.selected_page_numbers)}")

    def add_excluded_ids(self, excluded_ids: List[str]) -> None:
        self.excluded_ids.update(excluded_ids)
        self.logger.success(f"Excluded {len(excluded_ids)} ids. Total excluded ids: {len(self.excluded_ids)}")

    def set_focus_mode(self, focus_mode: bool) -> None:
        self.focus_mode = focus_mode
        self.logger.success(f"Focus mode: {str(focus_mode)}")

    def set_random_mode(self, random_mode: bool) -> None:
        self.random_mode = random_mode
        self.logger.success(f"Random mode: {str(random_mode)}")

    def get_start_query(self) -> tuple[str, Dict[str, List[str]]]:
        return build_start_query(
            groups=self.groups,
            selected_documents=self.selected_documents,
            excluded_ids=self.excluded_ids,
            selected_chunk_numbers=self.selected_chunk_numbers,
            selected_page_numbers=self.selected_page_numbers,
        )

    @DebugLogger.profile
    def get_tokens_from_selected(self) -> float:
        try:
            start_query, parameters = self.get_start_query()
            end_query = "RETURN sum(COALESCE(node.table_tokens, node.tokens))"
            num_tokens = self.database.RunQueryTool.query_graph_db(start_query + end_query, params=parameters)
            return num_tokens[1:][0][0]
        except Exception as e:
            self.logger.error(f"Failed to retrieve nodes: {e}", exc_info=True)
            return float("inf")

    @DebugLogger.profile
    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        """
        Retrieve nodes based on the given query bundle.
        :param query_bundle: QueryBundle containing query string and optional embedding.
        :return: List of NodeWithScore objects.
        """
        try:
            if self.focus_mode and self.selected_documents:
                self.logger.info("Retrieving all nodes..")
                return self.retrieve_all_nodes()
            elif self.random_mode:
                self.logger.info("Retrieving random nodes..")
                return self.retrieve_random_nodes()
            elif not self.focus_mode:
                self.logger.info("Retrieving similar nodes..")
                return self.retrieve_default(query_bundle)
            else:
                self.logger.error(f"Failed to determine the retrieving strategy.")
                return []
        except Exception as e:
            self.logger.error(f"Failed to retrieve nodes: {e}", exc_info=True)
            raise e

    def retrieve_default(self,
                         query_bundle: QueryBundle):
        query = self._to_lower_case(query_bundle.query_str)
        query_bundle = QueryBundle(query)
        vector_nodes = self._retrieve_vector_nodes(query_bundle)
        vector_nodes = self.post_process_nodes(vector_nodes, query_bundle)
        '''
        vector_nodes = self.rerank_nodes(vector_nodes, query_bundle)
        '''
        # graph_nodes = self._retrieve_graph_nodes(query_bundle)
        combined_nodes = vector_nodes  # + graph_nodes
        return combined_nodes

    def retrieve_all_nodes(self) -> List[NodeWithScore]:
        """
        Retrieve nodes based on the given query bundle.
        :param query_bundle: QueryBundle containing query string and optional embedding.
        :return: List of NodeWithScore objects.
        """
        try:
            start_query, parameters = self.get_start_query()
            end_query = (
                f"RETURN node.`{self.text_node_property}` AS text, Null, "
                "node.id AS id, "
                f"node {{.*, `{self.text_node_property}`: Null, "
                f"`{self.embedding_node_property}`: Null}} AS metadata"
            )

            vector_nodes = self.database.RunQueryTool.query_graph_db(start_query + end_query, params=parameters)
            vector_nodes = vector_nodes[1:]  # Skip column names
            vector_nodes = self._convert_to_nodes_with_score(vector_nodes)
            return vector_nodes
        except Exception as e:
            self.logger.error(f"Failed to retrieve nodes: {e}", exc_info=True)
            raise

    def retrieve_random_nodes(self) -> List[NodeWithScore]:
        """
        Retrieve nodes based on the given query bundle.
        :return: List of NodeWithScore objects.
        """
        try:
            start_query, parameters = self.get_start_query()
            end_query = (
                "WITH node, rand() as rand_num "
                "ORDER BY rand_num "
                "LIMIT 5 "
                f"RETURN node.`{self.text_node_property}` AS text, Null, "
                "node.id AS id, "
                f"node {{.*, `{self.text_node_property}`: Null, "
                f"`{self.embedding_node_property}`: Null }} AS metadata"
            )
            vector_nodes = self.database.RunQueryTool.query_graph_db(start_query + end_query, params=parameters)
            vector_nodes = vector_nodes[1:]  # Skip column names
            vector_nodes = self._convert_to_nodes_with_score(vector_nodes)
            return vector_nodes
        except Exception as e:
            self.logger.error(f"Failed to retrieve nodes: {e}", exc_info=True)
            raise

    def post_process_nodes(self,
                           nodes: List[NodeWithScore],
                           query_bundle: QueryBundle) \
            -> List[NodeWithScore]:
        self.logger.info("Postprocessing nodes after retrieval...")
        for postprocessor in self._node_postprocessors:
            nodes = postprocessor.postprocess_nodes(
                nodes, query_bundle=query_bundle
            )
        return nodes

    @staticmethod
    def cypher_validator(cypher_query: str) -> str:
        result = re.search('\`\`\`cypher\n(.*)\n\`\`\`', cypher_query)
        if result:
            return result.group(1)
        result = re.search('\`\`\`\n(.*)\n\`\`\`', cypher_query)
        if result:
            return result.group(1)
        return cypher_query

    def _retrieve_graph_nodes(self,
                              query_bundle: QueryBundle):
        self.logger.info("Starting graph node retrieval...")

        graph_nodes = GraphManager.custom_query(query_bundle)
        try:
            # filter based on groups
            nodes_final: List[NodeWithScore] = []
            if graph_nodes:
                _dict = graph_nodes[0]
                key = list(_dict.keys())[0]
                result = _dict[key]
                visibility_groups = result["visibility_groups"]
                if any(x in visibility_groups for x in self.groups):
                    nodes_final.append(NodeWithScore(
                        node=TextNode(
                            text=result["text"] if "text" in list(result.keys()) else result["markdown_table"]
                        ),
                        score=1)
                    )
                self.logger.success(f"Retrieved {len(nodes_final)} graph nodes successfully.")
            return nodes_final
        except Exception as e:
            self.logger.error(str(e))
            return []

    def _retrieve_vector_nodes(self,
                               query_bundle: QueryBundle,
                               ) -> List[NodeWithScore]:

        self.logger.info("Starting vector node retrieval...")
        start_query = self._get_search_index_query(self._hybrid_search)


        query_embedding = query_bundle.embedding or self._embed_model.get_query_embedding(query_bundle.query_str)

        query = self._remove_illegal_lucene_chars(query_bundle.query_str)
        query = self._enable_lucene_chars(query)

        parameters = {
            "index": self._index_name,
            "k": self._similarity_top_k,
            "q_k": self._similarity_top_k*4,
            "embedding": query_embedding,
            "keyword_index": self._keyword_index_name,
            "query": query,
            "groups": self.groups
        }

        if self.selected_documents:
            parameters["filenames"] = self.selected_documents
            start_query = self._get_search_index_query_by_file_name()

        end_query = (
            f"RETURN node.`{self.text_node_property}` AS text, score, "
            "node.id AS id, "
            f"node {{.*, `{self.text_node_property}`: Null, "
            f"`{self.embedding_node_property}`: Null }} AS metadata"
        )
        vector_nodes = self.database.RunQueryTool.query_graph_db(start_query + end_query, params=parameters)
        vector_nodes = vector_nodes[1:]  # Skip column names
        seen = set()
        vector_nodes = self._convert_to_nodes_with_score(vector_nodes)
        vector_nodes_no_dupe = [n for n in vector_nodes  # Skip column names
                                if not (n.node.hash in seen or seen.add(n.node.hash))
                                # type: ignore[func-returns-value]
                                ]
        self.logger.success(f"Retrieved {len(vector_nodes)} vector nodes successfully.")

        return vector_nodes_no_dupe

    def _convert_to_nodes_with_score(self, vector_nodes: List[List[Any]]) -> List[NodeWithScore]:
        """
        Process retrieved nodes and convert them into NodeWithScore objects.
        :param vector_nodes: Raw query results from the database.
        :return: List of NodeWithScore objects.
        """
        nodes = []
        for record in vector_nodes:
            text = record[0]
            score = record[1]
            metadata = record[3]
            try:
                node = self.dict_to_node(metadata, text)
                nodes.append(NodeWithScore(node=node, score=score))
            except Exception as e:
                self.logger.warning(f"Error creating NodeWithScore: {str(e)}")
        return nodes

    @staticmethod
    def _to_lower_case(txt: str) -> str:
        """Lower case the text."""
        return txt.lower()

    @staticmethod
    def _get_search_index_query(hybrid: bool) -> str:
        """
        Get the appropriate search index query based on the search mode.
        :param hybrid: Whether to use hybrid search.
        :return: Query string.
        """
        if hybrid:
            return (
                "CALL () { "
                "CALL db.index.vector.queryNodes($index, $q_k, $embedding) "
                "YIELD node, score "
                "WHERE ANY(visibility_groups IN node.visibility_groups WHERE visibility_groups IN $groups) "
                "WITH collect({node:node, score:score}) AS nodes, max(score) AS max "
                "UNWIND nodes AS n "
                "RETURN n.node AS node, (n.score / max) AS score "
                "UNION "
                "CALL db.index.fulltext.queryNodes($keyword_index, $query, {limit: $q_k}) "
                "YIELD node, score "
                "WHERE ANY(visibility_groups IN node.visibility_groups WHERE visibility_groups IN $groups) "
                "WITH collect({node:node, score:score}) AS nodes, max(score) AS max "
                "UNWIND nodes AS n "
                "RETURN n.node AS node, (n.score / max) AS score "
                "} "
                "WITH node, max(score) AS score "
                "ORDER BY score DESC "
                "LIMIT $k "
                )
        return (
            "MATCH (node:Chunk) "
            "WHERE ANY(visibility_groups IN node.visibility_groups WHERE visibility_groups IN $groups) "
            "WITH node, vector.similarity.cosine(node.embedding, $embedding) AS score "
        )

    @staticmethod
    def _get_search_index_query_by_file_name() -> str:
        return (
            "CALL () { "
            "CALL db.index.vector.queryNodes($index, $q_k, $embedding) "
            "YIELD node, score "
            "WHERE ANY(visibility_groups IN node.visibility_groups WHERE visibility_groups IN $groups) "
            "AND ANY(filename IN node.filename WHERE filename IN $filenames) "
            "WITH collect({node:node, score:score}) AS nodes, max(score) AS max "
            "UNWIND nodes AS n "
            "RETURN n.node AS node, (n.score / max) AS score "
            "UNION "
            "CALL db.index.fulltext.queryNodes($keyword_index, $query, {limit: $q_k}) "
            "YIELD node, score "
            "WHERE ANY(visibility_groups IN node.visibility_groups WHERE visibility_groups IN $groups) "
            "AND ANY(filename IN node.filename WHERE filename IN $filenames) "
            "WITH collect({node:node, score:score}) AS nodes, max(score) AS max "
            "UNWIND nodes AS n "
            "RETURN n.node AS node, (n.score / max) AS score "
            "} "
            "WITH node, max(score) AS score "
            "ORDER BY score DESC "
            "LIMIT $k "
        )

    @staticmethod
    def _remove_illegal_lucene_chars(text: Optional[str]) -> Optional[str]:
        """
        Remove Lucene special characters from a query string.
        :param text: Input query string.
        :return: Cleaned query string.
        """
        if not text:
            return None
        special_chars = "!(){}[]^\"/:"
        for char in text:
            if char in special_chars:
                text = text.replace(char, "")
        return text.strip()

    @staticmethod
    def _enable_lucene_chars(text: Optional[str]) -> Optional[str]:
        """
        Remove Lucene special characters from a query string.
        :param text: Input query string.
        :return: Cleaned query string.
        """
        if not text:
            return None
        # replace all \ firsts if presents
        text = text.replace("\\", "\\\\")
        special_chars = "+-&|~*?"
        for char in text:
            if char in special_chars:
                text = text.replace(char, "\\" + char)
        return text.strip()

    @staticmethod
    def dict_to_node(metadata: dict, text: Optional[str] = None) -> BaseNode:
        """
        Convert metadata dictionary to a Node object.
        :param metadata: Metadata dictionary containing node details.
        :param text: Optional text content for the node.
        :return: BaseNode object.
        """
        node_type = metadata.get("_node_type", None)
        metadata.pop("_node_content", None) # No need of _node_content (contains original node metadata)
        node_json = json.dumps({"metadata": metadata})

        if not node_json:
            raise ValueError("Node content not found in metadata dictionary.")

        if node_type == IndexNode.class_name():
            node = IndexNode.from_json(node_json)
        elif node_type == ImageNode.class_name():
            node = ImageNode.from_json(node_json)
        else:
            node = TextNode.from_json(node_json)
        
        if text:
            node.set_content(text)
        return node