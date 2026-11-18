"""Unified token counting for configured hosted and local LLM providers."""

import abc
import os

import tiktoken
from typing import Optional
import google.generativeai as genai
from src.common.logging.logger import DebugLogger

class TokenizerStrategy(abc.ABC):
    """
    Abstract base class for tokenizer strategies.
    Defines the common interface for all tokenizers.
    """
    def __init__(self):
        self.logger = DebugLogger(class_name=self.__class__.__name__, main_feature="SYSTEM")
        self.encoding = lambda x: ""

    def get_encoding(self):
        return self.encoding

    @abc.abstractmethod
    def count_tokens(self, text: str) -> int:
        """
        Counts the number of tokens in the given text.

        :param text: The input string to tokenize.
        :return: The number of tokens as an integer.
        """
        pass


class OpenAITokenizer(TokenizerStrategy):
    """
    Tokenizer for OpenAI models using the 'tiktoken' library.
    """

    def __init__(self,
                 model_name: str = "gpt-4",
                 logger: DebugLogger = DebugLogger()):
        """
        Initializes the OpenAITokenizer.

        :param model_name: The OpenAI model name to use for encoding.
        """
        super().__init__()
        self.logger = logger
        self.model_name = model_name
        self.logger.info(f"Initialized OpenAITokenizer for model: {self.model_name}")
        try:
            self.encoding = tiktoken.encoding_for_model(self.model_name).encode
        except KeyError:
            self.encoding = tiktoken.get_encoding("cl100k_base").encode

    def count_tokens(self, text: str) -> int:
        """
        Counts tokens using the selected tiktoken encoding.

        :param text: The input string to tokenize.
        :return: The number of tokens as an integer.
        """
        return len(self.encoding(text))


class GoogleTokenizer(TokenizerStrategy):
    """
    Tokenizer for Google's Gemini models.
    """

    def __init__(self, model_name: str = "gemini-pro", api_key: str = None, logger: DebugLogger = DebugLogger()):
        """
        Initializes the GoogleTokenizer.

        :param model_name: The Google Gemini model name.
        :param api_key: The Google AI API key.
        """
        super().__init__()
        self.logger = logger
        api_key = api_key or os.environ.get("GOOGLE_API_TOKENIZER")
        if api_key is None:
            self.logger.error("Google API missing for google tokenizer!.")
            raise ValueError("Google API missing for google tokenizer!.")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)
        self.encoding = lambda x: self.model.count_tokens(x).total_tokens * "a"
        self.logger.info(f"Initialized Google tokenizer for model: {model_name}")

    def count_tokens(self, text: str) -> int:
        """
        Counts tokens by calling the Google AI API.

        :param text: The input string to tokenize.
        :return: The number of tokens.
        """
        try:
            response = self.model.count_tokens(text)
            return response.total_tokens
        except Exception as e:
            raise e


class OllamaTokenizer(TokenizerStrategy):
    """
    Tokenizer for models served by an Ollama instance.
    """

    def __init__(self, model_name: str, host: str = "http://localhost:11434", logger: DebugLogger = DebugLogger()):
        """
        Initializes the OllamaTokenizer.

        :param model_name: The name of the model served by Ollama.
        :param host: The URL of the Ollama server.
        """
        super().__init__()
        self.logger = logger
        self.model_name = model_name
        self.encoding = lambda x: int(len(x) / 4) * "a"
        self.logger.info(f"Initialized Ollama tokenizer for model '{model_name}'")

    def count_tokens(self, text: str) -> int:
        """
        Counts tokens by the 4-character rule.

        :param text: The input string to tokenize.
        :return: The number of tokens
        """
        return len(self.encoding(text))


class HuggingFaceTokenizer(TokenizerStrategy):
    """Token counter backed by the configured local Hugging Face tokenizer."""

    def __init__(self, model_name: str, logger: Optional[DebugLogger] = None):
        super().__init__()
        self.logger = logger or self.logger
        from transformers import AutoTokenizer

        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.encoding = self.tokenizer.encode
        self.logger.info(f"Initialized Hugging Face tokenizer for model '{model_name}'")

    def count_tokens(self, text: str) -> int:
        return len(self.tokenizer.encode(text))


class TokenCounter:
    """
    A facade class to simplify token counting for different LLM providers.
    """
    # Class-level dictionary to store instances
    _instances = {}

    def __new__(cls, provider: str, model_name: str, logger: Optional[DebugLogger] = None, **kwargs):
        """
        Override __new__ to control instance creation.
        """
        provider_low = provider.lower()
        key_parts = [provider_low, model_name]

        if provider_low == "google":
            key_parts.append(kwargs.get("api_key") or os.environ.get("GOOGLE_API_TOKENIZER"))
        elif provider_low == "ollama":
            key_parts.append(kwargs.get("host"))

        instance_key = tuple(key_parts)

        if instance_key not in cls._instances:
            # If instance doesn't exist, create a new one
            instance = super().__new__(cls)
            cls._instances[instance_key] = instance
            # Add a flag to indicate __init__ needs to run
            instance._initialized = False

        return cls._instances[instance_key]

    def __init__(self, provider: str, model_name: str, logger: Optional[DebugLogger]=None, **kwargs):
        """
        Initializes the TokenCounter with a specific provider and model.

        :param provider: The configured LLM provider.
        :param model_name: The name of the model to use for tokenization.
        :param kwargs: Additional keyword arguments for specific tokenizers,
                       e.g., `api_key` for 'google' or `host` for 'ollama'.
        """
        # Check if this instance has already been initialized
        if getattr(self, '_initialized', False):
            return

        self.logger = logger or DebugLogger(class_name=self.__class__.__name__, main_feature="SYSTEM")
        self.logger.set_class_name(self.__class__.__name__)
        self.provider = provider.lower()
        self.model_name = model_name
        self.tokenizer = self._get_tokenizer(**kwargs)

        self._initialized = True

    def get_encoding(self):
        return self.tokenizer.encoding

    def _get_tokenizer(self, **kwargs) -> TokenizerStrategy:
        """
        Factory method to create the appropriate tokenizer strategy.

        :param kwargs: Keyword arguments passed from the constructor.
        :return: An instance of a TokenizerStrategy subclass.
        """
        if self.provider in {"openai", "openrouter", "azure"}:
            return OpenAITokenizer(model_name=self.model_name,
                                   logger=self.logger)
        elif self.provider == "google":
            api_key = kwargs.get("api_key")
            return GoogleTokenizer(model_name=self.model_name,
                                   api_key=api_key,
                                   logger=self.logger)
        elif self.provider == "ollama":
            host = kwargs.get("host")
            return OllamaTokenizer(model_name=self.model_name,
                                   host=host,
                                   logger=self.logger) if host else OllamaTokenizer(model_name=self.model_name,
                                                                                    logger=self.logger)
        elif self.provider == "huggingface":
            from config.settings import settings

            model_config = settings.models_info.model_dump()["providers"].get("huggingface", {}).get(
                self.model_name
            )
            if model_config is not None:
                try:
                    model_name = model_config["actual_model_name"]
                except KeyError as exc:
                    raise ValueError(
                        f"Hugging Face model '{self.model_name}' has no actual_model_name configured."
                    ) from exc
            else:
                model_name = self.model_name
            return HuggingFaceTokenizer(model_name=model_name, logger=self.logger)
        else:
            raise ValueError(f"Unsupported provider: '{self.provider}'. "
                             "Choose a provider supported by the model configuration.")

    def count(self, text: str) -> int:
        """
        Counts the tokens in the text using the configured tokenizer.

        :param text: The string to count tokens for.
        :return: The number of tokens as an integer.
        """
        if not isinstance(text, str):
            raise TypeError("Input text must be a string.")
        return self.tokenizer.count_tokens(text)