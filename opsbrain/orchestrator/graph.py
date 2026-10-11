"""Orchestrator LangGraph state machine (OPU-43).

  route       — pick agents (LLM classifier, keyword fallback) and rewrite
                follow-ups into a standalone question
  call_agent  — one parallel branch per routed agent (LangGraph Send);
                each branch appends exactly one AgentResult
  synthesise  — status, merged sources, and one answer
  END

Rules for every step are in orchestrator/CONTRACT.md.
"""

from __future__ import annotations

import operator
import time
from typing import Annotated, Any, TypedDict

import httpx
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from orchestrator import llm as llm_ops
from orchestrator.contract import (
    error_from_exception,
    fallback_answer,
    merge_sources,
    overall_status,
    result_from_error,
    result_from_reply,
)
from orchestrator.router import AGENT_REGISTRY, route
from shared.models import (
    AgentName,
    AgentQuery,
    AgentResult,
    OverallStatus,
    RoutingDecision,
)
from shared.observability import AGENT_DURATION, AGENT_EXECUTIONS


class OrchestratorState(TypedDict, total=False):
    """State carried through one /ask request (contract: orchestrator/CONTRACT.md).

    `results` uses an append reducer so parallel agent branches can each
    contribute their AgentResult without overwriting one another.
    """
    request_id: str
    session_id: str | None
    question: str
    history: list[dict[str, str]]          # prior turns: {"role": "user"|"assistant", "content": ...}
    agent_question: str                    # standalone rewrite of `question` sent to agents
    routing: RoutingDecision
    results: Annotated[list[AgentResult], operator.add]
    status: OverallStatus
    final_answer: str
    sources: list[str]


class AgentCall(TypedDict):
    """Payload of one Send() branch."""
    agent: AgentName
    question: str
    request_id: str


async def call_agent(
    agent: AgentName,
    query: AgentQuery,
    transport: httpx.AsyncBaseTransport | None = None,
) -> AgentResult:
    """POST to one agent's /query and normalize the outcome. Never raises.

    Retryable non-timeout failures (agent unreachable / 503) get one retry;
    a timeout already consumed the agent's whole budget, so it isn't retried.
    """
    spec = AGENT_REGISTRY[agent]
    started = time.monotonic()
    async with httpx.AsyncClient(timeout=spec.timeout_s, transport=transport) as client:
        for attempt in (1, 2):
            try:
                resp = await client.post(f"{spec.url}{spec.query_path}", json=query.model_dump())
                resp.raise_for_status()
            except Exception as exc:  # noqa: BLE001 - every failure becomes an AgentResult
                error = error_from_exception(exc)
                if attempt == 1 and error.retryable and error.code != "timeout":
                    continue
                result = result_from_error(agent, error, _elapsed_ms(started))
                _observe_agent_result(agent, result.status, started)
                return result
            try:
                body = resp.json()
            except ValueError:
                body = None  # 2xx with a non-JSON body → invalid_response
            result = result_from_reply(agent, body, _elapsed_ms(started))
            _observe_agent_result(agent, result.status, started)
            return result
    raise AssertionError("unreachable")  # pragma: no cover


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _observe_agent_result(agent: AgentName, status: str, started: float) -> None:
    AGENT_EXECUTIONS.labels(agent, status).inc()
    AGENT_DURATION.labels(agent).observe(time.monotonic() - started)


def build_orchestrator_graph(llm: Any | None = None, transport: httpx.AsyncBaseTransport | None = None):
    """Compile the graph. `llm` and `transport` are injectable for tests."""

    async def route_node(state: OrchestratorState) -> OrchestratorState:
        question = state["question"]
        if llm is not None:
            classified = await llm_ops.classify(llm, question, state.get("history", []))
            if classified is not None:
                decision, standalone = classified
                return {"routing": decision, "agent_question": standalone}
        return {"routing": route(question), "agent_question": question}

    def fan_out(state: OrchestratorState) -> list[Send]:
        return [
            Send("call_agent", AgentCall(agent=name, question=state["agent_question"], request_id=state["request_id"]))
            for name in state["routing"].agents
        ]

    async def call_agent_node(call: AgentCall) -> OrchestratorState:
        query = AgentQuery(question=call["question"], request_id=call["request_id"])
        return {"results": [await call_agent(call["agent"], query, transport)]}

    async def synthesise_node(state: OrchestratorState) -> OrchestratorState:
        # Branches finish in any order; report results in routing order.
        order = {name: i for i, name in enumerate(state["routing"].agents)}
        results = sorted(state.get("results", []), key=lambda r: order.get(r.agent, len(order)))
        ok = [r for r in results if r.status == "ok"]

        answer = None
        if llm is not None and len(ok) >= 2:
            answer = await llm_ops.synthesise(llm, state["agent_question"], results)
        return {
            "status": overall_status(results),
            "final_answer": answer or fallback_answer(results),
            "sources": merge_sources(results),
        }

    graph = StateGraph(OrchestratorState)
    graph.add_node("route",      route_node)
    graph.add_node("call_agent", call_agent_node)
    graph.add_node("synthesise", synthesise_node)
    graph.add_edge(START,        "route")
    graph.add_conditional_edges("route", fan_out, ["call_agent"])
    graph.add_edge("call_agent", "synthesise")
    graph.add_edge("synthesise", END)
    return graph.compile()
