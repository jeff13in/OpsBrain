"""FastAPI entrypoint for the OpsBrain Code Agent."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from agents.code.agent import CodeAgent, CodeClientError
from shared.agent_bus import attach_kafka_worker

app = FastAPI(
    title="OpsBrain Code Agent",
    version="0.1.0",
    description="Query GitHub pull requests and GitHub Actions CI/CD pipeline status.",
)

# Also answer the Orchestrator's requests over Kafka when AGENT_TRANSPORT=kafka (OPU-50).
attach_kafka_worker(app, "code")


class HealthResponse(BaseModel):
    status: str
    repo: str | None
    github_token_configured: bool


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class PullRequestListResponse(BaseModel):
    repo: str
    state: str
    count: int
    pull_requests: list[dict[str, Any]]


class WorkflowRunListResponse(BaseModel):
    repo: str
    count: int
    workflow_runs: list[dict[str, Any]]


class CommitListResponse(BaseModel):
    repo: str
    branch: str | None
    count: int
    commits: list[dict[str, Any]]


class DeploymentListResponse(BaseModel):
    repo: str
    count: int
    deployments: list[dict[str, Any]]


class WorkflowDispatchRequest(BaseModel):
    ref: str = Field(default="main", min_length=1)
    inputs: dict[str, Any] | None = None


@lru_cache(maxsize=1)
def get_agent() -> CodeAgent:
    return CodeAgent()


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(**get_agent().health())


@app.post("/query")
def query(request: QueryRequest) -> dict[str, Any]:
    """Orchestrator entry point. Failures return CodeClientError.status_code (503 retryable,
    4xx bad input, 500 misconfiguration) — never a 200 with the error as the answer."""
    try:
        return get_agent().ask(request.question)
    except CodeClientError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/pulls", response_model=PullRequestListResponse)
def list_pulls(
    state: str = Query(default="open", pattern="^(open|closed|all)$"),
    limit: int = Query(default=10, ge=1, le=100),
) -> PullRequestListResponse:
    try:
        return PullRequestListResponse(**get_agent().list_pull_requests(state=state, limit=limit))
    except CodeClientError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/pulls/{number}")
def get_pull(number: int) -> dict[str, Any]:
    try:
        return get_agent().get_pull_request(number)
    except CodeClientError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/pulls/{number}/status")
def get_pull_status(number: int) -> dict[str, Any]:
    try:
        return get_agent().get_pull_request_status(number)
    except CodeClientError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/actions/runs", response_model=WorkflowRunListResponse)
def list_runs(
    branch: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=100),
) -> WorkflowRunListResponse:
    try:
        return WorkflowRunListResponse(
            **get_agent().list_workflow_runs(branch=branch, status=status, limit=limit)
        )
    except CodeClientError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/actions/summary")
def actions_summary(branch: str | None = Query(default=None)) -> dict[str, Any]:
    try:
        return get_agent().summarize_ci(branch=branch)
    except CodeClientError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/commits", response_model=CommitListResponse)
def list_commits(
    branch: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=100),
) -> CommitListResponse:
    try:
        return CommitListResponse(**get_agent().list_commits(branch=branch, limit=limit))
    except CodeClientError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/commits/{sha}")
def get_commit(sha: str) -> dict[str, Any]:
    try:
        return get_agent().get_commit(sha)
    except CodeClientError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/deployments", response_model=DeploymentListResponse)
def list_deployments(
    environment: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=100),
) -> DeploymentListResponse:
    try:
        return DeploymentListResponse(
            **get_agent().list_deployments(environment=environment, limit=limit)
        )
    except CodeClientError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/deployments/{deployment_id}/status")
def get_deployment_status(deployment_id: int) -> dict[str, Any]:
    try:
        return get_agent().get_deployment_status(deployment_id)
    except CodeClientError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.post("/actions/runs/{run_id}/rerun")
def rerun_workflow(
    run_id: int, failed_jobs_only: bool = Query(default=False)
) -> dict[str, Any]:
    try:
        return get_agent().rerun_workflow(run_id, failed_jobs_only=failed_jobs_only)
    except CodeClientError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.post("/actions/workflows/{workflow}/dispatch")
def trigger_workflow(workflow: str, request: WorkflowDispatchRequest) -> dict[str, Any]:
    try:
        return get_agent().trigger_workflow(
            workflow, ref=request.ref, inputs=request.inputs
        )
    except CodeClientError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
