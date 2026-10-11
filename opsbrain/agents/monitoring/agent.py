"""Monitoring agent utilities for Prometheus, Grafana, and alert health."""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class MonitoringConfig:
    prometheus_base_url: str = field(
        default_factory=lambda: os.getenv(
            "PROMETHEUS_BASE_URL",
            "http://prometheus:9090",
        ).rstrip("/")
    )
    grafana_base_url: str = field(
        default_factory=lambda: os.getenv(
            "GRAFANA_BASE_URL",
            "http://grafana:3000",
        ).rstrip("/")
    )
    grafana_api_token: str = field(
        default_factory=lambda: os.getenv("GRAFANA_API_TOKEN", "")
    )
    alertmanager_base_url: str = field(
        default_factory=lambda: os.getenv(
            "ALERTMANAGER_BASE_URL",
            "http://alertmanager:9093",
        ).rstrip("/")
    )
    timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("MONITORING_TIMEOUT_SECONDS", "10"))
    )
    default_lookback_minutes: int = field(
        default_factory=lambda: int(os.getenv("MONITORING_DEFAULT_LOOKBACK_MINUTES", "15"))
    )


class MonitoringClientError(RuntimeError):
    """Raised when a monitoring backend cannot be queried successfully."""


@dataclass(slots=True)
class PodHealth:
    namespace: str
    pod: str
    phase: str = "Unknown"
    ready: bool = False
    restarts: int = 0
    containers_ready: int = 0
    containers_total: int = 0
    waiting_reasons: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.phase in {"Failed", "Unknown"}:
            return "unhealthy"
        if self.restarts > 0 and not self.ready:
            return "degraded"
        if self.phase == "Running" and self.ready:
            return "healthy"
        if self.phase in {"Pending", "Succeeded"}:
            return self.phase.lower()
        return "degraded"


class MonitoringAgent:
    """Provide monitoring queries used by the OpsBrain Monitoring Agent."""

    def __init__(self, config: MonitoringConfig | None = None) -> None:
        self.config = config or MonitoringConfig()

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "services": {
                "prometheus": self.config.prometheus_base_url,
                "grafana": self.config.grafana_base_url,
                "alertmanager": self.config.alertmanager_base_url,
            },
        }

    def query_prometheus(
        self,
        query: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        step: str = "60s",
    ) -> dict[str, Any]:
        clean_query = query.strip()
        if not clean_query:
            raise ValueError("Prometheus query cannot be empty.")

        if start and end:
            payload = self._request_json(
                "GET",
                self.config.prometheus_base_url,
                "/api/v1/query_range",
                params={
                    "query": clean_query,
                    "start": self._to_timestamp(start),
                    "end": self._to_timestamp(end),
                    "step": step,
                },
            )
        else:
            payload = self._request_json(
                "GET",
                self.config.prometheus_base_url,
                "/api/v1/query",
                params={"query": clean_query},
            )

        return self._normalize_prometheus_payload(clean_query, payload)

    def get_grafana_dashboard(self, uid: str) -> dict[str, Any]:
        dashboard_uid = uid.strip()
        if not dashboard_uid:
            raise ValueError("Grafana dashboard UID cannot be empty.")

        payload = self._request_json(
            "GET",
            self.config.grafana_base_url,
            f"/api/dashboards/uid/{dashboard_uid}",
            use_grafana_token=True,
        )
        dashboard = payload.get("dashboard", {})
        meta = payload.get("meta", {})
        panels = self._extract_panels(dashboard.get("panels", []))
        return {
            "uid": dashboard.get("uid", dashboard_uid),
            "title": dashboard.get("title", ""),
            "url": meta.get("url", ""),
            "folder_title": meta.get("folderTitle", ""),
            "panel_count": len(panels),
            "panels": panels,
        }

    def query_grafana_panel(
        self,
        *,
        datasource_uid: str,
        expr: str,
        from_minutes_ago: int | None = None,
        to_minutes_ago: int = 0,
        ref_id: str = "A",
    ) -> dict[str, Any]:
        if not datasource_uid.strip():
            raise ValueError("Grafana datasource UID is required.")
        if not expr.strip():
            raise ValueError("Grafana panel expression cannot be empty.")

        window = from_minutes_ago or self.config.default_lookback_minutes
        end = _utc_now() - timedelta(minutes=to_minutes_ago)
        start = end - timedelta(minutes=window)
        body = {
            "from": str(int(start.timestamp() * 1000)),
            "to": str(int(end.timestamp() * 1000)),
            "queries": [
                {
                    "refId": ref_id,
                    "datasource": {"uid": datasource_uid},
                    "expr": expr,
                    "instant": False,
                    "range": True,
                }
            ],
        }
        payload = self._request_json(
            "POST",
            self.config.grafana_base_url,
            "/api/ds/query",
            body=body,
            use_grafana_token=True,
        )
        return {
            "datasource_uid": datasource_uid,
            "expression": expr,
            "window_minutes": window,
            "results": payload.get("results", {}),
        }

    def get_alerts(self, *, active_only: bool = False) -> dict[str, Any]:
        payload = self._request_json(
            "GET",
            self.config.alertmanager_base_url,
            "/api/v2/alerts",
        )
        alerts = payload if isinstance(payload, list) else []
        if active_only:
            alerts = [
                alert
                for alert in alerts
                if alert.get("status", {}).get("state", "").lower() == "active"
            ]
        return {
            "count": len(alerts),
            "alerts": [self._normalize_alert(alert) for alert in alerts],
        }

    def summarize_alerts(self) -> dict[str, Any]:
        alerts_payload = self.get_alerts()
        alerts = alerts_payload["alerts"]
        by_state = Counter(alert.get("state", "unknown") for alert in alerts)
        by_severity = Counter(alert.get("severity", "unknown") for alert in alerts)
        by_alertname = Counter(alert.get("alertname", "unknown") for alert in alerts)
        return {
            "total": len(alerts),
            "active": by_state.get("active", 0),
            "suppressed": by_state.get("suppressed", 0),
            "severity_breakdown": dict(by_severity),
            "state_breakdown": dict(by_state),
            "top_alerts": [
                {"alertname": name, "count": count}
                for name, count in by_alertname.most_common(5)
            ],
        }

    def get_pod_health(self, *, namespace: str | None = None) -> dict[str, Any]:
        selectors = [f'namespace="{namespace}"'] if namespace else []
        namespace_filter = "{" + ",".join(selectors) + "}" if selectors else ""

        phase_result = self.query_prometheus(
            f"kube_pod_status_phase{namespace_filter}"
        )
        ready_result = self.query_prometheus(
            f"kube_pod_status_ready{namespace_filter}"
        )
        restart_result = self.query_prometheus(
            f"kube_pod_container_status_restarts_total{namespace_filter}"
        )
        container_ready_result = self.query_prometheus(
            f"kube_pod_container_status_ready{namespace_filter}"
        )
        waiting_reason_result = self.query_prometheus(
            f"kube_pod_container_status_waiting_reason{namespace_filter}"
        )

        pods = self._build_pod_health(
            phase_result["result"],
            ready_result["result"],
            restart_result["result"],
            container_ready_result["result"],
            waiting_reason_result["result"],
        )
        counts = Counter(pod.status for pod in pods)
        return {
            "namespace": namespace,
            "total_pods": len(pods),
            "status_breakdown": dict(counts),
            "pods": [self._serialize_pod(pod) for pod in pods],
        }

    def get_scrape_targets(self) -> dict[str, Any]:
        """Which Prometheus scrape targets are up or down (the `up` metric)."""
        result = self.query_prometheus("up")["result"]
        targets = [
            {
                "job": entry.get("metric", {}).get("job", "unknown"),
                "instance": entry.get("metric", {}).get("instance", "unknown"),
                "up": self._sample_value(entry) == 1.0,
            }
            for entry in result
        ]
        return {
            "total": len(targets),
            "down": sum(not t["up"] for t in targets),
            "targets": targets,
        }

    def ask(self, question: str) -> dict[str, Any]:
        """Best-effort natural-language entry point used by the orchestrator's /query contract (OPU-50).

        Picks one backend query by keyword; alerts are the default because they're the
        broadest health signal. MonitoringClientError propagates so /query returns 503
        instead of an error message dressed up as an answer.
        """
        q = question.lower()
        if any(word in q for word in ("pod", "crash", "restart")):
            data = self.get_pod_health()
            return {"answer": self._format_pod_health(data), "sources": ["prometheus:kube_pod_status"], "data": data}
        if any(word in q for word in ("target", "scrape", "down")):
            data = self.get_scrape_targets()
            return {"answer": self._format_targets(data), "sources": ["prometheus:up"], "data": data}
        data = self.summarize_alerts()
        return {"answer": self._format_alerts(data), "sources": ["alertmanager:alerts"], "data": data}

    @staticmethod
    def _format_alerts(data: dict[str, Any]) -> str:
        if data["total"] == 0:
            return "No alerts in Alertmanager."
        severities = ", ".join(f"{count} {sev}" for sev, count in data["severity_breakdown"].items())
        top = ", ".join(f"{a['alertname']} ({a['count']})" for a in data["top_alerts"])
        return (
            f"{data['active']} active and {data['suppressed']} suppressed alert(s) out of {data['total']} "
            f"({severities}). Most frequent: {top}."
        )

    @staticmethod
    def _format_pod_health(data: dict[str, Any]) -> str:
        if data["total_pods"] == 0:
            return "Prometheus has no pod status metrics."
        breakdown = ", ".join(f"{count} {status}" for status, count in data["status_breakdown"].items())
        unhealthy = [p["pod"] for p in data["pods"] if p["status"] in {"unhealthy", "degraded"}]
        answer = f"{data['total_pods']} pod(s): {breakdown}."
        if unhealthy:
            answer += f" Needing attention: {', '.join(unhealthy[:10])}."
        return answer

    @staticmethod
    def _format_targets(data: dict[str, Any]) -> str:
        if data["total"] == 0:
            return "Prometheus has no scrape targets."
        if data["down"] == 0:
            return f"All {data['total']} Prometheus scrape target(s) are up."
        down = ", ".join(f"{t['job']} ({t['instance']})" for t in data["targets"] if not t["up"])
        return f"{data['down']} of {data['total']} Prometheus scrape target(s) are down: {down}."

    def _request_json(
        self,
        method: str,
        base_url: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        use_grafana_token: bool = False,
    ) -> Any:
        url = f"{base_url}{path}"
        if params:
            encoded = urlencode(
                {key: value for key, value in params.items() if value is not None}
            )
            url = f"{url}?{encoded}"

        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        if use_grafana_token and self.config.grafana_api_token:
            headers["Authorization"] = f"Bearer {self.config.grafana_api_token}"

        request = Request(url, data=data, method=method, headers=headers)
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            message = exc.read().decode("utf-8", errors="ignore").strip()
            raise MonitoringClientError(
                f"{method} {url} failed with HTTP {exc.code}: {message or exc.reason}"
            ) from exc
        except URLError as exc:
            raise MonitoringClientError(
                f"Could not reach monitoring backend at {url}: {exc.reason}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise MonitoringClientError(
                f"Monitoring backend at {url} returned invalid JSON."
            ) from exc

    def _normalize_prometheus_payload(
        self,
        query: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if payload.get("status") != "success":
            raise MonitoringClientError(
                f"Prometheus returned non-success status for query: {query}"
            )
        data = payload.get("data", {})
        return {
            "query": query,
            "result_type": data.get("resultType", "unknown"),
            "result_count": len(data.get("result", [])),
            "result": data.get("result", []),
        }

    def _extract_panels(self, panels: list[dict[str, Any]]) -> list[dict[str, Any]]:
        extracted: list[dict[str, Any]] = []
        for panel in panels:
            if panel.get("type") == "row" and panel.get("panels"):
                extracted.extend(self._extract_panels(panel["panels"]))
                continue
            targets = panel.get("targets") or []
            extracted.append(
                {
                    "id": panel.get("id"),
                    "title": panel.get("title", ""),
                    "type": panel.get("type", ""),
                    "datasource_uid": self._panel_datasource_uid(panel),
                    "targets": [
                        {
                            "ref_id": target.get("refId"),
                            "expr": target.get("expr") or target.get("query"),
                        }
                        for target in targets
                    ],
                }
            )
        return extracted

    def _panel_datasource_uid(self, panel: dict[str, Any]) -> str | None:
        datasource = panel.get("datasource")
        if isinstance(datasource, dict):
            return datasource.get("uid")
        return None

    def _normalize_alert(self, alert: dict[str, Any]) -> dict[str, Any]:
        labels = alert.get("labels", {})
        annotations = alert.get("annotations", {})
        status = alert.get("status", {})
        return {
            "alertname": labels.get("alertname", "unknown"),
            "severity": labels.get("severity", "unknown"),
            "namespace": labels.get("namespace"),
            "pod": labels.get("pod"),
            "state": status.get("state", "unknown").lower(),
            "summary": annotations.get("summary") or annotations.get("description", ""),
            "starts_at": alert.get("startsAt"),
            "ends_at": alert.get("endsAt"),
        }

    def _build_pod_health(
        self,
        phase_result: list[dict[str, Any]],
        ready_result: list[dict[str, Any]],
        restart_result: list[dict[str, Any]],
        container_ready_result: list[dict[str, Any]],
        waiting_reason_result: list[dict[str, Any]],
    ) -> list[PodHealth]:
        pods: dict[tuple[str, str], PodHealth] = {}

        for entry in phase_result:
            labels = entry.get("metric", {})
            value = self._sample_value(entry)
            if value < 1:
                continue
            key = (labels.get("namespace", ""), labels.get("pod", ""))
            pods[key] = PodHealth(
                namespace=key[0],
                pod=key[1],
                phase=labels.get("phase", "Unknown"),
            )

        for entry in ready_result:
            labels = entry.get("metric", {})
            key = (labels.get("namespace", ""), labels.get("pod", ""))
            pod = pods.setdefault(key, PodHealth(namespace=key[0], pod=key[1]))
            if labels.get("condition") == "true" and self._sample_value(entry) >= 1:
                pod.ready = True

        for entry in restart_result:
            labels = entry.get("metric", {})
            key = (labels.get("namespace", ""), labels.get("pod", ""))
            pod = pods.setdefault(key, PodHealth(namespace=key[0], pod=key[1]))
            pod.restarts += int(self._sample_value(entry))

        ready_counts: dict[tuple[str, str], dict[str, int]] = defaultdict(
            lambda: {"ready": 0, "total": 0}
        )
        for entry in container_ready_result:
            labels = entry.get("metric", {})
            key = (labels.get("namespace", ""), labels.get("pod", ""))
            ready_counts[key]["total"] += 1
            if self._sample_value(entry) >= 1:
                ready_counts[key]["ready"] += 1

        for key, counts in ready_counts.items():
            pod = pods.setdefault(key, PodHealth(namespace=key[0], pod=key[1]))
            pod.containers_ready = counts["ready"]
            pod.containers_total = counts["total"]

        for entry in waiting_reason_result:
            if self._sample_value(entry) < 1:
                continue
            labels = entry.get("metric", {})
            key = (labels.get("namespace", ""), labels.get("pod", ""))
            pod = pods.setdefault(key, PodHealth(namespace=key[0], pod=key[1]))
            reason = labels.get("reason")
            if reason and reason not in pod.waiting_reasons:
                pod.waiting_reasons.append(reason)

        return sorted(pods.values(), key=lambda pod: (pod.namespace, pod.pod))

    def _serialize_pod(self, pod: PodHealth) -> dict[str, Any]:
        return {
            "namespace": pod.namespace,
            "pod": pod.pod,
            "phase": pod.phase,
            "ready": pod.ready,
            "restarts": pod.restarts,
            "containers_ready": pod.containers_ready,
            "containers_total": pod.containers_total,
            "waiting_reasons": pod.waiting_reasons,
            "status": pod.status,
        }

    @staticmethod
    def _sample_value(entry: dict[str, Any]) -> float:
        value = entry.get("value")
        if isinstance(value, list) and len(value) >= 2:
            return float(value[1])
        return 0.0

    @staticmethod
    def _to_timestamp(value: datetime) -> str:
        return str(value.timestamp())
