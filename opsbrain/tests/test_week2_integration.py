"""Week 2 HTTP integration through real apps/graphs with controlled backends."""

import json
from functools import lru_cache
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from monitoring import main as monitoring_main
from monitoring.agent import MonitoringAgent, MonitoringClientError
from rag import main as rag_main
from rag.agent import RAGAgent
from rag.retriever import RetrievedChunk

from orchestrator import main
from orchestrator.graph import build_orchestrator_graph
from orchestrator.memory import SessionMemory
from orchestrator.router import AGENT_REGISTRY


class RunbookRetriever:
    config = SimpleNamespace(default_top_k=4)

    def retrieve(self, question, *, top_k=None):
        return [RetrievedChunk(id="1", source="alerts.md", score=0.95,
                               content="For active alerts, inspect the alert and follow the runbook procedure.")]

    def build_context(self, chunks):
        return "\n".join(chunk.content for chunk in chunks)


class AppTransport(httpx.AsyncBaseTransport):
    def __init__(self):
        self.calls = []
        self.apps = {
            httpx.URL(AGENT_REGISTRY["rag"].url).host: rag_main.app,
            httpx.URL(AGENT_REGISTRY["monitoring"].url).host: monitoring_main.app,
        }

    async def handle_async_request(self, request):
        self.calls.append((request.url.host, json.loads(request.content)))
        return await httpx.ASGITransport(app=self.apps[request.url.host]).handle_async_request(request)


@pytest.fixture
def integrated_apps(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("AGENT_TRANSPORT", "http")
    rag = RAGAgent(retriever=RunbookRetriever())
    monitoring = MonitoringAgent()
    transport = AppTransport()
    graph = build_orchestrator_graph(transport=transport)
    monkeypatch.setattr(rag_main, "get_agent", lambda: rag)
    monkeypatch.setattr(monitoring_main, "get_agent", lambda: monitoring)
    monkeypatch.setattr(main, "get_graph", lru_cache(maxsize=1)(lambda: graph))
    monkeypatch.setattr(main, "memory", SessionMemory())
    # Only the external Alertmanager response is injected. Monitoring's actual
    # normalization/formatting and both services' API validation still execute.
    monkeypatch.setattr(monitoring, "_request_json", lambda *args, **kwargs: [{
        "labels": {"alertname": "HighLatency", "severity": "warning"},
        "annotations": {"summary": "Latency is elevated"},
        "status": {"state": "active"},
    }])
    with TestClient(main.app) as client:
        yield client, monitoring, transport


@pytest.mark.parametrize("question,agents,sources", [
    ("Explain the alerts runbook procedure", ["rag", "monitoring"], ["alerts.md", "alertmanager:alerts"]),
    ("Are alerts active?", ["monitoring"], ["alertmanager:alerts"]),
    ("Explain the runbook procedure", ["rag"], ["alerts.md"]),
])
def test_real_agent_apps_route_and_preserve_answers(integrated_apps, question, agents, sources):
    client, _, transport = integrated_apps
    response = client.post("/ask", json={"question": question, "session_id": "week2"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["routing"]["agents"] == agents
    assert [result["agent"] for result in body["results"]] == agents
    assert body["sources"] == sources
    assert all(result["status"] == "ok" for result in body["results"])
    assert len(transport.calls) == len(agents)
    assert {payload["request_id"] for _, payload in transport.calls} == {body["request_id"]}
    assert {payload["question"] for _, payload in transport.calls} == {question}
    assert main.memory.history("week2")[-1]["content"] == body["answer"]
    if "rag" in agents:
        result = next(result for result in body["results"] if result["agent"] == "rag")
        assert result["data"]["grounded"] is True
        assert "[alerts.md]" in body["answer"]
    if "monitoring" in agents:
        assert "HighLatency" in body["answer"]
    if len(agents) == 1:
        assert body["answer"] == body["results"][0]["answer"]


def test_real_monitoring_outage_keeps_rag_evidence_and_retries_once(integrated_apps):
    client, monitoring, transport = integrated_apps
    with patch.object(monitoring, "_request_json", side_effect=MonitoringClientError("backend unavailable")):
        response = client.post("/ask", json={"question": "Explain the alerts runbook procedure"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "partial"
    assert body["sources"] == ["alerts.md"]
    assert body["results"][1]["error"]["code"] == "unavailable"
    assert "[alerts.md]" in body["answer"] and "monitoring (unavailable)" in body["answer"]
    monitoring_host = httpx.URL(AGENT_REGISTRY["monitoring"].url).host
    assert sum(host == monitoring_host for host, _ in transport.calls) == 2


def test_real_monitoring_only_outage_is_502_and_is_not_remembered(integrated_apps):
    client, monitoring, _ = integrated_apps
    with patch.object(monitoring, "_request_json", side_effect=MonitoringClientError("backend unavailable")):
        response = client.post("/ask", json={"question": "Are alerts active?", "session_id": "failed"})
    assert response.status_code == 502
    assert response.json()["status"] == "error"
    assert response.json()["sources"] == []
    assert main.memory.history("failed") == []
