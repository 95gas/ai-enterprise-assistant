import pytest

pytest.importorskip("temporalio")

from src.services.chat.temporal import temporal_enabled
from src.services.temporal.workflows import (
    DocumentIngestionWorkflow,
    DocumentBatchDeleteWorkflow,
    DocumentExtractionWorkflow,
    ALL_WORKFLOWS,
)
from src.services.temporal.client import TemporalMicroserviceClient


def test_redis_settings_configuration():
    pytest.importorskip("presidio_analyzer")
    pytest.importorskip("presidio_anonymizer")
    from config.settings import settings

    assert hasattr(settings, "redis")
    assert settings.redis.port == 6379
    assert settings.redis.host is not None
    assert settings.redis.db == 0


def test_temporal_workflows_and_client_definitions(monkeypatch):
    monkeypatch.setenv("TEMPORAL_ENABLED", "true")
    assert temporal_enabled() is True

    assert DocumentIngestionWorkflow in ALL_WORKFLOWS
    assert DocumentBatchDeleteWorkflow in ALL_WORKFLOWS
    assert DocumentExtractionWorkflow in ALL_WORKFLOWS

    client = TemporalMicroserviceClient(target="localhost:7233", task_queue="test-queue")
    assert client.target == "localhost:7233"
    assert client.task_queue == "test-queue"


def test_temporal_disabled_by_default(monkeypatch):
    monkeypatch.delenv("TEMPORAL_ENABLED", raising=False)
    client = TemporalMicroserviceClient()
    # Should raise error if attempted to get client when disabled
    with pytest.raises(RuntimeError, match="Temporal orchestration is disabled"):
        import asyncio
        asyncio.run(client._get_client())
