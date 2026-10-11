"""FastAPI entry point for the OpsBrain Orchestrator.

The Orchestrator is the single public-facing API. Users (CLI or Slack)
send questions here; it routes them to the right agents in parallel,
collects answers, and returns one AskResponse (see orchestrator/CONTRACT.md).
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from orchestrator.graph import build_orchestrator_graph
from orchestrator.llm import get_llm
from orchestrator.memory import SessionMemory
from shared.agent_bus import KafkaAgentBus, kafka_enabled
from shared.models import AskRequest, AskResponse
from shared.observability import WORKFLOW_DURATION, WORKFLOWS, instrument_app

logger = logging.getLogger(__name__)

@lru_cache(maxsize=1)
def get_bus() -> KafkaAgentBus | None:
    if not kafka_enabled():
        return None
    bus = KafkaAgentBus()
    bus.start()
    return bus


@asynccontextmanager
async def lifespan(_app: FastAPI):
    bus = get_bus()
    try:
        yield
    finally:
        if bus is not None:
            bus.stop()
        get_graph.cache_clear()
        get_bus.cache_clear()


app = FastAPI(title="OpsBrain Orchestrator", version="0.2.0", lifespan=lifespan)
instrument_app(app, "orchestrator")

memory = SessionMemory()


@lru_cache(maxsize=1)
def get_graph():
    options = {"bus": bus} if (bus := get_bus()) is not None else {}
    return build_orchestrator_graph(llm=get_llm("router"), synth_llm=get_llm("synth"), **options)


@app.get("/health")
def health():
    return {"status": "ok", "agent": "orchestrator"}


@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest):
    """Route the question through the agent graph and return a unified answer.

    200 when at least one agent answered (status ok/partial), 502 when none did.
    """
    request_id = uuid.uuid4().hex
    started = time.monotonic()
    workflow_status = "error"
    try:
        out: dict = await get_graph().ainvoke({
            "request_id": request_id,
            "session_id": request.session_id,
            "question": request.question,
            "history": memory.history(request.session_id),
            "results": [],
        })
        workflow_status = out["status"]
    finally:
        WORKFLOWS.labels(workflow_status).inc()
        WORKFLOW_DURATION.observe(time.monotonic() - started)
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
