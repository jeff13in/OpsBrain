"""Tests for the Orchestrator graph and /ask endpoint (OPU-43).

Agents are faked with httpx.MockTransport and the LLM with a stub, so these
run offline. Live multi-agent runs against docker compose are OPU-51.
"""

from __future__ import annotations

import asyncio
import json
import unittest
from types import SimpleNamespace

import httpx
from fastapi.testclient import TestClient

from orchestrator import main
from orchestrator.graph import build_orchestrator_graph
from orchestrator.memory import SessionMemory
from orchestrator.router import AGENT_REGISTRY

AGENT_BY_HOST = {httpx.URL(spec.url).host: name for name, spec in AGENT_REGISTRY.items()}


def agent_transport(replies: dict, calls: list | None = None, delay: float = 0.0) -> httpx.MockTransport:
    """Fake agents. replies[agent] is a dict body, an int status, an exception, or a list of those (one per attempt)."""
    attempts: dict[str, int] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        agent = AGENT_BY_HOST[request.url.host]
        if calls is not None:
            calls.append((agent, json.loads(request.content)))
        if delay:
            await asyncio.sleep(delay)
        reply = replies[agent]
        if isinstance(reply, list):
            reply = reply[min(attempts.get(agent, 0), len(reply) - 1)]
            attempts[agent] = attempts.get(agent, 0) + 1
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, int):
            return httpx.Response(reply, json={"detail": "boom"})
        return httpx.Response(200, json=reply)

    return httpx.MockTransport(handler)


class FakeLLM:
    """Answers router prompts with `route_reply` and synthesis prompts with `synth_reply`."""

    def __init__(self, route_reply: str, synth_reply: str = "merged answer") -> None:
        self.route_reply = route_reply
        self.synth_reply = synth_reply
        self.prompts: list[str] = []

    async def ainvoke(self, messages):
        system, human = messages[0].content, messages[1].content
        self.prompts.append(human)
        if "route DevOps questions" in system:
            return SimpleNamespace(content=self.route_reply)
        return SimpleNamespace(content=self.synth_reply)


def run(graph, question: str, history: list | None = None) -> dict:
    return asyncio.run(graph.ainvoke({"request_id": "r1", "question": question, "history": history or [], "results": []}))


def ok(answer: str, sources: list[str]) -> dict:
    return {"answer": answer, "sources": sources}


class FanOutTests(unittest.TestCase):
    def test_calls_routed_agents_in_parallel_and_merges(self) -> None:
        in_flight, peak = 0, 0

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0.05)
            in_flight -= 1
            agent = AGENT_BY_HOST[request.url.host]
            return httpx.Response(200, json=ok(f"{agent} says hi", [f"{agent}:src", "shared"]))

        graph = build_orchestrator_graph(transport=httpx.MockTransport(handler))
        out = run(graph, "Are alerts firing on the EKS pods?")

        self.assertEqual(peak, 2, "both agents should be in flight at once")
        self.assertEqual(out["routing"].agents, ["monitoring", "infra"])
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["sources"], ["monitoring:src", "shared", "infra:src"])
        self.assertIn("[monitoring] monitoring says hi", out["final_answer"])

    def test_agents_receive_contract_query(self) -> None:
        calls: list = []
        graph = build_orchestrator_graph(transport=agent_transport({"rag": ok("a", [])}, calls))
        run(graph, "How do I rotate the database password?")
        self.assertEqual(calls, [("rag", {"question": "How do I rotate the database password?", "request_id": "r1"})])

    def test_single_agent_answer_is_verbatim(self) -> None:
        graph = build_orchestrator_graph(transport=agent_transport({"rag": ok("Restart it.", ["r.md"])}))
        self.assertEqual(run(graph, "What now?")["final_answer"], "Restart it.")


class FailureTests(unittest.TestCase):
    def test_one_failed_agent_gives_partial(self) -> None:
        graph = build_orchestrator_graph(transport=agent_transport({"monitoring": ok("2 alerts", ["m"]), "infra": 500}))
        out = run(graph, "Are alerts firing on the EKS pods?")
        self.assertEqual(out["status"], "partial")
        self.assertEqual(out["sources"], ["m"])
        self.assertIn("infra (agent_error)", out["final_answer"])

    def test_unavailable_is_retried_once(self) -> None:
        calls: list = []
        graph = build_orchestrator_graph(transport=agent_transport({"rag": [503, ok("second try", [])]}, calls))
        out = run(graph, "anything")
        self.assertEqual(len(calls), 2)
        self.assertEqual(out["final_answer"], "second try")

    def test_bad_request_and_timeout_are_not_retried(self) -> None:
        for reply, expected_status in ((422, "error"), (httpx.ReadTimeout("slow"), "timeout")):
            calls: list = []
            graph = build_orchestrator_graph(transport=agent_transport({"rag": reply}, calls))
            out = run(graph, "anything")
            self.assertEqual(len(calls), 1)
            self.assertEqual(out["results"][0].status, expected_status)
            self.assertEqual(out["status"], "error")

    def test_non_json_body_is_invalid_response(self) -> None:
        transport = httpx.MockTransport(lambda request: httpx.Response(200, text="<html>oops</html>"))
        out = run(build_orchestrator_graph(transport=transport), "anything")
        self.assertEqual(out["results"][0].error.code, "invalid_response")


class LLMTests(unittest.TestCase):
    def test_llm_routes_and_rewrites_follow_up(self) -> None:
        calls: list = []
        llm = FakeLLM('```json\n{"agents": ["code", "infra"], "standalone_question": "Did PR #42 break the api pods?", "reason": "r"}\n```')
        graph = build_orchestrator_graph(llm=llm, transport=agent_transport({"infra": ok("pods ok", []), "code": ok("PR green", [])}, calls))

        out = run(graph, "did it break them?", history=[{"role": "user", "content": "check PR #42"}])

        self.assertEqual(out["routing"].method, "llm")
        self.assertEqual(out["routing"].agents, ["infra", "code"])  # registry order
        self.assertEqual({c[1]["question"] for c in calls}, {"Did PR #42 break the api pods?"})
        self.assertIn("check PR #42", llm.prompts[0])
        self.assertEqual(out["final_answer"], "merged answer")  # 2 successes → LLM synthesis

    def test_bad_llm_routing_falls_back_to_keywords(self) -> None:
        for reply in ("not json", '{"agents": []}', '{"agents": ["slack"]}'):
            graph = build_orchestrator_graph(llm=FakeLLM(reply), transport=agent_transport({"monitoring": ok("a", [])}))
            out = run(graph, "Any alerts firing?")
            self.assertEqual(out["routing"].method, "keyword", reply)

    def test_synthesis_failure_uses_fallback_answer(self) -> None:
        class FailingSynth(FakeLLM):
            async def ainvoke(self, messages):
                if "route DevOps questions" in messages[0].content:
                    return await super().ainvoke(messages)
                raise RuntimeError("quota")

        llm = FailingSynth('{"agents": ["rag", "infra"], "standalone_question": "q"}')
        graph = build_orchestrator_graph(llm=llm, transport=agent_transport({"rag": ok("A", []), "infra": ok("B", [])}))
        self.assertEqual(run(graph, "q")["final_answer"], "[rag] A\n\n[infra] B")


class AskEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original = (main.get_graph, main.memory)
        main.memory = SessionMemory()
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        main.get_graph, main.memory = self.original

    def use(self, graph) -> None:
        main.get_graph = lambda: graph

    def test_success_returns_200_ask_response(self) -> None:
        self.use(build_orchestrator_graph(transport=agent_transport({"rag": ok("Restart it.", ["r.md"])})))
        resp = self.client.post("/ask", json={"question": "What now?"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["answer"], "Restart it.")
        self.assertEqual(body["results"][0]["agent"], "rag")

    def test_all_agents_failing_returns_502_with_same_shape(self) -> None:
        self.use(build_orchestrator_graph(transport=agent_transport({"rag": httpx.ConnectError("down")})))
        resp = self.client.post("/ask", json={"question": "What now?"})
        self.assertEqual(resp.status_code, 502)
        self.assertEqual(resp.json()["status"], "error")
        self.assertEqual(resp.json()["results"][0]["error"]["code"], "unavailable")

    def test_session_history_is_passed_to_next_turn(self) -> None:
        llm = FakeLLM('{"agents": ["rag"], "standalone_question": "q"}')
        self.use(build_orchestrator_graph(llm=llm, transport=agent_transport({"rag": ok("use kubectl", [])})))
        self.client.post("/ask", json={"question": "how do I restart api?", "session_id": "s1"})
        self.client.post("/ask", json={"question": "and the worker?", "session_id": "s1"})
        self.assertIn("how do I restart api?", llm.prompts[-1])
        self.assertIn("use kubectl", llm.prompts[-1])


class SessionMemoryTests(unittest.TestCase):
    def test_keeps_only_recent_turns_and_sessions(self) -> None:
        mem = SessionMemory(max_turns=2, max_sessions=2)
        for i in range(3):
            mem.append("a", f"q{i}", f"a{i}")
        self.assertEqual([t["content"] for t in mem.history("a")], ["q1", "a1", "q2", "a2"])
        mem.append("b", "q", "a")
        mem.append("c", "q", "a")
        self.assertEqual(mem.history("a"), [])  # evicted as least recently used
        self.assertEqual(mem.history(None), [])

    def test_expired_sessions_are_forgotten(self) -> None:
        mem = SessionMemory(ttl_s=0)
        mem.append("a", "q", "a")
        self.assertEqual(mem.history("a"), [])


if __name__ == "__main__":
    unittest.main()
