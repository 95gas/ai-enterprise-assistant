import re, asyncio, nest_asyncio
from typing import Any, List, Callable, Optional, Union

from llama_index.core.llms.llm import LLM
from llama_index.core import PropertyGraphIndex
from llama_index.core.async_utils import run_jobs
from llama_index.core.prompts import PromptTemplate
from llama_index.core import PropertyGraphIndex, StorageContext
from llama_index.core.schema import TransformComponent, BaseNode
from llama_index.core.graph_stores.types import PropertyGraphStore
from llama_index.core.indices.property_graph.utils import default_parse_triplets_fn
from llama_index.core.prompts.default_prompts import DEFAULT_KG_TRIPLET_EXTRACT_PROMPT
from llama_index.core.graph_stores.types import (
    EntityNode,
    KG_NODES_KEY,
    KG_RELATIONS_KEY,
    Relation,
)

from src.knowledge.base import KnowledgeManager
from src.common.models.manager import ModelManager
from src.common.logging.logger import DebugLogger
from config.settings import settings

MODELS_INFO_DICT = settings.models_info.model_dump()


nest_asyncio.apply()


class GraphRAGExtractor(TransformComponent):
    """Extract triples from a graph.

    Uses an LLM and a simple prompt + output parsing to extract paths (i.e. triples) and entity, relation descriptions from text.

    Args:
        llm (LLM):
            The language model to use.
        extract_prompt (Union[str, PromptTemplate]):
            The prompt to use for extracting triples.
        parse_fn (callable):
            A function to parse the output of the language model.
        num_workers (int):
            The number of workers to use for parallel processing.
        max_paths_per_chunk (int):
            The maximum number of paths to extract per chunk.
    """

    llm: LLM
    extract_prompt: PromptTemplate
    parse_fn: Callable
    num_workers: int
    max_paths_per_chunk: int

    def __init__(
        self,
        llm: Optional[LLM] = None,
        extract_prompt: Optional[Union[str, PromptTemplate]] = None,
        parse_fn: Callable = default_parse_triplets_fn,
        max_paths_per_chunk: int = 10,
        num_workers: int = 4,
    ) -> None:
        """Init params."""
        from llama_index.core import Settings

        if isinstance(extract_prompt, str):
            extract_prompt = PromptTemplate(extract_prompt)

        super().__init__(
            llm=llm or Settings.llm,
            extract_prompt=extract_prompt or DEFAULT_KG_TRIPLET_EXTRACT_PROMPT,
            parse_fn=parse_fn,
            num_workers=num_workers,
            max_paths_per_chunk=max_paths_per_chunk,
        )

    @classmethod
    def class_name(cls) -> str:
        return "GraphExtractor"

    def __call__(
        self, nodes: List[BaseNode], show_progress: bool = False, **kwargs: Any
    ) -> List[BaseNode]:
        """Extract triples from nodes."""
        return asyncio.run(
            self.acall(nodes, show_progress=show_progress, **kwargs)
        )

    async def _aextract(self, node: BaseNode) -> BaseNode:
        """Extract triples from a node."""
        assert hasattr(node, "text")

        text = node.get_content(metadata_mode="llm")
        try:
            llm_response = await self.llm.apredict(
                self.extract_prompt,
                text=text,
                max_knowledge_triplets=self.max_paths_per_chunk,
            )
            entities, entities_relationship = self.parse_fn(llm_response)
        except ValueError:
            entities = []
            entities_relationship = []

        existing_nodes = node.metadata.pop(KG_NODES_KEY, [])
        existing_relations = node.metadata.pop(KG_RELATIONS_KEY, [])
        entity_metadata = node.metadata.copy()
        for entity, entity_type, description in entities:
            entity_metadata["entity_description"] = description
            entity_node = EntityNode(
                name=entity, label=entity_type, properties=entity_metadata
            )
            existing_nodes.append(entity_node)

        relation_metadata = node.metadata.copy()
        for triple in entities_relationship:
            subj, obj, rel, description = triple
            relation_metadata["relationship_description"] = description
            rel_node = Relation(
                label=rel,
                source_id=subj,
                target_id=obj,
                properties=relation_metadata,
            )

            existing_relations.append(rel_node)

        node.metadata[KG_NODES_KEY] = existing_nodes
        node.metadata[KG_RELATIONS_KEY] = existing_relations
        return node

    async def acall(
        self, nodes: List[BaseNode], show_progress: bool = False, **kwargs: Any
    ) -> List[BaseNode]:
        """Extract triples from nodes async."""
        jobs = []
        for node in nodes:
            jobs.append(self._aextract(node))

        return await run_jobs(
            jobs,
            workers=self.num_workers,
            show_progress=show_progress,
            desc="Extracting paths from text",
        )


class GraphManager(KnowledgeManager):
    """
    Manages graph store operations, including cleaning, indexing, and query execution.
    Extends KnowledgeManager to support configurations specific to graph-based indexing.
    """

    def __init__(self, store: PropertyGraphStore, storage_context: StorageContext, logger: DebugLogger = None) -> None:
        """
        Initialize the GraphManager with a graph-based store and storage context.
        :param store: The graph data storage backend.
        :param storage_context: Context or configuration settings for storage management.
        """
        super().__init__(store, storage_context, logger)
        self.logger.info("GraphManager initialized with a graph store.")

    def load_index(self) -> bool:
        """
        Load the index from the graph store if available.
        :return: True if the index was successfully loaded, False otherwise.
        """
        self.logger.info("Attempting to load the index from the graph store.")
        try:
            # Load the index using configured components
            #self.index = self._initialize_index() # TODO
            self.logger.success("Index loaded successfully from the graph store.")
            return True
        except Exception as e:
            self.logger.error("Error while loading the index.", exc_info=True)
            return False

    def _initialize_index(self) -> PropertyGraphIndex:
        """
        Initializes the PropertyGraphIndex with the required components.
        :return: The configured PropertyGraphIndex instance.
        """
        return PropertyGraphIndex.from_existing(
            property_graph_store=self.store,
            kg_extractors=[self._get_kg_extractors()],
            storage_context=self.storage_context,
            #embed_kg_nodes=False,  # Avoid embedding text of nodes (optimization)
            show_progress=True,
            #transformations=None,  # Add metadata to the chunks
        )

    @staticmethod
    def _get_kg_extractors():
        """
        Configures and returns the knowledge graph extractors.
        :return: List of knowledge graph extractors.
        """
        llm = ModelManager().get_model(model_data=MODELS_INFO_DICT["doc_model"])

        KG_TRIPLET_EXTRACT_TMPL = """
        -Goal-
        Given a text document, identify all entities and their entity types from the text and all relationships among the identified entities.
        Given the text, extract up to {max_knowledge_triplets} entity-relation triplets.

        -Steps-
        1. Identify all entities. For each identified entity, extract the following information:
        - entity_name: Name of the entity, capitalized
        - entity_type: Type of the entity
        - entity_description: Comprehensive description of the entity's attributes and activities

        2. From the entities identified in step 1, identify all pairs of (source_entity, target_entity) that are *clearly related* to each other.
        For each pair of related entities, extract the following information:
        - source_entity: name of the source entity, as identified in step 1
        - target_entity: name of the target entity, as identified in step 1
        - relation: relationship between source_entity and target_entity
        - relationship_description: explanation as to why you think the source entity and the target entity are related to each other

        3. Output Formatting:
        - Return the result in valid JSON format with two keys: 'entities' (list of entity objects) and 'relationships' (list of relationship objects).
        - Exclude any text outside the JSON structure (e.g., no explanations or comments).
        - If no entities or relationships are identified, return empty lists: { "entities": [], "relationships": [] }.

        -An Output Example-
        {
          "entities": [
            {
              "entity_name": "Albert Einstein",
              "entity_type": "Person",
              "entity_description": "Albert Einstein was a theoretical physicist who developed the theory of relativity and made significant contributions to physics."
            },
            {
              "entity_name": "Theory of Relativity",
              "entity_type": "Scientific Theory",
              "entity_description": "A scientific theory developed by Albert Einstein, describing the laws of physics in relation to observers in different frames of reference."
            },
            {
              "entity_name": "Nobel Prize in Physics",
              "entity_type": "Award",
              "entity_description": "A prestigious international award in the field of physics, awarded annually by the Royal Swedish Academy of Sciences."
            }
          ],
          "relationships": [
            {
              "source_entity": "Albert Einstein",
              "target_entity": "Theory of Relativity",
              "relation": "developed",
              "relationship_description": "Albert Einstein is the developer of the theory of relativity."
            },
            {
              "source_entity": "Albert Einstein",
              "target_entity": "Nobel Prize in Physics",
              "relation": "won",
              "relationship_description": "Albert Einstein won the Nobel Prize in Physics in 1921."
            }
          ]
        }

        -Real Data-
        ######################
        text: {text}
        ######################
        output:"""

        return GraphRAGExtractor(
                                 llm=llm,
                                 extract_prompt=KG_TRIPLET_EXTRACT_TMPL,
                                 max_paths_per_chunk=2,
                                 parse_fn=parse_fn,
        )

def parse_fn(response_str: str) -> Any:
    import json
    json_pattern = r"\{.*\}"
    match = re.search(json_pattern, response_str, re.DOTALL)
    entities = []
    relationships = []
    if not match:
        return entities, relationships
    json_str = match.group(0)
    try:
        data = json.loads(json_str)
        entities = [
            (
                entity["entity_name"],
                entity["entity_type"],
                entity["entity_description"],
            )
            for entity in data.get("entities", [])
        ]
        relationships = [
            (
                relation["source_entity"],
                relation["target_entity"],
                relation["relation"],
                relation["relationship_description"],
            )
            for relation in data.get("relationships", [])
        ]
        return entities, relationships
    except json.JSONDecodeError as e:
        print("Error parsing JSON:", e)
        return entities, relationships
