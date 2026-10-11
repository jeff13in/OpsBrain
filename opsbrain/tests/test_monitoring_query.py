"""Tests for the Monitoring agent's Orchestrator entry point: ask() and POST /query (OPU-50)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from monitoring import main
from monitoring.agent import MonitoringAgent, MonitoringClientError

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


class QueryEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main.app)

    def test_returns_agent_reply_shape(self) -> None:
        with patch.object(main.get_agent(), "summarize_alerts", return_value=ALERTS):
            resp = self.client.post("/query", json={"question": "alerts?", "request_id": "r1"})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(set(resp.json()), {"answer", "sources", "data"})

    def test_backend_down_is_503_not_an_answer(self) -> None:
        with patch.object(main.get_agent(), "summarize_alerts", side_effect=MonitoringClientError("Alertmanager unreachable")):
            resp = self.client.post("/query", json={"question": "alerts?", "request_id": "r1"})

        self.assertEqual(resp.status_code, 503)
        self.assertIn("Alertmanager unreachable", resp.json()["detail"])


if __name__ == "__main__":
    unittest.main()
