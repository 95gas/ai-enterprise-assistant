from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.common.telemetry import configure_fastapi_metrics


def test_fastapi_metrics_expose_request_count_and_route():
    app = FastAPI()
    configure_fastapi_metrics(app, "test-service")

    @app.get("/items/{item_id}")
    async def get_item(item_id: str):
        return {"id": item_id}

    with TestClient(app) as client:
        assert client.get("/items/123").status_code == 200
        metrics = client.get("/metrics")

    assert metrics.status_code == 200
    request_metric = next(
        line
        for line in metrics.text.splitlines()
        if line.startswith("http_server_requests_total{")
    )
    assert 'service="test-service"' in request_metric
    assert 'method="GET"' in request_metric
    assert 'route="/items/{item_id}"' in request_metric
    assert 'status="200"' in request_metric
    assert request_metric.endswith(" 1.0")
    assert "http_server_request_duration_seconds_bucket" in metrics.text
