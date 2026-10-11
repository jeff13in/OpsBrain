"""LLM-backed routing and synthesis for the Orchestrator (OPU-43).

Both functions are best-effort: they return None on any failure and the
graph falls back to the deterministic rules in router.py / contract.py.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from orchestrator.router import AGENT_REGISTRY
from shared.llm import ChatConfigurationError, ChatRole, get_chat_model
from shared.models import AgentName, AgentResult, RoutingDecision

ROUTING_TIMEOUT_SECONDS = 10.0
SYNTHESIS_TIMEOUT_SECONDS = 20.0

logger = logging.getLogger(__name__)

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


def get_llm(role: ChatRole = "router") -> Any | None:
    """Resolve one chat role; missing configuration enables existing fallbacks."""
    try:
        return get_chat_model(role)
    except ChatConfigurationError:
        logger.warning("Chat configuration unavailable for %s; using deterministic fallback.", role)
        return None


class RouterReply(BaseModel):
    agents: list[AgentName] = Field(min_length=1)
    standalone_question: str | None = Field(default=None, min_length=1, max_length=2000)
    reason: str = ""


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
        async with asyncio.timeout(ROUTING_TIMEOUT_SECONDS):
            reply = await llm.ainvoke([SystemMessage(content=ROUTER_PROMPT.format(agents=agents)), HumanMessage(content=prompt)])
        parsed = RouterReply.model_validate(_parse_json(_text(reply)))
        names = [a for a in AGENT_REGISTRY if a in parsed.agents]
        decision = RoutingDecision(agents=names, method="llm", reason=parsed.reason[:300])
        standalone = (parsed.standalone_question or question).strip()
        if not standalone:
            raise ValueError("empty standalone question")
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
        async with asyncio.timeout(SYNTHESIS_TIMEOUT_SECONDS):
            reply = await llm.ainvoke([
                SystemMessage(content=SYNTH_PROMPT),
                HumanMessage(content=f"Question:\n{question}\n\nAgent answers:\n\n" + "\n\n".join(sections)),
            ])
        answer = _text(reply)
        if not answer:
            return None
        sources = dict.fromkeys(source for r in results if r.status == "ok" for source in r.sources)
        missing_citations = [f"[{source}]" for source in sources if f"[{source}]" not in answer]
        if missing_citations:
            answer += "\n\nSources: " + ", ".join(missing_citations)
        unavailable = [f"{r.agent} ({r.error.code if r.error else r.status})" for r in results if r.status != "ok"]
        if unavailable:
            answer += "\n\nUnavailable: " + ", ".join(unavailable) + "."
        return answer
    except Exception as exc:  # noqa: BLE001 - any LLM failure means "use fallback_answer"
        logger.warning("LLM synthesis failed, using fallback answer: %s", exc.__class__.__name__)
        return None
