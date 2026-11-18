import os
from pathlib import Path

from config.settings import CONFIG_DIR, PostgresSettings, Settings, settings
from src.utils.env_loader import EnvLoader


def test_pipeline_yaml_files_populate_typed_settings():
    assert settings.theme == "mirai"
    assert settings.system.port == 8080
    assert settings.system.allowed_origins == [
        "http://localhost:5173",
        "http://172.26.255.2:5173",
        "http://172.26.255.3:5173",
    ]
    assert settings.CHUNK_SIZE == 256
    assert settings.CHUNK_OVERLAP == 0
    assert settings.s3.structure_config == CONFIG_DIR / "storage.yaml"
    assert settings.STORAGE_PATH == Path.home() / "ask_storage" / "docs"
    assert settings.credentials.default_values.tot_token_limit == 10000
    assert settings.ticket_structure["type"] == ["Incident", "Service", "Change"]
    models = settings.models_info
    assert models.chat_models[0].provider == "huggingface"
    assert models.providers["huggingface"]["demo_chat"]["actual_model_name"] == "google/gemma-3-270m-it"
    assert models.embedder_model.provider == "huggingface"
    assert models.providers["huggingface"]["demo_embedder"]["embedding_dimensions"] == 384
    assert settings.s3.url == "http://localhost:8333"


def test_environment_values_override_pipeline_yaml(monkeypatch):
    monkeypatch.setenv("DEVICE", "cpu")
    monkeypatch.setenv("STORAGE_PATH", "custom-docs")
    monkeypatch.setenv("S3_URL", "http://s3.example.test:8333")

    configured = Settings()

    assert configured.system.device == "cpu"
    assert configured.STORAGE_PATH == Path("custom-docs")
    assert configured.s3.url == "http://s3.example.test:8333"


def test_postgres_components_override_legacy_database_url(tmp_path):
    env_file = tmp_path / "secrets.env"
    env_file.write_text(
        "DATABASE_URL=postgresql+psycopg://old:old@localhost:5432/old\n"
        "POSTGRES_HOST=localhost\n"
        "POSTGRES_PORT=5433\n"
        "POSTGRES_DB=demo\n"
        "POSTGRES_USER=demo\n"
        "POSTGRES_PASSWORD=demo\n",
        encoding="utf-8",
    )

    configured = PostgresSettings(_env_file=env_file)

    assert configured.url == "postgresql+psycopg://demo:demo@localhost:5433/demo"


def test_legacy_database_url_is_supported_without_shared_postgres_values(tmp_path):
    legacy_env = tmp_path / "legacy.env"
    legacy_env.write_text(
        "DATABASE_URL=postgresql+psycopg://old:old@db.example.test:5432/old\n",
        encoding="utf-8",
    )

    configured = PostgresSettings(_env_file=legacy_env)

    assert configured.url == "postgresql+psycopg://old:old@db.example.test:5432/old"


def test_env_loader_loads_configured_environment_file(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "secrets.env").write_text(
        "POSTGRES_USER=demo\nOPENAI_API_KEY=local-key\n",
        encoding="utf-8",
    )
    for key in ("POSTGRES_USER", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    loader = EnvLoader(config_dir)
    loader.load_env_files()

    assert os.environ["POSTGRES_USER"] == "demo"
    assert os.environ["OPENAI_API_KEY"] == "local-key"
