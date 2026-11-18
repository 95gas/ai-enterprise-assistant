import json, time
from pydantic import Field
from openai import APITimeoutError, RateLimitError
from typing import Sequence, List, Dict, Iterable, Any, Union

from llama_index.core.schema import BaseNode, TransformComponent, MetadataMode
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.extractors import BaseExtractor
from llama_index.llms.azure_openai import AzureOpenAI
from llama_index.core.utils import get_tqdm_iterable
from llama_index.core.llms import ChatMessage
from llama_index.llms.openai import OpenAI
from llama_index.llms.ollama import Ollama

from src.schema.knowledge_graph import SchemaHandler
from src.core.models.manager import ModelManager
from src.common.logging.logger import DebugLogger
from config.settings import settings

MODELS_INFO_DICT = settings.models_info.model_dump()
NUM_WORKERS = settings.system.num_workers
DEVICE = settings.system.device


class MetadataExtraction(TransformComponent):
    def __call__(self, nodes: Sequence[BaseNode], **kwargs) -> Sequence[BaseNode]:
        """
        Apply metadata extraction transformations on the given nodes.
        :param nodes: Sequence of BaseNode objects to transform.
        :param kwargs: Additional arguments for pipeline execution.
        :return: Transformed nodes with extracted metadata.
        """
        pass

    @staticmethod
    def run(nodes: Sequence[BaseNode], llm: Union[OpenAI, AzureOpenAI, Ollama], show_progress: bool = True, in_place: bool = False) \
            -> Sequence[BaseNode]:
        """
        Static method to run metadata extraction on given nodes.
        :param nodes: Sequence of BaseNode objects to transform.
        :param show_progress: Whether to display progress during execution.
        :param in_place: Whether transformations are applied in place.
        :return: Transformed nodes with extracted metadata.
        """
        logger = DebugLogger()
        logger.info("Extracting metadata...")

        try:
            extractors = MetadataExtraction._initialize_extractors(llm)
            pipeline = IngestionPipeline(transformations=extractors)
            base_nodes = pipeline.run(
                nodes=nodes,
                show_progress=show_progress,
                in_place=in_place,
            )
            logger.success("Metadata extraction completed successfully.")
            return base_nodes

        except Exception as e:
            logger.error("Error during metadata extraction", exc_info=True)
            raise e

    @staticmethod
    def _initialize_extractors(llm: Union[OpenAI, AzureOpenAI, Ollama]) -> List[TransformComponent]:
        """
        Initialize metadata extractors with required configurations.
        :return: List of configured metadata extractors.
        """
        return [
            LLMEntityExtractor(
                llm=llm,
                device=DEVICE,
                disable_template_rewrite=True,
                metadata_mode = MetadataMode.NONE,
            ),
        ]


class LLMEntityExtractor(BaseExtractor):

    llm: Union[OpenAI, AzureOpenAI, Ollama] = Field(
        default=ModelManager().get_model(MODELS_INFO_DICT["doc_model"]),
        description="The llm instance to use.",
    )

    def __init__(
            self,
            llm: Union[OpenAI, AzureOpenAI, Ollama],
            **kwargs: Any,
    ) -> None:
        """Init params."""
        super().__init__(**kwargs)
        self.llm = llm

    async def aextract(self, nodes: Sequence[BaseNode]) -> List[Dict]:
        entities_map = SchemaHandler.get_entities()
        prompt = (f"Extract the entities from the text using a specific entity map.\n"
                  f"Return a json output where the keys are the entities in the entity map "
                  f"and each value of the keys is a list of string. Follow this schema:\n"
                  f"key: [str]"
                  f"The entity map is defined by the list of entities below:\n"
                  f"{entities_map}")

        # Extract node-level entity metadata
        metadata_list: List[Dict] = [{} for _ in nodes]
        metadata_queue: Iterable[int] = get_tqdm_iterable(
            range(len(nodes)), self.show_progress, "Extracting entities using the llm..."
        )

        for i in metadata_queue:
            metadata = metadata_list[i]
            metadata.update({"entities" : {}})
            node_text = nodes[i].get_content(metadata_mode=self.metadata_mode)
            dict_entities = self.llm_extract(prompt=prompt, text=node_text)
            entity_labels = dict_entities.keys()

            if entity_labels:
                for label in entity_labels:
                    if dict_entities[label]:
                        if label not in metadata:
                            metadata["entities"][label] = set()
                        if isinstance(dict_entities[label], list):
                            metadata["entities"][label].add(", ".join(dict_entities[label]))

        # convert metadata from set to list
        for metadata in metadata_list:
            for key, val in metadata["entities"].items():
                if isinstance(val, set):
                    metadata["entities"][key] = list(val)
            metadata["entities"] = json.dumps(metadata["entities"])
        return metadata_list

    def llm_extract(
        self,
        prompt: str,
        text: str,
        max_retries: int = 10,
        timeout: int = 360.0,
    ):

        logger = DebugLogger()

        messages = [
            ChatMessage(role="system", content=prompt),
            ChatMessage(
                role="user",
                content=text,
            )
        ]

        tries = 0
        while tries < max_retries:
            try:
                response = self.llm.chat(
                    messages=messages,
                    timeout=timeout,
                    response_format={"type": "json_object"}
                )
                response_text = response.message.content
                return json.loads(response_text)
            except (APITimeoutError, RateLimitError) as e:
                # Rate limit exceeded
                tries += 1
                wait_time = tries * 3
                logger.warning(
                    f"Rate limit error: {e}. Retrying in {wait_time} seconds... (Attempt {tries}/{max_retries})"
                )
                time.sleep(wait_time)
            except Exception as e:
                logger.error(f"Skipping entity extraction! An unexpected error occurred: {e}")
                return {}
        logger.warning("Max retries exceeded. Skipping entity extraction!...")
        return {}