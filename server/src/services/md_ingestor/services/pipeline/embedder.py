import random
import pandas as pd
import asyncio
from openai._exceptions import RateLimitError
from typing import Any, List, Dict, Union, Optional
from src.common.errors import FileProcessingError
from src.common.connectors.postgres.base import PostgresManager
from src.common.connectors.postgres.token import TokenRepo
from src.common.logging.logger import DebugLogger
from config.settings import settings

DEVICE = settings.system.device

ModelType = Union[
    "OpenAIEmbedding", "AzureOpenAIEmbedding", "HuggingFaceEmbedding", "VertexTextEmbedding", "OllamaEmbedding"
]

class Embedder:
    """
    A class for generating embeddings for document elements using an embedding engine.
    """
    def __init__(
            self,
            embedder_model: ModelType,
            provider: str,
            device: str = DEVICE,
            logger: DebugLogger = None,
            db_manager: Optional[PostgresManager] = None
    ) -> None:
        """
        Initialize the Embedder with an embedding engine and device configuration.
        :param embedder_model: The embedding engine to use.
        :param device: The device to run the embedding engine on.
        """
        self.logger = logger or DebugLogger(class_name=self.__class__.__name__, main_feature="DOC")
        self.logger.info("Initializing Embedder...")
        self.device = device
        self.embedding_engine = embedder_model
        self._provider = provider
        self.token_repo = TokenRepo(db_manager=db_manager)
        self.logger.success("Embedder ready.")

    def config_log(self, user: Optional[str]):
        """
        Sets the current user for the current logger.
        :param user: the user
        """
        self.logger.set_user(user)
        self.token_repo.logger.set_user(user)

    @DebugLogger.profile
    async def run_embedder(self, elements: List[Dict[str, Any]], filename: str, max_workers: int = 10) -> List[Dict[str, Any]] | Exception:
        """
        Executes the embedding pipeline for the given elements in parallel.
        """
        self.logger.info(f"Embedding pipeline started for file: {filename}")
        self.logger.info(f"Embedding {len(elements)} chunks with concurrency limit: {max_workers}")

        semaphore = asyncio.Semaphore(max_workers)

        async def sem_task(element):
            async with semaphore:
                return await self._embed_element(element)

        try:
            tasks = [sem_task(element) for element in elements]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True) 
            self.logger.success(f"Embedding pipeline finished for file: {filename}")
            return elements
        except Exception as e:
            raise FileProcessingError(str(e), filename, "EmbeddingError")

    async def _embed_element(self, element: Dict[str, Any], max_retries=3, base_delay=2.0) -> None:
        """
        Generates and adds embeddings for a single element with exponential backoff.
        """
        for attempt in range(max_retries):
            try:
                text = element.get("text", "")
                if not text: 
                    self.logger.warning("Empty text chunk received.")
                    return
                    #text = "[empty_page]"
                    #element["text"] = text

                embeddings = await self.embedding_engine.aget_text_embedding(text)
                element["embeddings"] = embeddings
                
                # Metadata logging/DB Save
                self.token_repo.save(
                    user=self.logger.user,
                    input_tokens=len(text), # self.tokenizer.count(str(text))
                    output_tokens=len(embeddings),
                    llm_model=self.embedding_engine.model_name,
                    provider=self._provider,
                    label="EMBEDDING"
                )
                return # Success
            except Exception as e:
                is_rate_limit = any(indicator in str(e).lower() for indicator in ["429", "token", "rate limit"])
                if attempt == max_retries - 1:
                    self.logger.error(f"Failed to embed element after {max_retries} attempts: {e}")
                    raise e
                elif is_rate_limit:
                    jitter = random.uniform(0, 1)
                    sleep_time = (base_delay * (2 ** attempt)) + jitter
                    self.logger.warning(f"RateLimit hit. Retrying in {sleep_time:.2f}s (Attempt {attempt + 1})")
                    await asyncio.sleep(sleep_time)
                else:
                    self.logger.error(f"Non-retryable error: {e}")
                    raise e