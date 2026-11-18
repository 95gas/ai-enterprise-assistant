import os
from typing import Union, Optional, Dict, Any
from google.oauth2 import service_account

from llama_index.embeddings.vertex import VertexTextEmbedding
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.embeddings.azure_openai import AzureOpenAIEmbedding
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.google_genai import GoogleGenAI
from llama_index.llms.openai import OpenAI
from llama_index.llms.azure_openai import AzureOpenAI
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.huggingface import HuggingFaceLLM

from src.common.logging.logger import DebugLogger
from config.settings import settings

GOOGLE_CREDENTIALS_PATH = settings.GOOGLE_CREDENTIALS_PATH
MODELS_INFO_DICT = settings.models_info.model_dump()
MODELS_SECRETS = settings.models_secrets
DEVICE = settings.system.device
THEME = settings.theme


ModelType = Union[
    "OpenAI", "AzureOpenAI", "Ollama", "GoogleGenAI", "HuggingFaceLLM",
    "OpenAIEmbedding", "AzureOpenAIEmbedding", "HuggingFaceEmbedding", "VertexTextEmbedding", "OllamaEmbedding"
]


class ModelManager:
    """
    Manages the configuration and lazy initialization of LLMs and embedding models
    for OpenAI, Azure OpenAI, and Hugging Face. Reads all configuration parameters
    from environment variables with sensible defaults.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        """
        Override __new__ to implement the singleton pattern.
        Ensures only one instance of ModelManager is ever created
        """
        if cls._instance is None:
            cls._instance = super(ModelManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, logger: DebugLogger = None) -> None:
        # Check if this instance has already been initialized
        if getattr(self, '_initialized', False):
            return

        self.logger = logger or DebugLogger(class_name=self.__class__.__name__, main_feature="SYSTEM")

        # Load configuration from environment variables
        self.models_configs = MODELS_INFO_DICT["providers"]

        self.azure_deployment_name = MODELS_SECRETS.azure.deployment_name
        self.azure_endpoint = MODELS_SECRETS.azure.endpoint
        self.azure_llm_api_key = MODELS_SECRETS.azure.llm_api_key
        self.azure_llm_api_version = MODELS_SECRETS.azure.llm_api_version
        self.azure_embedding_api_key = MODELS_SECRETS.azure.embedder_api_key
        self.azure_embedding_api_version = MODELS_SECRETS.azure.embedder_api_version

        self.google_project_id = MODELS_SECRETS.google.project_id
        self.google_region_llm = MODELS_SECRETS.google.region_llm
        self.google_region_embedder = MODELS_SECRETS.google.region_embedder

        # Lazily initialized models
        self._google_embed_model = None
        self._openai_embed_model = None
        self._azureopenai_embed_model = None
        self._ollama_embed_model = None
        self._huggingface_embed_model = None

        # Validate critical model variables
        self._validate_model_variables()
        # Mark this instance as initialized
        self._initialized = True


    def get_google_credentials(self):
        credentials = None
        try:
            if os.path.exists(GOOGLE_CREDENTIALS_PATH):
                scopes = ["https://www.googleapis.com/auth/generative-language",
                          "https://www.googleapis.com/auth/cloud-platform"]
                credentials = service_account.Credentials.from_service_account_file(GOOGLE_CREDENTIALS_PATH,
                                                                                    scopes=scopes)
            else:
                self.logger.warning("Google credentials file not found.")
        except:
            self.logger.warning("Error reading Google credentials file.")
        return credentials


    def config_log(self, user: Optional[str]):
        """
        Sets the current user for the current logger and the class name to print.
        :param user: the user
        """
        self.logger.set_user(user)


    def _validate_model_variables(self) -> None:
        """
        Validate that critical model variables are set.
        Logs warnings for missing non-essential variables.
        """
        models_options = ["chat_models", "helper_model", "vision_model", "doc_model"]
        for option in models_options:
            if not MODELS_INFO_DICT.get(option):
                self.logger.warning(f"Model '{option}' is not set in models_info.json for the current theme '{THEME}'.")
            else:
                if isinstance(MODELS_INFO_DICT[option], list):
                    for m in MODELS_INFO_DICT[option]:
                        if not self.models_configs.get(m["provider"]).get(m["custom_name"]):
                            self.logger.warning(f"Model '{m}' has not been registered in models in models_info.json.")
                else:
                    if not self.models_configs.get(MODELS_INFO_DICT[option]["provider"]).get(MODELS_INFO_DICT[option]["custom_name"]):
                        self.logger.warning(f"Model '{m}' has not been registered in models in models_info.json.")


    def google_llm(self,
                   model_name: str,
                   context_window: int,
                   temperature: Optional[float] = None) -> GoogleGenAI:
        """Lazy initialization of the Google LLM."""
        self.logger.info(f"Initializing Google LLM with model: {model_name}")

        google_credentials = self.get_google_credentials()
        if not google_credentials:
            raise Exception("Google credentials file not found. Could not initialize Google llm")

        return GoogleGenAI(
            model=model_name,
            vertexai_config={"project": self.google_project_id,
                             "location": self.google_region_llm,
                             "credentials": google_credentials},
            temperature=temperature if temperature else 0.0,
            max_tokens=65535,
            context_window=context_window
        )


    def openai_llm(self, model_name: str) -> OpenAI:
        """Lazy initialization of the OpenAI LLM."""
        self.logger.info(f"Initializing OpenAI LLM with model: {model_name}")
        return OpenAI(model=model_name)


    def azure_llm(self,
                  model_name: str,
                  max_retries: int = None,
                  temperature: Optional[float] = None,
                  timeout: Optional[int] = None) -> AzureOpenAI:
        """Lazy initialization of the Azure OpenAI LLM."""
        self.logger.info(f"Initializing Azure OpenAI LLM with model: {model_name}")
        return AzureOpenAI(
            deployment_name=model_name,
            api_key=self.azure_llm_api_key,
            azure_endpoint=self.azure_endpoint,
            api_version=self.azure_llm_api_version,
            max_retries=max_retries if max_retries else 0,
            temperature=temperature if temperature else 1.0,
            timeout=timeout if timeout else 360,
        )


    def ollama_llm(self,
                   model_name: str,
                   context_window: int,
                   temperature: Optional[float] = None,
                   timeout: Optional[int] = None
                   ) -> Ollama:
        """Lazy initialization of the Ollama LLM."""
        self.logger.info(f"Initializing Ollama LLM with model: {model_name}")
        return Ollama(
            model=model_name,
            base_url=settings.models_secrets.ollama.base_url,
            request_timeout=float(timeout) if timeout else 360.0,
            temperature=temperature if temperature else 1.0,
            context_window=context_window
        )

    def openrouter_llm(self, model_name: str) -> OpenAI:
        """Create an OpenRouter chat model through its OpenAI-compatible API."""
        config = settings.models_secrets.openrouter
        if not config.api_key:
            raise ValueError("OPENROUTER_API_KEY is required for OpenRouter models.")
        self.logger.info(f"Initializing OpenRouter LLM with model: {model_name}")
        return OpenAI(
            model=model_name,
            api_key=config.api_key,
            api_base=config.api_base,
        )

    def huggingface_llm(
            self,
            model_name: str,
            context_window: int,
            hf_token: Optional[str] = None,
            **kwargs,
    ) -> HuggingFaceLLM:
        """Lazy initialization of the Hugging Face LLM."""
        self.logger.info(f"Initializing HuggingFace LLM with model: {model_name}")
        token = hf_token or os.getenv("HF_TOKEN")

        model_kwargs = kwargs.pop("model_kwargs", {})
        tokenizer_kwargs = kwargs.pop("tokenizer_kwargs", {})

        if token:
            model_kwargs.setdefault("token", token)
            tokenizer_kwargs.setdefault("token", token)

        return HuggingFaceLLM(
            model_name=model_name,
            tokenizer_name=model_name,
            context_window=context_window,
            model_kwargs=model_kwargs,
            tokenizer_kwargs=tokenizer_kwargs,
            device_map=DEVICE,
            **kwargs,  # Keep any existing arguments (device_map, max_new_tokens, etc.)
        )


    def google_embedder(self, model_name: str) -> VertexTextEmbedding:
        if self._google_embed_model is None or self._google_embed_model.model_name != model_name:
            self.logger.info(f"Initializing Google Vertex AI embedding model: {model_name}")
            google_credentials = self.get_google_credentials()
            if not google_credentials:
                raise Exception("Google credentials file not found. Could not initialize Google llm")
            self._google_embed_model = VertexTextEmbedding(model_name=model_name,
                                                            project=self.google_project_id,
                                                           location=self.google_region_embedder,
                                                           credentials=google_credentials)
        return self._google_embed_model


    def openai_embedder(self, model_name: str) -> OpenAIEmbedding:
        if self._openai_embed_model is None or self._openai_embed_model.model_name != model_name:
            self.logger.info(f"Initializing OpenAI embedding model: {model_name}")
            self._openai_embed_model = OpenAIEmbedding(model=model_name)
        return self._openai_embed_model


    def azure_embedder(self, 
                       model_name: str, 
                       embedding_dimensions: int,
                       max_retries: int = None) -> AzureOpenAIEmbedding:
        if self._azureopenai_embed_model is None or self._azureopenai_embed_model.model_name != model_name:
            self.logger.info(f"Initializing Azure OpenAI embedding model: {model_name}")
            self._azureopenai_embed_model = AzureOpenAIEmbedding(
                deployment_name=model_name,
                api_key=self.azure_embedding_api_key,
                azure_endpoint=self.azure_endpoint,
                api_version=self.azure_embedding_api_version,
                max_retries=max_retries if max_retries else 0,
                dimensions=embedding_dimensions
            )
        return self._azureopenai_embed_model


    def ollama_embedder(self, model_name: str) -> OllamaEmbedding:
        """Added missing method for Ollama Embeddings."""
        if self._ollama_embed_model is None or self._ollama_embed_model.model_name != model_name:
            self.logger.info(f"Initializing Ollama embedding model: {model_name}")
            self._ollama_embed_model = OllamaEmbedding(model_name=model_name)
        return self._ollama_embed_model


    def huggingface_embedder(self, model_name: str) -> HuggingFaceEmbedding:
        if self._huggingface_embed_model is None or self._huggingface_embed_model.model_name != model_name:
            self.logger.info(f"Initializing Hugging Face embedding model: {model_name}")
            self._huggingface_embed_model = HuggingFaceEmbedding(model_name=model_name,
                                                                 normalize=True,
                                                                 device=DEVICE,
                                                                 trust_remote_code=True)
        return self._huggingface_embed_model


    def get_model(self, model_data: Dict[str, str], **kwargs) -> ModelType:
        """
        Retrieve the desired model instance (LLM or Embedder).

        :param model_name: The custom name of the model to retrieve.
        :param kwargs: Additional keyword arguments (temperature, timeout, etc).
        :return: The requested model instance.
        """
        custom_name = model_data["custom_name"]
        provider = model_data["provider"]
        self.logger.info(f"Retrieving model: {custom_name}")
        config = self._get_model_config(provider=provider, custom_name=custom_name)

        actual_name = config["actual_model_name"]
        is_embedder = config.get("embedding_dimensions") is not None

        try:
            if is_embedder:
                return self._create_embedder(provider, actual_name, config, **kwargs)
            else:
                return self._create_llm(provider, actual_name, config, **kwargs)
        except ValueError as e:
            self.logger.error(f"Configuration error for {custom_name}: {e}")
            raise


    def _get_model_config(self, provider: str, custom_name: str) -> Dict[str, Any]:
        """Safely retrieves model configuration from the global dictionary."""
        try:
            model_info = self.models_configs[provider][custom_name]
            return model_info
        except KeyError:
            error_msg = f"Model '{custom_name}' not found or improperly configured in models_info.json."
            self.logger.error(error_msg)
            raise ValueError(error_msg)


    def _create_llm(self, provider: str, actual_name: str, config: Dict, **kwargs) -> ModelType:
        """Handles the instantiation logic for LLMs."""
        context_window = config.get("context_window")
        temperature = kwargs.get("temperature")

        if provider == "google":
            return self.google_llm(
                model_name=actual_name,
                context_window=context_window,
                temperature=temperature
            )

        elif provider == "openai":
            return self.openai_llm(actual_name)

        elif provider == "openrouter":
            return self.openrouter_llm(actual_name)

        elif provider == "azure":
            return self.azure_llm(
                model_name=actual_name,
                temperature=temperature,
                max_retries=kwargs.get("max_retries"),
                timeout=kwargs.get("timeout")
            )

        elif provider == "ollama":
            return self.ollama_llm(
                model_name=actual_name,
                context_window=context_window,
                temperature=temperature
            )

        elif provider == "huggingface":
            return self.huggingface_llm(actual_name, context_window)

        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")


    def _create_embedder(self, provider: str, actual_name: str, config: Dict, **kwargs) -> ModelType:
        """Handles the instantiation logic for Embedders."""
        if provider == "google":
            return self.google_embedder(actual_name)

        elif provider == "openai":
            return self.openai_embedder(actual_name)

        elif provider == "azure":
            return self.azure_embedder(
                model_name=actual_name,
                embedding_dimensions=config["embedding_dimensions"],
                max_retries=kwargs.get("max_retries")
            )

        elif provider == "ollama":
            return self.ollama_embedder(actual_name)

        elif provider == "huggingface":
            return self.huggingface_embedder(actual_name)

        else:
            raise ValueError(f"Unsupported Embedder provider: {provider}")