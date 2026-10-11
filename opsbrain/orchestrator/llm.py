"""LLM-backed routing and synthesis for the Orchestrator (OPU-43).

Both functions are best-effort: they return None on any failure and the
graph falls back to the deterministic rules in router.py / contract.py.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any

from orchestrator.router import AGENT_REGISTRY
from shared.models import AgentResult, RoutingDecision

try:
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError:  # pragma: no cover - orchestrator still works on keyword routing
    HumanMessage = SystemMessage = ChatGoogleGenerativeAI = None

logger = logging.getLogger(__name__)

# Hard limits on each Gemini call. Past them, routing falls back to keywords and
# synthesis to fallback_answer(). Without them a rate-limited key (the free tier
# allows 5 requests/min) makes the client retry 429s for over a minute (OPU-51).
ROUTE_TIMEOUT_S = float(os.getenv("ORCHESTRATOR_ROUTE_TIMEOUT_SECONDS", "10"))
SYNTH_TIMEOUT_S = float(os.getenv("ORCHESTRATOR_SYNTH_TIMEOUT_SECONDS", "20"))

ROUTER_PROMPT = """You route DevOps questions to specialist agents.

Agents:
{agents}

Reply with JSON only, no prose:
{{"agents": ["<name>", ...], "standalone_question": "<question>", "reason": "<short reason>"}}

- Pick every agent needed to answer; pick "rag" if unsure.
- standalone_question: the user's latest question rewritten so it makes sense
  without the conversation (resolve "it", "that pod", etc.). Unchanged if already standalone."""

SYNTH_PROMPT = """You are OpsBrain. Several specialist agents answered parts of the user's question.
Combine their answers into one concise reply. Use only what the agents said; don't invent facts.
Keep source citations in square brackets. If some agents were unavailable, say what is missing."""


def get_llm() -> Any | None:
    if ChatGoogleGenerativeAI is None or not os.getenv("GOOGLE_API_KEY"):
        return None
    # max_output_tokens leaves room for the "thinking" model's hidden reasoning
    # (see memory.md — unset, it can return empty content).
    return ChatGoogleGenerativeAI(
        model=os.getenv("GOOGLE_CHAT_MODEL", "gemini-3.6-flash"),
        temperature=0,
        max_output_tokens=4096,
        max_retries=1,  # the per-call timeouts below are the real bound
    )


def _text(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, list):
        return " ".join(str(part.get("text", part)) if isinstance(part, dict) else str(part) for part in content).strip()
    return str(content).strip()


def _format_history(history: list[dict[str, str]]) -> str:
    return "\n".join(f"{turn['role']}: {turn['content']}" for turn in history)


def _parse_json(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.DOTALL)  # tolerate ```json fences
    if not match:
        raise ValueError("no JSON object in router reply")
    return json.loads(match.group(0))


async def classify(llm: Any, question: str, history: list[dict[str, str]]) -> tuple[RoutingDecision, str] | None:
    """Return (routing decision, standalone question), or None to fall back to keywords."""
    agents = "\n".join(f"- {name}: {spec.description}" for name, spec in AGENT_REGISTRY.items())
    prompt = f"Conversation so far:\n{_format_history(history)}\n\n" if history else ""
    prompt += f"Latest question:\n{question}"
    try:
        reply = await asyncio.wait_for(
            llm.ainvoke([SystemMessage(content=ROUTER_PROMPT.format(agents=agents)), HumanMessage(content=prompt)]),
            timeout=ROUTE_TIMEOUT_S,
        )
        parsed = _parse_json(_text(reply))
        names = [a for a in AGENT_REGISTRY if a in parsed.get("agents", [])]  # registry order, unknown names dropped
        decision = RoutingDecision(agents=names, method="llm", reason=str(parsed.get("reason", ""))[:300])
        standalone = str(parsed.get("standalone_question") or question).strip()[:2000]
        return decision, standalone
    except Exception as exc:  # noqa: BLE001 - any LLM/parse failure means "use keywords"
        logger.warning("LLM routing failed, falling back to keywords: %s", exc.__class__.__name__)
        return None


async def synthesise(llm: Any, question: str, results: list[AgentResult]) -> str | None:
    """Merge several agent answers into one, or None to use the deterministic fallback."""
    sections = []
    for r in results:
        if r.status == "ok":
            sections.append(f"[{r.agent}] {r.answer}\nSources: {', '.join(r.sources) or 'none'}")
        else:
            sections.append(f"[{r.agent}] UNAVAILABLE ({r.error.code if r.error else r.status})")
    try:
        reply = await asyncio.wait_for(
            llm.ainvoke([
                SystemMessage(content=SYNTH_PROMPT),
                HumanMessage(content=f"Question:\n{question}\n\nAgent answers:\n\n" + "\n\n".join(sections)),
            ]),
            timeout=SYNTH_TIMEOUT_S,
        )
        return _text(reply) or None
    except Exception as exc:  # noqa: BLE001 - any LLM failure means "use fallback_answer"
        logger.warning("LLM synthesis failed, using fallback answer: %s", exc.__class__.__name__)
        return None
