"""Unit tests for the Orchestrator contract (OPU-42): routing, normalization, aggregation.

The graph wiring itself is covered in test_orchestrator_graph.py.
"""

from __future__ import annotations

import unittest

import httpx

from orchestrator.contract import (
    error_from_exception,
    fallback_answer,
    merge_sources,
    overall_status,
    result_from_error,
    result_from_reply,
)
from orchestrator.router import route
from shared.models import AgentError, AgentResult


def _ok(agent: str, answer: str, sources: list[str]) -> AgentResult:
    return AgentResult(agent=agent, status="ok", answer=answer, sources=sources)


def _failed(agent: str, code: str = "unavailable") -> AgentResult:
    return result_from_error(agent, AgentError(code=code, message="x", retryable=True))


class RoutingTests(unittest.TestCase):
    def test_unmatched_question_falls_back_to_rag(self) -> None:
        decision = route("What is the meaning of life?")
        self.assertEqual(decision.agents, ["rag"])
        self.assertEqual(decision.method, "fallback")

    def test_routes_to_every_matching_agent_in_registry_order(self) -> None:
        decision = route("Did the CI pipeline break the EKS pods, and are alerts firing?")
        self.assertEqual(decision.agents, ["monitoring", "infra", "code"])
        self.assertEqual(decision.method, "keyword")

    def test_keywords_match_whole_words_only(self) -> None:
        # "pr" must not match inside "prometheus" / "production"
        self.assertNotIn("code", route("Is prometheus scraping production?").agents)


class NormalizationTests(unittest.TestCase):
    def test_rag_extras_are_kept_in_data(self) -> None:
        body = {"answer": "Restart it.", "sources": ["runbook-high-cpu.md"], "grounded": True, "retrieved_chunks": 3}
        result = result_from_reply("rag", body, latency_ms=12)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.sources, ["runbook-high-cpu.md"])
        self.assertEqual(result.data, {"grounded": True, "retrieved_chunks": 3})

    def test_infra_data_field_passes_through(self) -> None:
        result = result_from_reply("infra", {"answer": "2 nodes", "sources": ["kubernetes:nodes"], "data": {"total_nodes": 2}})
        self.assertEqual(result.data, {"total_nodes": 2})

    def test_reply_without_answer_is_invalid_response(self) -> None:
        result = result_from_reply("code", {"sources": []})
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error.code, "invalid_response")

    def test_http_errors_map_to_contract_codes(self) -> None:
        request = httpx.Request("POST", "http://agent/query")

        def status_error(code: int) -> httpx.HTTPStatusError:
            return httpx.HTTPStatusError("x", request=request, response=httpx.Response(code, request=request))

        self.assertEqual(error_from_exception(httpx.ReadTimeout("x")).code, "timeout")
        self.assertEqual(error_from_exception(httpx.ConnectError("x")).code, "unavailable")
        self.assertEqual(error_from_exception(status_error(503)).code, "unavailable")
        self.assertEqual(error_from_exception(status_error(422)).code, "bad_request")
        self.assertEqual(error_from_exception(status_error(500)).code, "agent_error")
        self.assertTrue(error_from_exception(httpx.ReadTimeout("x")).retryable)
        self.assertFalse(error_from_exception(status_error(422)).retryable)

    def test_timeout_error_gives_timeout_status(self) -> None:
        self.assertEqual(_failed("rag", "timeout").status, "timeout")


class AggregationTests(unittest.TestCase):
    def test_overall_status(self) -> None:
        self.assertEqual(overall_status([_ok("rag", "a", [])]), "ok")
        self.assertEqual(overall_status([_ok("rag", "a", []), _failed("infra")]), "partial")
        self.assertEqual(overall_status([_failed("rag")]), "error")
        self.assertEqual(overall_status([]), "error")

    def test_sources_merged_in_order_without_duplicates_or_failed_agents(self) -> None:
        results = [_ok("rag", "a", ["r1", "shared"]), _failed("monitoring"), _ok("infra", "b", ["shared", "i1"])]
        self.assertEqual(merge_sources(results), ["r1", "shared", "i1"])

    def test_single_agent_answer_is_returned_verbatim(self) -> None:
        self.assertEqual(fallback_answer([_ok("rag", "Restart it.", [])]), "Restart it.")

    def test_partial_answer_names_missing_agents(self) -> None:
        answer = fallback_answer([_ok("rag", "Restart it.", []), _failed("infra", "timeout")])
        self.assertIn("[rag] Restart it.", answer)
        self.assertIn("infra (timeout)", answer)


if __name__ == "__main__":
    unittest.main()
