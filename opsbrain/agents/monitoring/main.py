"""FastAPI entrypoint for the OpsBrain Monitoring agent."""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from monitoring.agent import MonitoringAgent, MonitoringClientError
from shared.agent_bus import attach_kafka_worker

app = FastAPI(
    title="OpsBrain Monitoring Agent",
    version="0.1.0",
    description=(
        "Query Prometheus, Grafana, and Alertmanager for infrastructure and "
        "application health."
    ),
)

# Also answer the Orchestrator's requests over Kafka when AGENT_TRANSPORT=kafka (OPU-50).
attach_kafka_worker(app, "monitoring")


class HealthResponse(BaseModel):
    status: str
    services: dict[str, str]


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class PrometheusQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    start: datetime | None = None
    end: datetime | None = None
    step: str = Field(default="60s", min_length=2, max_length=20)


class GrafanaPanelQueryRequest(BaseModel):
    datasource_uid: str = Field(min_length=1, max_length=200)
    expr: str = Field(min_length=1, max_length=2000)
    from_minutes_ago: int | None = Field(default=None, ge=1, le=1440)
    to_minutes_ago: int = Field(default=0, ge=0, le=1440)
    ref_id: str = Field(default="A", min_length=1, max_length=5)


class AlertListResponse(BaseModel):
    count: int
    alerts: list[dict[str, Any]]


class AlertSummaryResponse(BaseModel):
    total: int
    active: int
    suppressed: int
    severity_breakdown: dict[str, int]
    state_breakdown: dict[str, int]
    top_alerts: list[dict[str, Any]]


class PodHealthResponse(BaseModel):
    namespace: str | None
    total_pods: int
    status_breakdown: dict[str, int]
    pods: list[dict[str, Any]]


@lru_cache(maxsize=1)
def get_agent() -> MonitoringAgent:
    return MonitoringAgent()


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    response = get_agent().health()
    return HealthResponse(**response)


@app.post("/query")
def query(request: QueryRequest) -> dict[str, Any]:
    """Orchestrator entry point. 503 when Prometheus/Alertmanager can't be queried —
    never a 200 with the error as the answer."""
    try:
        return get_agent().ask(request.question)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MonitoringClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/metrics/query")
def query_metrics(request: PrometheusQueryRequest) -> dict[str, Any]:
    try:
        start = _normalize_datetime(request.start)
        end = _normalize_datetime(request.end)
        return get_agent().query_prometheus(
            request.query,
            start=start,
            end=end,
            step=request.step,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MonitoringClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/dashboards/{uid}")
def get_dashboard(uid: str) -> dict[str, Any]:
    try:
        return get_agent().get_grafana_dashboard(uid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MonitoringClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/dashboards/panel-query")
def query_panel(request: GrafanaPanelQueryRequest) -> dict[str, Any]:
    try:
        return get_agent().query_grafana_panel(
            datasource_uid=request.datasource_uid,
            expr=request.expr,
            from_minutes_ago=request.from_minutes_ago,
            to_minutes_ago=request.to_minutes_ago,
            ref_id=request.ref_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MonitoringClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/alerts", response_model=AlertListResponse)
def list_alerts(
    active_only: bool = Query(default=False, description="Only include active alerts."),
) -> AlertListResponse:
    try:
        response = get_agent().get_alerts(active_only=active_only)
    except MonitoringClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return AlertListResponse(**response)


@app.get("/alerts/summary", response_model=AlertSummaryResponse)
def summarize_alerts() -> AlertSummaryResponse:
    try:
        response = get_agent().summarize_alerts()
    except MonitoringClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return AlertSummaryResponse(**response)


@app.get("/pods/health", response_model=PodHealthResponse)
def pod_health(namespace: str | None = Query(default=None, min_length=1)) -> PodHealthResponse:
    try:
        response = get_agent().get_pod_health(namespace=namespace)
    except MonitoringClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return PodHealthResponse(**response)


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
