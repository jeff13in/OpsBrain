"""Orchestrator contract rules — OPU-42.

Pure functions that turn raw agent HTTP outcomes into AgentResult and fold
several AgentResults into one AskResponse. The graph (OPU-43) calls these;
nothing here does I/O, so every rule is unit-testable.
"""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import ValidationError

from shared.models import (
    AgentError,
    AgentName,
    AgentReply,
    AgentResult,
    OverallStatus,
)

# Keys of an agent reply that AgentResult carries as first-class fields;
# anything else the agent returned is preserved under `data`.
_REPLY_FIELDS = {"answer", "sources", "data"}


def result_from_reply(agent: AgentName, body: Any, latency_ms: int = 0) -> AgentResult:
    """Normalize a 2xx agent body into an AgentResult (or an invalid_response error)."""
    try:
        reply = AgentReply.model_validate(body)
    except ValidationError as exc:
        return result_from_error(
            agent,
            AgentError(code="invalid_response", message=f"Reply did not match AgentReply: {exc.error_count()} error(s)", retryable=False),
            latency_ms,
        )

    extras = {k: v for k, v in body.items() if k not in _REPLY_FIELDS}
    data = {**(reply.data or {}), **extras} or None
    return AgentResult(
        agent=agent,
        status="ok",
        answer=reply.answer,
        sources=reply.sources,
        data=data,
        latency_ms=latency_ms,
    )


def error_from_exception(exc: Exception) -> AgentError:
    """Map an httpx failure onto the contract's error codes."""
    if isinstance(exc, httpx.TimeoutException):
        return AgentError(code="timeout", message="Agent did not respond before the deadline.", retryable=True)
    if isinstance(exc, httpx.HTTPStatusError):
        return error_from_status(exc.response.status_code, exc.response.text)
    if isinstance(exc, httpx.TransportError):
        return AgentError(code="unavailable", message=f"Could not reach agent: {exc.__class__.__name__}", retryable=True)
    return AgentError(code="agent_error", message=f"Unexpected error calling agent: {exc.__class__.__name__}", retryable=False)


def error_from_status(status_code: int, detail: str = "") -> AgentError:
    if status_code == 503:
        return AgentError(code="unavailable", message=detail or "Agent dependency unavailable.", retryable=True)
    if 400 <= status_code < 500:
        return AgentError(code="bad_request", message=detail or f"Agent rejected the request ({status_code}).", retryable=False)
    return AgentError(code="agent_error", message=detail or f"Agent failed ({status_code}).", retryable=False)


def result_from_error(agent: AgentName, error: AgentError, latency_ms: int = 0) -> AgentResult:
    return AgentResult(
        agent=agent,
        status="timeout" if error.code == "timeout" else "error",
        error=error,
        latency_ms=latency_ms,
    )


def overall_status(results: list[AgentResult]) -> OverallStatus:
    ok = sum(r.status == "ok" for r in results)
    if results and ok == len(results):
        return "ok"
    return "partial" if ok else "error"


def merge_sources(results: list[AgentResult]) -> list[str]:
    """Sources of successful agents, in routing order, de-duplicated."""
    seen: dict[str, None] = {}
    for r in results:
        if r.status == "ok":
            seen.update(dict.fromkeys(r.sources))
    return list(seen)


def fallback_answer(results: list[AgentResult]) -> str:
    """Deterministic answer used when there is one result or LLM synthesis fails.

    One successful agent → its answer verbatim. Several → one labelled section
    each. Failed agents are listed at the end so a partial answer says what's missing.
    """
    ok = [r for r in results if r.status == "ok"]
    failed = [r for r in results if r.status != "ok"]

    if len(ok) == 1 and not failed:
        return ok[0].answer or ""

    parts = [f"[{r.agent}] {r.answer}" for r in ok]
    if failed:
        parts.append("Unavailable: " + ", ".join(f"{r.agent} ({r.error.code})" for r in failed if r.error))
    if not ok:
        parts.insert(0, "No agent was able to answer this question.")
    return "\n\n".join(parts)
