"""Shared Pydantic models used across all OpsBrain agents.

Define every cross-agent data shape here so each microservice speaks
the same language without duplicating model code.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

# ── RAG Agent ────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str
    top_k: int = 5


class DocumentChunk(BaseModel):
    content: str
    source: str
    chunk_id: int
    metadata: dict[str, Any] = {}


class QueryResponse(BaseModel):
    question: str
    answer: str
    sources: list[str]
    agent: str = "rag"


class IngestRequest(BaseModel):
    directory: str = "./docs"


class IngestResponse(BaseModel):
    status: str
    files_processed: int
    chunks_stored: int


# ── Inter-Agent Messaging (Kafka) ─────────────────────────────────────────────

class AgentMessage(BaseModel):
    """Message envelope passed between agents over Kafka."""
    task_id: str
    from_agent: str
    to_agent: str
    payload: dict[str, Any]


# ── Orchestrator contract (OPU-42) ────────────────────────────────────────────
# The shapes every agent and the Orchestrator agree on. See
# orchestrator/CONTRACT.md for the routing and aggregation rules around them.

AgentName = Literal["rag", "monitoring", "infra", "code"]

AgentStatus = Literal["ok", "error", "timeout"]
"""Outcome of a single agent call."""

ErrorCode = Literal["timeout", "unavailable", "bad_request", "agent_error", "invalid_response"]
"""Why an agent call failed.

timeout          — no reply within the per-agent deadline          (retryable)
unavailable      — connection refused / DNS failure / HTTP 503     (retryable)
bad_request      — agent rejected the input (HTTP 4xx)             (not retryable)
agent_error      — agent crashed (HTTP 5xx other than 503)         (not retryable)
invalid_response — 2xx, but the body didn't match AgentReply       (not retryable)
"""

OverallStatus = Literal["ok", "partial", "error"]
"""ok = every routed agent succeeded; partial = at least one did; error = none did."""


class AgentQuery(BaseModel):
    """What the Orchestrator POSTs to an agent's /query endpoint."""
    question: str = Field(min_length=1, max_length=2000)
    request_id: str


class AgentReply(BaseModel):
    """The minimum every agent's /query must return on success (HTTP 2xx).

    Agents may return extra fields (RAG adds `grounded`, `retrieved_chunks`, …);
    they are kept in AgentResult.data rather than dropped.
    """
    answer: str
    sources: list[str] = []
    data: dict[str, Any] | None = None


class AgentError(BaseModel):
    code: ErrorCode
    message: str
    retryable: bool


class AgentResult(BaseModel):
    """One agent's outcome, normalized by the Orchestrator. Never raised — always returned."""
    agent: AgentName
    status: AgentStatus
    answer: str | None = None
    sources: list[str] = []
    data: dict[str, Any] | None = None
    error: AgentError | None = None
    latency_ms: int = 0


class RoutingDecision(BaseModel):
    agents: list[AgentName] = Field(min_length=1)
    method: Literal["llm", "keyword", "fallback"]
    reason: str


class AskRequest(BaseModel):
    """Public request to the Orchestrator's /ask endpoint."""
    question: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None


class AskResponse(BaseModel):
    """Public response from the Orchestrator's /ask endpoint.

    Returned with HTTP 200 for status ok/partial and 502 for status error,
    so the body shape is the same either way.
    """
    request_id: str
    session_id: str | None = None
    question: str
    status: OverallStatus
    answer: str
    sources: list[str]
    routing: RoutingDecision
    results: list[AgentResult]


class KafkaAgentRequest(BaseModel):
    """AgentQuery envelope with reply correlation and an absolute deadline."""
    correlation_id: str = Field(min_length=1, max_length=128)
    agent: AgentName
    query: AgentQuery
    reply_topic: str = Field(min_length=1, max_length=249, pattern=r"^[A-Za-z0-9._-]+$")
    deadline: float = Field(gt=0, allow_inf_nan=False)


class KafkaAgentReply(BaseModel):
    """The agent's HTTP-equivalent status/body transported over Kafka."""
    correlation_id: str = Field(min_length=1, max_length=128)
    agent: AgentName
    status_code: int = Field(ge=100, le=599, strict=True)
    body: Any = None
