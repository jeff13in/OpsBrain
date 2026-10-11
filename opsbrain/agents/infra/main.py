"""FastAPI entrypoint for the OpsBrain Infra Agent."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from agents.infra.agent import InfraAgent, InfraClientError
from shared.observability import instrument_app

app = FastAPI(
    title="OpsBrain Infra Agent",
    version="0.1.0",
    description="Check AWS resource state, Kubernetes pod/node health, and Terraform plan status.",
)
instrument_app(app, "infra-agent")


class HealthResponse(BaseModel):
    status: str
    capabilities: dict[str, bool]


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class Ec2ListResponse(BaseModel):
    region: str
    count: int
    instances: list[dict[str, Any]]


class PodHealthResponse(BaseModel):
    namespace: str | None
    total_pods: int
    status_breakdown: dict[str, int]
    pods: list[dict[str, Any]]


class NodeListResponse(BaseModel):
    total_nodes: int
    nodes: list[dict[str, Any]]


class DeploymentListResponse(BaseModel):
    namespace: str | None
    total_deployments: int
    status_breakdown: dict[str, int]
    deployments: list[dict[str, Any]]


class EksListResponse(BaseModel):
    region: str
    count: int
    clusters: list[dict[str, Any]]


class RdsListResponse(BaseModel):
    region: str
    count: int
    status_breakdown: dict[str, int]
    instances: list[dict[str, Any]]


@lru_cache(maxsize=1)
def get_agent() -> InfraAgent:
    return InfraAgent()


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(**get_agent().health())


@app.post("/query")
def query(request: QueryRequest) -> dict[str, Any]:
    """Orchestrator entry point. Failures return InfraClientError.status_code (503 retryable,
    4xx bad input, 500 misconfiguration) — never a 200 with the error as the answer."""
    try:
        return get_agent().ask(request.question)
    except InfraClientError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/aws/instances", response_model=Ec2ListResponse)
def list_instances(state: str | None = Query(default=None)) -> Ec2ListResponse:
    try:
        return Ec2ListResponse(**get_agent().list_ec2_instances(state=state))
    except InfraClientError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/aws/instances/summary")
def instances_summary() -> dict[str, Any]:
    try:
        return get_agent().summarize_ec2()
    except InfraClientError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/k8s/pods", response_model=PodHealthResponse)
def pod_health(namespace: str | None = Query(default=None, min_length=1)) -> PodHealthResponse:
    try:
        return PodHealthResponse(**get_agent().get_pod_health(namespace=namespace))
    except InfraClientError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/k8s/nodes", response_model=NodeListResponse)
def list_nodes() -> NodeListResponse:
    try:
        return NodeListResponse(**get_agent().list_nodes())
    except InfraClientError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/terraform/plan")
def terraform_plan(plan_file: str | None = Query(default=None)) -> dict[str, Any]:
    try:
        return get_agent().get_terraform_plan_summary(plan_file=plan_file)
    except InfraClientError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/k8s/deployments", response_model=DeploymentListResponse)
def list_deployments(namespace: str | None = Query(default=None, min_length=1)) -> DeploymentListResponse:
    try:
        return DeploymentListResponse(**get_agent().list_deployments(namespace=namespace))
    except InfraClientError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/k8s/usage")
def node_resource_usage() -> dict[str, Any]:
    try:
        return get_agent().get_node_resource_usage()
    except InfraClientError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/aws/eks", response_model=EksListResponse)
def list_eks_clusters() -> EksListResponse:
    try:
        return EksListResponse(**get_agent().list_eks_clusters())
    except InfraClientError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/aws/rds", response_model=RdsListResponse)
def list_rds_instances() -> RdsListResponse:
    try:
        return RdsListResponse(**get_agent().list_rds_instances())
    except InfraClientError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/health/summary")
def health_summary() -> dict[str, Any]:
    return get_agent().get_health_summary()
