"""Timeout and failure handling for the Infra and Code agents (OPU-62).

Every backend failure must surface as a non-2xx /query response whose status
tells the Orchestrator whether to retry (503) or not (4xx / 500) — never as a
200 with the error text as the answer. See orchestrator/CONTRACT.md.
"""

from __future__ import annotations

import asyncio
import io
import subprocess
import time
import unittest
from email.message import Message
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import httpx
from botocore.exceptions import ClientError, NoCredentialsError
from fastapi.testclient import TestClient
from kubernetes.client.exceptions import ApiException
from moto import mock_aws
from urllib3.exceptions import MaxRetryError

from agents.code import main as code_main
from agents.code.agent import CodeAgent, CodeClientError, CodeConfig
from agents.infra import main as infra_main
from agents.infra.agent import InfraAgent, InfraClientError, InfraConfig
from orchestrator.graph import build_orchestrator_graph


def boto_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, "DescribeInstances")


def infra_agent(**overrides) -> InfraAgent:
    return InfraAgent(InfraConfig(aws_region="us-east-1", timeout_seconds=7, **overrides))


class InfraTimeoutTests(unittest.TestCase):
    def test_aws_clients_are_bounded_by_timeout_seconds(self) -> None:
        with mock_aws():
            client = infra_agent()._aws_client("ec2")
        self.assertEqual(client.meta.config.read_timeout, 7)
        self.assertEqual(client.meta.config.connect_timeout, 5)
        self.assertEqual(client.meta.config.retries["total_max_attempts"], 2)

    def test_kubernetes_calls_pass_request_timeout(self) -> None:
        api = MagicMock()
        api.list_node.return_value.items = []
        with patch("agents.infra.agent.k8s_client.CoreV1Api", return_value=api):
            agent = infra_agent()
            agent._k8s_loaded = True
            agent.list_nodes()
        api.list_node.assert_called_once_with(_request_timeout=7)

    def test_health_summary_checks_run_concurrently(self) -> None:
        agent = infra_agent()
        slow = lambda: time.sleep(0.3) or {}
        names = ["summarize_ec2", "list_eks_clusters", "list_rds_instances", "list_nodes", "get_pod_health", "list_deployments"]
        with patch.multiple(agent, **dict.fromkeys(names, slow)):
            started = time.monotonic()
            summary = agent.get_health_summary()
        self.assertLess(time.monotonic() - started, 1.0, "six 0.3s checks should overlap, not take 1.8s")
        self.assertEqual(summary["overall"], "healthy")

    def test_terraform_timeout_is_retryable(self) -> None:
        agent = infra_agent()
        with patch.object(agent, "_terraform_available", return_value=True), \
             patch("agents.infra.agent.subprocess.run", side_effect=subprocess.TimeoutExpired("terraform", 7)):
            with self.assertRaises(InfraClientError) as ctx:
                agent.get_terraform_plan_summary()
        self.assertEqual(ctx.exception.status_code, 503)


class InfraErrorStatusTests(unittest.TestCase):
    def assert_status(self, exc: Exception, method: str, expected: int) -> None:
        agent = infra_agent()
        client = MagicMock()
        getattr(client, method).side_effect = exc
        with patch.object(agent, "_aws_client", return_value=client), self.assertRaises(InfraClientError) as ctx:
            agent.list_ec2_instances() if method == "describe_instances" else agent.list_rds_instances()
        self.assertEqual(ctx.exception.status_code, expected)

    def test_aws_error_statuses(self) -> None:
        self.assert_status(NoCredentialsError(), "describe_instances", 500)
        self.assert_status(boto_error("UnauthorizedOperation"), "describe_instances", 500)
        self.assert_status(boto_error("Throttling"), "describe_instances", 503)
        self.assert_status(boto_error("InternalError"), "describe_db_instances", 503)

    def test_unreachable_cluster_is_retryable(self) -> None:
        api = MagicMock()
        api.list_pod_for_all_namespaces.side_effect = MaxRetryError(None, "/api/v1/pods", "connection refused")
        with patch("agents.infra.agent.k8s_client.CoreV1Api", return_value=api):
            agent = infra_agent()
            agent._k8s_loaded = True
            with self.assertRaises(InfraClientError) as ctx:
                agent.get_pod_health()
        self.assertEqual(ctx.exception.status_code, 503)

    def test_forbidden_cluster_is_config_error(self) -> None:
        api = MagicMock()
        api.list_node.side_effect = ApiException(status=403, reason="Forbidden")
        with patch("agents.infra.agent.k8s_client.CoreV1Api", return_value=api):
            agent = infra_agent()
            agent._k8s_loaded = True
            with self.assertRaises(InfraClientError) as ctx:
                agent.list_nodes()
        self.assertEqual(ctx.exception.status_code, 500)

    def test_missing_kubeconfig_is_config_error(self) -> None:
        with self.assertRaises(InfraClientError) as ctx:
            infra_agent(kubeconfig_path="/nonexistent/kubeconfig").list_nodes()
        self.assertEqual(ctx.exception.status_code, 500)

    def test_health_question_fails_only_when_every_check_fails(self) -> None:
        agent = infra_agent()
        failing = MagicMock(side_effect=InfraClientError("down"))
        names = ["summarize_ec2", "list_eks_clusters", "list_rds_instances", "list_nodes", "get_pod_health", "list_deployments"]
        with patch.multiple(agent, **dict.fromkeys(names, failing)), self.assertRaises(InfraClientError) as ctx:
            agent.ask("overall health?")
        self.assertEqual(ctx.exception.status_code, 503)

        with patch.multiple(agent, **dict.fromkeys(names[1:], failing), summarize_ec2=lambda: {"total": 0, "region": "us-east-1", "state_breakdown": {}}):
            self.assertIn("degraded", agent.ask("overall health?")["answer"].lower())


class InfraQueryEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(infra_main.app)

    def query(self, agent: InfraAgent, question: str) -> httpx.Response:
        with patch.object(infra_main, "get_agent", return_value=agent):
            return self.client.post("/query", json={"question": question})

    def test_backend_failure_is_not_a_200(self) -> None:
        agent = infra_agent()
        with patch.object(agent, "list_nodes", side_effect=InfraClientError("cluster unreachable")):
            resp = self.query(agent, "list k8s nodes")
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json()["detail"], "cluster unreachable")

    def test_config_failure_is_500(self) -> None:
        resp = self.query(infra_agent(kubeconfig_path="/nonexistent/kubeconfig"), "list k8s nodes")
        self.assertEqual(resp.status_code, 500)


def github_error(code: int, headers: dict[str, str] | None = None) -> HTTPError:
    hdrs = Message()
    for key, value in (headers or {}).items():
        hdrs[key] = value
    return HTTPError("https://api.github.com/x", code, "err", hdrs, io.BytesIO(b'{"message": "err"}'))


class CodeErrorStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = CodeAgent(CodeConfig(github_repo="acme/app", github_token="t", timeout_seconds=3))

    def status_for(self, exc: Exception) -> int:
        with patch("agents.code.agent.urlopen", side_effect=exc), self.assertRaises(CodeClientError) as ctx:
            self.agent.list_commits()
        return ctx.exception.status_code

    def test_github_failures_map_to_statuses(self) -> None:
        self.assertEqual(self.status_for(github_error(404)), 404)
        self.assertEqual(self.status_for(github_error(422)), 400)
        self.assertEqual(self.status_for(github_error(401)), 500)
        self.assertEqual(self.status_for(github_error(403)), 500)
        self.assertEqual(self.status_for(github_error(403, {"x-ratelimit-remaining": "0"})), 503)
        self.assertEqual(self.status_for(github_error(429)), 503)
        self.assertEqual(self.status_for(github_error(502)), 503)
        self.assertEqual(self.status_for(URLError("connection refused")), 503)

    def test_read_timeout_is_caught(self) -> None:
        with patch("agents.code.agent.urlopen", side_effect=TimeoutError("timed out")), \
             self.assertRaises(CodeClientError) as ctx:
            self.agent.list_commits()
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertIn("within 3s", str(ctx.exception))


class CodeQueryEndpointTests(unittest.TestCase):
    def query(self, agent: CodeAgent, question: str) -> httpx.Response:
        with patch.object(code_main, "get_agent", return_value=agent):
            return TestClient(code_main.app).post("/query", json={"question": question})

    def test_missing_repo_is_500_not_a_200_answer(self) -> None:
        resp = self.query(CodeAgent(CodeConfig(github_repo="")), "any open PRs?")
        self.assertEqual(resp.status_code, 500)
        self.assertIn("GITHUB_REPO", resp.json()["detail"])

    def test_unknown_pr_is_404(self) -> None:
        agent = CodeAgent(CodeConfig(github_repo="acme/app", github_token="t"))
        with patch("agents.code.agent.urlopen", side_effect=github_error(404)):
            resp = self.query(agent, "what's the status of PR #999?")
        self.assertEqual(resp.status_code, 404)


class OrchestratorSeesAgentFailuresTests(unittest.TestCase):
    """The real Infra FastAPI app behind the Orchestrator graph, in-process."""

    def ask(self, agent: InfraAgent):
        graph = build_orchestrator_graph(transport=httpx.ASGITransport(app=infra_main.app))
        with patch.object(infra_main, "get_agent", return_value=agent):
            return asyncio.run(graph.ainvoke({"request_id": "r1", "question": "list k8s nodes", "history": [], "results": []}))

    def test_backend_outage_is_reported_as_unavailable(self) -> None:
        agent = infra_agent()
        with patch.object(agent, "list_nodes", side_effect=InfraClientError("cluster unreachable")):
            out = self.ask(agent)
        self.assertEqual(out["status"], "error")
        self.assertEqual(out["results"][0].error.code, "unavailable")
        self.assertNotIn("cluster unreachable", out["final_answer"].split("\n")[0])

    def test_misconfiguration_is_reported_as_agent_error(self) -> None:
        out = self.ask(infra_agent(kubeconfig_path="/nonexistent/kubeconfig"))
        self.assertEqual(out["results"][0].error.code, "agent_error")
        self.assertFalse(out["results"][0].error.retryable)

    def test_success_still_flows_through(self) -> None:
        agent = infra_agent()
        with patch.object(agent, "list_nodes", return_value={"total_nodes": 2, "nodes": [{"name": "a", "ready": True}, {"name": "b", "ready": True}]}):
            out = self.ask(agent)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["sources"], ["kubernetes:nodes"])


if __name__ == "__main__":
    unittest.main()
