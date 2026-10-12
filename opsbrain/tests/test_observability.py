"""Tests for shared metrics and safe request labels."""

import asyncio

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from orchestrator.graph import call_agent
from shared.models import AgentQuery
from shared.observability import AGENT_FAILURES, instrument_app


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


@pytest.mark.parametrize("status,body,code", [
    (404, {"detail": "not found"}, "bad_request"),
    (503, {"detail": "offline"}, "unavailable"),
    (200, {"sources": []}, "invalid_response"),
])
def test_failures_count_once_per_final_result_with_contract_code(status, body, code):
    counter = AGENT_FAILURES.labels("code", code)
    before = counter._value.get()
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(status, json=body)

    result = asyncio.run(call_agent("code", AgentQuery(question="check commits", request_id="metrics"),
                                   httpx.MockTransport(handle)))
    assert result.error.code == code
    assert counter._value.get() == before + 1
    assert len(calls) == (2 if status == 503 else 1)
