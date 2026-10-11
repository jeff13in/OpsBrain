"""Monitoring /query adapter and error contract; no external backends."""
import unittest
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


def test_default_alert_answer_keeps_counts_names_and_data():
    agent = MonitoringAgent()
    alerts = {
        "total": 3, "active": 2, "suppressed": 1,
        "severity_breakdown": {"critical": 2, "warning": 1},
        "top_alerts": [{"alertname": "HighCPU", "count": 2}],
    }
    with patch.object(agent, "summarize_alerts", return_value=alerts):
        reply = agent.ask("Is anything firing?")
    assert reply["sources"] == ["alertmanager:alerts"]
    assert "2 active and 1 suppressed" in reply["answer"]
    assert "HighCPU (2)" in reply["answer"]
    assert reply["data"] == {"alerts": alerts}


def test_pod_answer_names_degraded_pods():
    agent = MonitoringAgent()
    pods = {
        "total_pods": 2, "status_breakdown": {"healthy": 1, "degraded": 1},
        "pods": [{"pod": "api-1", "status": "healthy"}, {"pod": "worker-1", "status": "degraded"}],
    }
    with patch.object(agent, "get_pod_health", return_value=pods):
        reply = agent.ask("Are any pods restarting?")
    assert reply["sources"] == ["prometheus:kube_pod_status"]
    assert "Needing attention: worker-1" in reply["answer"]


def test_down_answer_names_scrape_targets():
    agent = MonitoringAgent()
    with patch.object(agent, "query_prometheus", return_value={"result": [
        {"metric": {"job": "prometheus", "instance": "localhost:9090"}, "value": [0, "1"]},
        {"metric": {"job": "rag-agent", "instance": "rag-agent:8001"}, "value": [0, "0"]},
    ]}):
        reply = agent.ask("Which targets are down?")
    assert reply["data"]["targets"]["down"] == 1
    assert "rag-agent (rag-agent:8001)" in reply["answer"]


def test_empty_alert_summary_has_no_alerts_answer():
    agent = MonitoringAgent()
    with patch.object(agent, "summarize_alerts", return_value={"total": 0}):
        assert agent.ask("status?")["answer"] == "No alerts in Alertmanager."


# ── ask() topic selection (OPU-51: answer every topic the question mentions) ──

ALERTS = {
    "total": 3, "active": 2, "suppressed": 1,
    "severity_breakdown": {"critical": 2, "warning": 1},
    "state_breakdown": {"active": 2, "suppressed": 1},
    "top_alerts": [{"alertname": "HighCPU", "count": 2}, {"alertname": "PodCrashLooping", "count": 1}],
}
PODS = {
    "namespace": None, "total_pods": 2, "status_breakdown": {"healthy": 1, "degraded": 1},
    "pods": [{"pod": "api-1", "status": "healthy"}, {"pod": "worker-1", "status": "degraded"}],
}
UP = {"result": [
    {"metric": {"job": "prometheus", "instance": "localhost:9090"}, "value": [0, "1"]},
    {"metric": {"job": "rag-agent", "instance": "rag-agent:8001"}, "value": [0, "0"]},
]}


class AskTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = MonitoringAgent()

    def test_alerts_are_the_default(self) -> None:
        with patch.object(self.agent, "summarize_alerts", return_value=ALERTS):
            reply = self.agent.ask("Is anything firing?")

        self.assertEqual(reply["sources"], ["alertmanager:alerts"])
        self.assertIn("2 active and 1 suppressed", reply["answer"])
        self.assertIn("HighCPU (2)", reply["answer"])
        self.assertEqual(reply["data"], {"alerts": ALERTS})

    def test_pod_questions_use_pod_health(self) -> None:
        with patch.object(self.agent, "get_pod_health", return_value=PODS):
            reply = self.agent.ask("Are any pods restarting?")

        self.assertEqual(reply["sources"], ["prometheus:kube_pod_status"])
        self.assertIn("Needing attention: worker-1", reply["answer"])

    def test_down_questions_use_scrape_targets(self) -> None:
        with patch.object(self.agent, "query_prometheus", return_value=UP):
            reply = self.agent.ask("Which targets are down?")

        self.assertEqual(reply["data"]["targets"]["down"], 1)
        self.assertIn("rag-agent (rag-agent:8001)", reply["answer"])

    def test_answers_every_topic_the_question_mentions(self) -> None:
        with patch.object(self.agent, "summarize_alerts", return_value=ALERTS), \
             patch.object(self.agent, "get_pod_health", return_value=PODS):
            reply = self.agent.ask("Which alerts are firing, and are any pods crashlooping?")

        self.assertEqual(reply["sources"], ["alertmanager:alerts", "prometheus:kube_pod_status"])
        self.assertIn("2 active", reply["answer"])
        self.assertIn("worker-1", reply["answer"])
        self.assertEqual(set(reply["data"]), {"alerts", "pods"})

    def test_one_backend_down_is_reported_in_the_answer(self) -> None:
        with patch.object(self.agent, "summarize_alerts", return_value=ALERTS), \
             patch.object(self.agent, "get_pod_health", side_effect=MonitoringClientError("Prometheus unreachable")):
            reply = self.agent.ask("alerts and pods?")

        self.assertEqual(reply["sources"], ["alertmanager:alerts"])
        self.assertIn("Couldn't check pods: Prometheus unreachable", reply["answer"])

    def test_every_backend_down_raises(self) -> None:
        with patch.object(self.agent, "get_pod_health", side_effect=MonitoringClientError("Prometheus unreachable")), \
             self.assertRaises(MonitoringClientError):
            self.agent.ask("any pods restarting?")

    def test_no_alerts(self) -> None:
        empty = {**ALERTS, "total": 0, "active": 0, "suppressed": 0, "severity_breakdown": {}, "top_alerts": []}
        with patch.object(self.agent, "summarize_alerts", return_value=empty):
            self.assertEqual(self.agent.ask("status?")["answer"], "No alerts in Alertmanager.")
