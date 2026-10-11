"""Monitoring /query adapter and error contract; no external backends."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from monitoring import main
from monitoring.agent import MonitoringAgent, MonitoringClientError


@pytest.mark.parametrize("question,method,payload,source", [
    ("Are alerts firing?", "summarize_alerts", {"total": 0}, "alertmanager:alerts"),
    ("Which pod is restarting?", "get_pod_health", {"total_pods": 0}, "prometheus:kube_pod_status"),
    ("Are scrape targets down?", "get_scrape_targets", {"total": 0}, "prometheus:up"),
])
def test_monitoring_query_returns_agent_contract(question, method, payload, source):
    agent = MonitoringAgent()
    with patch.object(agent, method, return_value=payload), patch.object(main, "get_agent", return_value=agent):
        reply = TestClient(main.app).post("/query", json={"question": question, "request_id": "r1"})
    assert reply.status_code == 200
    assert reply.json()["answer"] and reply.json()["sources"] == [source]


def test_monitoring_failure_is_503_not_successful_error_text():
    with patch.object(MonitoringAgent, "ask", side_effect=MonitoringClientError("backend unavailable")):
        reply = TestClient(main.app).post("/query", json={"question": "alerts"})
    assert reply.status_code == 503


def test_monitoring_query_validates_input_and_preserves_metrics():
    client = TestClient(main.app)
    assert client.post("/query", json={"question": ""}).status_code == 422
    assert client.get("/metrics").status_code == 200


def test_scrape_target_aggregation():
    agent = MonitoringAgent()
    with patch.object(agent, "query_prometheus", return_value={"result": [
        {"metric": {"job": "api", "instance": "api:8000"}, "value": [0, "1"]},
        {"metric": {"job": "db", "instance": "db:5432"}, "value": [0, "0"]},
    ]}):
        result = agent.get_scrape_targets()
    assert result["total"] == 2 and result["down"] == 1
