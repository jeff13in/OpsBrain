"""FastAPI entry point for the OpsBrain Orchestrator.

The Orchestrator is the single public-facing API. Users (CLI or Slack)
send questions here; it routes them to the right agents in parallel,
collects answers, and returns one AskResponse (see orchestrator/CONTRACT.md).
"""

from __future__ import annotations

import logging
import uuid
from functools import lru_cache

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from orchestrator.graph import build_orchestrator_graph
from orchestrator.llm import get_llm
from orchestrator.memory import SessionMemory
from shared.models import AskRequest, AskResponse

logger = logging.getLogger(__name__)

app = FastAPI(title="OpsBrain Orchestrator", version="0.2.0")

memory = SessionMemory()


@lru_cache(maxsize=1)
def get_graph():
    llm = get_llm()
    if llm is None:
        logger.warning("GOOGLE_API_KEY not set — routing by keywords, no LLM synthesis.")
    return build_orchestrator_graph(llm=llm)


@app.get("/health")
def health():
    return {"status": "ok", "agent": "orchestrator"}


@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest):
    """Route the question through the agent graph and return a unified answer.

    200 when at least one agent answered (status ok/partial), 502 when none did.
    """
    request_id = uuid.uuid4().hex
    out: dict = await get_graph().ainvoke({
        "request_id": request_id,
        "session_id": request.session_id,
        "question": request.question,
        "history": memory.history(request.session_id),
        "results": [],
    })
    # Parallel branches append in completion order; report them in routing order.
    order = {name: i for i, name in enumerate(out["routing"].agents)}
    results = sorted(out["results"], key=lambda r: order.get(r.agent, len(order)))
    response = AskResponse(
        request_id=request_id,
        session_id=request.session_id,
        question=request.question,
        status=out["status"],
        answer=out["final_answer"],
        sources=out["sources"],
        routing=out["routing"],
        results=results,
    )
    if response.status != "error":
        memory.append(request.session_id, request.question, response.answer)
    return JSONResponse(status_code=502 if response.status == "error" else 200, content=response.model_dump(mode="json"))
