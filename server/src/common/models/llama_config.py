from llama_index.core import Settings

from src.common.models.manager import ModelManager
from src.common.logging.logger import DebugLogger
from config.settings import settings as conf_settings

MODELS_INFO_DICT = conf_settings.models_info.model_dump()


class \
        LIConfig:
    def __init__(self):
        """
        Initializes the LlamaIndexConfigurator by setting up embedding and LLM models
        from environment variables and logging the configuration.
        """
        self.logger = DebugLogger(class_name=self.__class__.__name__, main_feature="SYSTEM")
        self.logger.info("Setting llama index up...")
        self.model_manager = ModelManager()

        self.llm_name = MODELS_INFO_DICT["chat_models"][0]
        self.embed_model_name = MODELS_INFO_DICT["embedder_model"]

        # Validate and configure
        self._validate_env_vars()
        self._configure_settings()

        self.logger.success("LlamaIndex is ready.")

    def _validate_env_vars(self) -> None:
        """
        Validates that the required environment variables are set.
        """
        missing_vars = []
        if not self.llm_name:
            missing_vars.append("chat_models")
        if not self.embed_model_name:
            missing_vars.append("embedder_model")

        if missing_vars:
            raise EnvironmentError(
                f"The following environment variables are not set: {', '.join(missing_vars)}"
            )

    def _configure_settings(self) -> None:
        """
        Configures the LlamaIndex settings for embedding and LLM models.
        """
        try:
            Settings.llm = self.model_manager.get_model(self.llm_name)
            Settings.embed_model = self.model_manager.get_model(self.embed_model_name)

            # Log configuration details
            self.logger.info(f"Configured LLM provider as '{self.llm_name}'")
            self.logger.info(f"Configured query embedding provider as '{self.embed_model_name}'")
        except Exception as e:
            self.logger.error("Error configuring LlamaIndex settings", exc_info=True)
            raise