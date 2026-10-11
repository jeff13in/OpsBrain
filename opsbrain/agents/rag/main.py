"""FastAPI entrypoint for the OpsBrain RAG agent."""

from __future__ import annotations

import logging
from functools import lru_cache

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from rag.agent import AgentResponse, RAGAgent
from rag.ingestor import IngestionResult, PgVectorIngestor
from shared.observability import instrument_app

logger = logging.getLogger(__name__)


app = FastAPI(
    title="OpsBrain RAG Agent",
    version="0.1.0",
    description="Retrieve runbook context from pgvector and answer DevOps questions.",
)
instrument_app(app, "rag-agent")


class QueryRequest(BaseModel):
    question: str = Field(min_length=5, max_length=2000)
    top_k: int = Field(default=4, ge=1, le=10)


class QueryResponse(BaseModel):
    answer: str
    sources: list[str]
    grounded: bool
    validation_errors: list[str]
    retrieved_chunks: int


class HealthResponse(BaseModel):
    status: str


class IngestRequest(BaseModel):
    directory: str = Field(default="/app/data", min_length=1)


class IngestResponse(BaseModel):
    documents_processed: int
    chunks_stored: int


@lru_cache(maxsize=1)
def get_agent() -> RAGAgent:
    return RAGAgent()


@lru_cache(maxsize=1)
def get_ingestor() -> PgVectorIngestor:
    return PgVectorIngestor()


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/ingest", response_model=IngestResponse)
def ingest_documents(request: IngestRequest) -> IngestResponse:
    try:
        result: IngestionResult = get_ingestor().ingest(request.directory)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (NotADirectoryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - safety net for service failures
        logger.exception("Document ingestion failed.")
        raise HTTPException(status_code=500, detail="Failed to ingest documents.") from exc
    return IngestResponse(
        documents_processed=result.documents_processed,
        chunks_stored=result.chunks_stored,
    )


@app.post("/query", response_model=QueryResponse)
def query_rag(request: QueryRequest) -> QueryResponse:
    try:
        response: AgentResponse = get_agent().ask(
            request.question,
            top_k=request.top_k,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - safety net for service failures
        logger.exception("RAG query failed.")
        raise HTTPException(status_code=500, detail="Failed to query the RAG agent.") from exc

    return QueryResponse(
        answer=response.answer,
        sources=response.sources,
        grounded=response.grounded,
        validation_errors=response.validation_errors,
        retrieved_chunks=response.retrieved_chunks,
    )
