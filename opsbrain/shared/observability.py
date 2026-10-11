"""Low-cardinality Prometheus metrics and JSON logging shared by every API."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest


HTTP_REQUESTS = Counter(
    "opsbrain_http_requests_total",
    "HTTP requests handled by OpsBrain services.",
    ("service", "method", "route", "status_code"),
)
HTTP_DURATION = Histogram(
    "opsbrain_http_request_duration_seconds",
    "HTTP request latency for OpsBrain services.",
    ("service", "method", "route"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
)
AGENT_EXECUTIONS = Counter(
    "opsbrain_agent_executions_total",
    "Agent calls made by the orchestrator.",
    ("agent", "status"),
)
AGENT_DURATION = Histogram(
    "opsbrain_agent_execution_duration_seconds",
    "End-to-end latency of orchestrator calls to agents.",
    ("agent",),
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
)
WORKFLOWS = Counter(
    "opsbrain_orchestrator_workflows_total",
    "Orchestrator workflows by final status.",
    ("status",),
)
WORKFLOW_DURATION = Histogram(
    "opsbrain_orchestrator_workflow_duration_seconds",
    "End-to-end orchestrator workflow latency.",
    buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120),
)


class JsonFormatter(logging.Formatter):
    """Emit collector-friendly JSON without request bodies or credentials."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": getattr(record, "service", os.getenv("OPSBRAIN_SERVICE", "unknown")),
        }
        for field in ("method", "route", "status_code", "duration_ms", "agent"):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            # Exception strings can embed DSNs or backend responses. Keep the
            # useful class without copying potentially sensitive values.
            payload["exception_type"] = record.exc_info[0].__name__
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(service: str) -> None:
    os.environ["OPSBRAIN_SERVICE"] = service
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())


def instrument_app(app: FastAPI, service: str) -> None:
    """Add /metrics and request instrumentation to a FastAPI application."""
    configure_logging(service)

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.middleware("http")
    async def observe_request(request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.url.path == "/metrics":
            return await call_next(request)
        started = time.monotonic()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            route = request.scope.get("route")
            route_path = getattr(route, "path", "unmatched")
            HTTP_REQUESTS.labels(service, request.method, route_path, str(status_code)).inc()
            duration = time.monotonic() - started
            HTTP_DURATION.labels(service, request.method, route_path).observe(duration)
            logging.getLogger("opsbrain.http").info(
                "request_completed",
                extra={
                    "service": service,
                    "method": request.method,
                    "route": route_path,
                    "status_code": status_code,
                    "duration_ms": round(duration * 1000, 2),
                },
            )
