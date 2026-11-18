from pathlib import Path
import os
import yaml
import logging
from multiprocessing import cpu_count
from typing import List, Dict, Any, Optional, Literal, Tuple, Type
from dotenv import load_dotenv
from pydantic_settings import (BaseSettings,
                               SettingsConfigDict,
                               PydanticBaseSettingsSource)
from pydantic import (AliasChoices,
                      model_validator,
                      computed_field,
                      Field,
                      BaseModel,
                      ConfigDict)


def disable_external_loggers():
    """Disable noisy third-party loggers without hiding startup errors."""
    logging.getLogger("neo4j.notifications").disabled = True
    logging.getLogger("werkzeug").disabled = True
    logging.getLogger("httpx").disabled = True


disable_external_loggers()

CONFIG_DIR = Path(__file__).resolve().parent
SECRETS_ENV = CONFIG_DIR / "secrets.env"

# Populate os.environ from secrets.env without overriding explicit environment variables
# (so Docker Compose environment overrides always win).
load_dotenv(SECRETS_ENV, override=False)

ENV_FILES = (SECRETS_ENV,)
PIPELINE_CONFIGS = (
    "system.yaml",
    "chat.yaml",
    "ingestion.yaml",
    "models.yaml",
    "users.yaml",
    "tickets.yaml",
    "microservices.yaml",
    "prompts.yaml",
    "storage.yaml",
)

logger = logging.getLogger(__name__)


# --- System ---
class SingleModelConfig(BaseModel):
    provider: str
    custom_name: str


class ModelsInfoSettings(BaseModel):
    model_config = ConfigDict(extra='allow')
    chat_models: List[SingleModelConfig] = Field(default_factory=list)
    embedder_model: Optional[SingleModelConfig] = None
    helper_model: Optional[SingleModelConfig] = None
    doc_model: Optional[SingleModelConfig] = None
    vision_model: Optional[SingleModelConfig] = None


class DefaultUserValues(BaseModel):
    tot_token_limit: int = 10000
    expiring_date_trial: str = "2100/12/31 00:00:00"
    tot_limit_reset_period: str = "day"


class UserGroupConfig(BaseModel):
    mode: Literal["extend", "substitute"]
    groups: List[str]


class UserPermissionsConfig(BaseModel):
    include: List[str] = Field(description="Can contain user emails or groups, that have access to the feature.")
    exclude: List[str] = Field(description="Can contain user emails or groups, that don't have access to the feature.")


class CredentialsSettings(BaseModel):
    default_values: DefaultUserValues = Field(default_factory=DefaultUserValues)
    groups: Dict[str, UserGroupConfig] = Field(default_factory=dict)
    permissions: Dict[str, UserPermissionsConfig] = Field(default_factory=dict)


class DockerSettings(BaseModel):
    db_name: Optional[str] = Field(None)
    server_name: Optional[str] = Field(None)


class SystemSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore",
                                      case_sensitive=True,
                                      populate_by_name=True,
                                      env_file=ENV_FILES)

    port: Optional[int] = Field(8080, validation_alias=AliasChoices("PORT", "SERVER_PORT"))
    num_workers: Optional[int] = Field(max(1, min((cpu_count() or 1) - 1, 5)), validation_alias="NUM_WORKERS")
    device: Optional[Literal["cpu", "cuda"]] = Field("cpu", validation_alias="DEVICE")
    allowed_origins: List[str] = Field(default_factory=list)

    @model_validator(mode='before')
    @classmethod
    def calculate_system_defaults(cls, data: Any) -> Any:
        if isinstance(data, dict):
            origins_list = data.get("ALLOWED_ORIGINS_LIST")
            if origins_list and isinstance(origins_list, str):
                data['allowed_origins'] = [x.strip() for x in origins_list.split(',')]
            elif "allowed_origins" not in data:
                port = data.get("PORT", data.get("SERVER_PORT", data.get("port", 8080)))
                data["allowed_origins"] = [f"http://localhost:{port}"]
        return data


# --- Databases ---
class S3Settings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore",
        case_sensitive=True,
        env_file=ENV_FILES,
    )

    url: str = Field("http://localhost:8333", validation_alias="S3_URL")
    username: str = Field(
        "ask-local-s3",
        validation_alias=AliasChoices("S3_ACCESS_KEY", "S3_USERNAME"),
    )
    password: str = Field(
        "ask-local-s3-secret",
        validation_alias=AliasChoices("S3_SECRET_KEY", "S3_PASSWORD"),
    )
    structure_config: Path = Field(
        default=CONFIG_DIR / "storage.yaml",
        validation_alias="S3_STRUCTURE_CONFIG",
        description="Path to the S3 folder structure YAML file",
    )


class PostgresSettings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore",
        case_sensitive=True,
        env_file=ENV_FILES,
    )

    database_url: Optional[str] = Field(None, validation_alias="DATABASE_URL")
    host: str = Field("localhost", validation_alias="POSTGRES_HOST")
    port: int = Field(5432, validation_alias="POSTGRES_PORT")
    database: str = Field("ask", validation_alias="POSTGRES_DB")
    username: str = Field("ask", validation_alias="POSTGRES_USER")
    password: str = Field("ask", validation_alias="POSTGRES_PASSWORD")

    @model_validator(mode="before")
    @classmethod
    def prefer_postgres_components(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        component_fields = (
            "host",
            "port",
            "database",
            "username",
            "password",
            "POSTGRES_HOST",
            "POSTGRES_PORT",
            "POSTGRES_DB",
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
        )
        if any(field in data for field in component_fields):
            data.pop("database_url", None)
            data.pop("DATABASE_URL", None)
        return data

    @property
    def url(self) -> str:
        if self.database_url:
            return self.database_url
        from sqlalchemy.engine import URL

        return URL.create(
            "postgresql+psycopg",
            username=self.username,
            password=self.password,
            host=self.host,
            port=self.port,
            database=self.database,
        ).render_as_string(hide_password=False)


class Neo4jSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore",
                                      case_sensitive=True,
                                      env_file=ENV_FILES)
    url: Optional[str] = Field("bolt://localhost:7687", validation_alias="NEO4J_URL")
    username: Optional[str] = Field(None, validation_alias="NEO4J_USERNAME")
    password: Optional[str] = Field(None, validation_alias="NEO4J_PASSWORD")
    database: Optional[str] = Field(None, validation_alias="NEO4J_DATABASE")


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore",
                                      case_sensitive=True,
                                      env_file=ENV_FILES)
    host: str = Field("localhost", validation_alias="REDIS_HOST")
    port: int = Field(6379, validation_alias="REDIS_PORT")
    password: Optional[str] = Field(None, validation_alias="REDIS_PASSWORD")
    db: int = Field(0, validation_alias="REDIS_DB")
    url: Optional[str] = Field(None, validation_alias="REDIS_URL")


# --- Connectors ---
class Connectors(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore",
                                      case_sensitive=True,
                                      env_file=ENV_FILES)
    sharepoint_tenant_id: Optional[str] = Field(None, description="The ID of your tenant (e.g. 'mycompanyname')",
                                                validation_alias="SHAREPOINT_TENANT_ID")
    sharepoint_client_id: Optional[str] = Field(None,
                                                description="The unique client identifier (also known as Application ID) used for authenticating requests to the SharePoint API.",
                                                validation_alias="SHAREPOINT_CLIENT_ID")
    sharepoint_client_secret: Optional[str] = Field(None,
                                                    description="The client secret or password associated with the client application.",
                                                    validation_alias="SHAREPOINT_CLIENT_SECRET")


# --- Microservices ---
class MicroservicesSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore",
                                      case_sensitive=True,
                                      env_file=ENV_FILES)
    secret: Optional[str] = Field("dev-microservices-secret",
                                  description="The secret to authenticate requests between microservices.'",
                                  validation_alias="SECRET")
    task_ttl: int = Field(86400, description="Time-to-live for tasks in seconds.")


# --- Auth and Security ---
class JWTSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore",
                                      case_sensitive=True,
                                      env_file=ENV_FILES)
    algorithm: str = Field("HS256", validation_alias="JWT_ALGORITHM")
    expire_minutes: int = Field(5, validation_alias="JWT_EXPIRE_MINUTES")
    secret: Optional[str] = Field(None, validation_alias="JWT_SECRET")


# --- Models ---
class AzureSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore",
                                      case_sensitive=True,
                                      env_file=ENV_FILES)
    endpoint: Optional[str] = Field(None,
                                    description="The base URL for your Azure OpenAI resource (e.g. 'https://res-name.openai.azure.com/').",
                                    validation_alias="AZURE_ENDPOINT")
    deployment_name: Optional[str] = Field(None,
                                           description="The custom name assigned to your model deployment (e.g. 'gpt-4-model').",
                                           validation_alias="AZURE_DEPLOYMENT_NAME")
    llm_api_version: Optional[str] = Field(None,
                                           description="The API version for chat completions (e.g. '2024-02-15-preview').",
                                           validation_alias="AZURE_CHAT_API_VERSION")
    llm_api_key: Optional[str] = Field(None, description="The secret API key for your Azure OpenAI resource.",
                                       validation_alias="AZURE_CHAT_API_KEY")
    embedder_api_version: Optional[str] = Field(None,
                                                description="The API version for the embedding model (e.g. '2023-05-15').",
                                                validation_alias="AZURE_EMBEDDING_API_VERSION")
    embedder_api_key: Optional[str] = Field(None, description="The secret API key for your Azure Embedding resource.",
                                            validation_alias="AZURE_EMBEDDING_API_KEY")


class GoogleSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore",
                                      case_sensitive=True,
                                      env_file=ENV_FILES)
    project_id: Optional[str] = Field(None, description="The GCP Project ID (e.g. 'my-awesome-ai-project').",
                                      validation_alias="GOOGLE_PROJECT_ID")
    region_llm: Optional[str] = Field(None, description="The GCP region for LLM services (e.g. 'us-east4').",
                                      validation_alias="GOOGLE_REGION_LLM")
    region_embedder: Optional[str] = Field(None,
                                           description="The GCP region for embedding services (e.g. 'us-central1').",
                                           validation_alias="GOOGLE_REGION_EMBEDDER")


class OpenAISettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore",
                                      case_sensitive=True,
                                      env_file=ENV_FILES)
    api_key: Optional[str] = Field(None, description="The standard OpenAI API secret key (e.g. 'sk-proj-xyz...').",
                                   validation_alias="OPENAI_API_KEY")


class OllamaSettings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore",
        case_sensitive=True,
        env_file=ENV_FILES,
    )
    base_url: str = Field(
        "http://localhost:11434",
        validation_alias="OLLAMA_BASE_URL",
    )


class OpenRouterSettings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore",
        case_sensitive=True,
        env_file=ENV_FILES,
    )
    api_key: Optional[str] = Field(None, validation_alias="OPENROUTER_API_KEY")
    api_base: str = Field(
        "https://openrouter.ai/api/v1",
        validation_alias="OPENROUTER_API_BASE",
    )
    site_url: Optional[str] = Field(None, validation_alias="OPENROUTER_SITE_URL")
    app_name: Optional[str] = Field(None, validation_alias="OPENROUTER_APP_NAME")


class HuggingFaceSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore",
                                      case_sensitive=True,
                                      env_file=ENV_FILES)
    api_token: Optional[str] = Field(
        None,
        description="The Hugging Face Hub User Access Token.",
        validation_alias=AliasChoices("HUGGINGFACE_API_TOKEN", "HUGGINGFACEHUB_API_TOKEN"),
    )


class ModelsSettings(BaseSettings):
    azure: Optional[AzureSettings] = Field(default_factory=AzureSettings)
    google: Optional[GoogleSettings] = Field(default_factory=GoogleSettings)
    openai: Optional[OpenAISettings] = Field(default_factory=OpenAISettings)
    ollama: Optional[OllamaSettings] = Field(default_factory=OllamaSettings)
    openrouter: Optional[OpenRouterSettings] = Field(default_factory=OpenRouterSettings)
    huggingface: Optional[HuggingFaceSettings] = Field(default_factory=HuggingFaceSettings)


class YamlConfigSource(PydanticBaseSettingsSource):
    """Loads top-level Settings values from focused YAML pipeline files."""

    def get_field_value(self, field: Any, field_name: str) -> Tuple[Any, str, bool]:
        return None, field_name, False

    @staticmethod
    def _merge(target: Dict[str, Any], source: Dict[str, Any]) -> None:
        for key, value in source.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                YamlConfigSource._merge(target[key], value)
            else:
                target[key] = value

    def __call__(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        for filename in PIPELINE_CONFIGS:
            path = CONFIG_DIR / filename
            if not path.exists():
                continue
            try:
                content = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError as exc:
                raise ValueError(f"Invalid YAML configuration in {path}: {exc}") from exc
            if not isinstance(content, dict):
                raise ValueError(f"Configuration file {path} must contain a YAML mapping.")
            self._merge(data, content)
        return data


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore",
                                      case_sensitive=True,
                                      populate_by_name=True,
                                      env_file=ENV_FILES)

    theme: str = Field("mirai", validation_alias="THEME")

    system: SystemSettings = Field(default_factory=SystemSettings)
    docker: DockerSettings = Field(default_factory=DockerSettings)
    postgres: PostgresSettings = Field(default_factory=PostgresSettings)
    neo4j: Neo4jSettings = Field(default_factory=Neo4jSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    jwt: JWTSettings = Field(default_factory=JWTSettings)
    s3: S3Settings = Field(default_factory=S3Settings)

    connectors: Connectors = Field(default_factory=Connectors)

    microservices: MicroservicesSettings = Field(default_factory=MicroservicesSettings)
    models_secrets: ModelsSettings = Field(default_factory=ModelsSettings)

    CHAT_HISTORY_BUFFER_SIZE: int = 8192
    CHAT_NOTES_MAX_SIZE: int = 4096
    CHUNK_SIZE: int = 256
    CHUNK_OVERLAP: int = 0
    DATE_FORMAT: str = "%Y/%m/%d %H:%M:%S"
    MAX_PRIVATE_DOCS_PER_USER: int = 10
    storage_path: Optional[Path] = Field(None, validation_alias="STORAGE_PATH")

    # --- Pipeline configuration loaded from YAML ---
    credentials: CredentialsSettings = Field(default_factory=CredentialsSettings)
    models_info: ModelsInfoSettings = Field(default_factory=ModelsInfoSettings)
    prompts_keys: Dict[str, str] = Field(default_factory=dict)
    step_streaming: Dict[str, Dict[str, str]] = Field(default_factory=dict)
    ticket_structure: Dict[str, Any] = Field(default_factory=dict)

    @computed_field
    def STORAGE_PATH(self) -> Path:
        configured_path = os.getenv("STORAGE_PATH")
        if configured_path:
            return Path(configured_path)
        if self.storage_path:
            return self.storage_path
        return Path.home() / "ask_storage" / "docs"

    @computed_field
    def STORAGE_TEMP_DOCS(self) -> Path:
        return self.STORAGE_PATH.parent / "temp"

    @computed_field
    def STORAGE_FAILED_DOCS(self) -> Path:
        return self.STORAGE_PATH.parent / "failed"

    @computed_field
    def STORAGE_MARKDOWN(self) -> Path:
        return self.STORAGE_PATH.parent / "markdowns"

    @computed_field
    def STORAGE_CHATS(self) -> Path:
        return self.STORAGE_PATH.parent / "chats"

    @computed_field
    def STORAGE_WIKI(self) -> Path:
        return self.STORAGE_PATH.parent / "wiki"

    @computed_field
    def SECRET_KEY_PATH(self) -> Path:
        return CONFIG_DIR / "secret_key.txt"

    @computed_field
    def GOOGLE_CREDENTIALS_PATH(self) -> Path:
        configured_path = os.getenv("GOOGLE_CREDENTIALS_PATH")
        return Path(configured_path) if configured_path else CONFIG_DIR / "google_credentials.json"

    @computed_field
    def DEFAULT_PROMPTS_PATH(self) -> Path:
        return CONFIG_DIR / "prompts" / "default"

    @computed_field
    def THEME_PROMPTS_PATH(self) -> Path:
        return CONFIG_DIR / "prompts" / self.theme

    @classmethod
    def settings_customise_sources(
            cls,
            settings_cls: Type[BaseSettings],
            init_settings: PydanticBaseSettingsSource,
            env_settings: PydanticBaseSettingsSource,
            dotenv_settings: PydanticBaseSettingsSource,
            file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,  # 1. Arguments passed to constructor
            env_settings,  # 2. Environment Variables
            dotenv_settings,  # 3. .env files
            YamlConfigSource(settings_cls),
        )


try:
    settings = Settings()
    logger.info(f"Loaded configuration for Theme: {settings.theme}")
    logger.info(f"Active Port: {settings.system.port} | Workers: {settings.system.num_workers}")

except Exception as e:
    logger.exception("Failed to load configuration")
    raise