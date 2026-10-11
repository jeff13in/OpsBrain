"""Tests for shared metrics and safe request labels."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.observability import instrument_app


def test_metrics_endpoint_exports_bounded_route_labels() -> None:
    app = FastAPI()
    instrument_app(app, "test-service")

    @app.get("/items/{item_id}")
    def item(item_id: str) -> dict[str, str]:
        return {"item_id": item_id}

    client = TestClient(app)
    assert client.get("/items/sensitive-id").status_code == 200
    metrics = client.get("/metrics").text

    assert "opsbrain_http_requests_total" in metrics
    assert 'route="/items/{item_id}"' in metrics
    assert "sensitive-id" not in metrics
