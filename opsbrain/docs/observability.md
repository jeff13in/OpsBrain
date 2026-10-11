# OpsBrain observability

OpsBrain exports Prometheus metrics from every FastAPI service, provisions two
Grafana dashboards, centralizes JSON application logs in Loki, and sends
Prometheus alerts to the existing Alertmanager. The Monitoring Agent reads the
same backends and is itself monitored.

## Architecture

```text
orchestrator + four agents -- /metrics --> Prometheus --> Alertmanager
             -- JSON stdout --> Promtail --> Loki
Prometheus + Loki -----------------------> Grafana
Prometheus + Grafana + Alertmanager -----> Monitoring Agent
```

HTTP labels use route templates such as `/pulls/{number}`, never raw URLs, user
IDs, request IDs, questions, or session IDs. Logs contain timestamp, severity,
service, message, route, status, and duration; request bodies, headers,
credentials, and query strings are omitted.

## Local deployment

Docker Engine with Compose v2 and the existing `.env` values are required.
Promtail reads Docker metadata and JSON log files through read-only mounts of
the Docker socket and `/var/lib/docker/containers`. This local collector setup
targets a Linux Docker Engine; use the Kubernetes DaemonSet configuration for
EKS rather than Docker Desktop host paths.

```bash
cd opsbrain
docker compose --profile full up --build -d
docker compose ps
curl http://localhost:8000/metrics
curl http://localhost:9090/api/v1/targets
```

Grafana is at <http://localhost:3000>, Prometheus at <http://localhost:9090>,
Alertmanager at <http://localhost:9093>, and Loki at
<http://localhost:3100/ready>. Anonymous Grafana admin access is local-only.

Expected targets are `opsbrain-orchestrator`, `opsbrain-rag-agent`,
`opsbrain-monitoring-agent`, `opsbrain-infra-agent`, and
`opsbrain-code-agent`. Provisioned dashboards are:

- **OpsBrain / Service Health**: availability, throughput, 5xx ratio,
  p50/p95/p99 latency, CPU, memory, and logs.
- **OpsBrain / Agent Activity**: agent outcomes, failures, p50/p95/p99 latency,
  workflow activity and latency, and agent logs.

Useful queries:

```promql
sum by (service) (rate(opsbrain_http_requests_total[5m]))
histogram_quantile(0.95, sum by (service, le) (rate(opsbrain_http_request_duration_seconds_bucket[5m])))
sum by (agent, status) (increase(opsbrain_agent_executions_total[1h]))
```

```logql
{namespace="local", service="orchestrator"} | json
{agent_type="rag", severity=~"ERROR|CRITICAL"} | json
```

Local Loki retention is seven days. Prometheus and Grafana use persistent
Compose volumes.

## Kubernetes deployment

Application Services have a named `http` port, scrape annotations, and stable
`app` labels. `k8s/observability.yaml` uses Prometheus Operator
`ServiceMonitor` and `PrometheusRule` resources; install their CRDs first.
Their `release: kube-prometheus-stack` label matches the Helm release below;
change both the release name and selector/labels together if you rename it.

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update
kubectl create namespace observability
helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace observability --values infra/helm/kube-prometheus-stack-values.yaml
helm upgrade --install loki grafana/loki \
  --namespace observability --values infra/helm/loki-values.yaml
helm upgrade --install promtail grafana/promtail \
  --namespace observability --values infra/helm/promtail-values.yaml
kubectl apply -f k8s/observability.yaml
```

Provision dashboards through the enabled Grafana sidecar:

```bash
kubectl -n opsbrain create configmap opsbrain-grafana-dashboards \
  --from-file=infra/grafana/dashboards/opsbrain-service-health.json \
  --from-file=infra/grafana/dashboards/opsbrain-agent-activity.json \
  --dry-run=client -o yaml | kubectl label --local -f - grafana_dashboard=1 -o yaml | kubectl apply -f -
kubectl -n observability port-forward svc/kube-prometheus-stack-grafana 3000:80
kubectl -n observability port-forward svc/kube-prometheus-stack-prometheus 9090:9090
```

The values use 15-day Prometheus retention and 20 GiB PVCs for Prometheus and
Loki. Confirm the StorageClass and size for the target cluster. Production
object storage and multi-replica Loki require an approved AWS bucket, IAM role,
availability target, and retention policy, so they are not guessed here.
Configure Grafana ingress/TLS/authentication and Alertmanager receivers with
separately managed secrets; no notification credentials are committed. The
local Alertmanager intentionally routes to a `discard` receiver so development
alerts do not contact real responders.

## Metrics

| Metric | Labels | Purpose |
|---|---|---|
| `opsbrain_http_requests_total` | service, method, route, status_code | Throughput/errors |
| `opsbrain_http_request_duration_seconds` | service, method, route | HTTP latency |
| `opsbrain_agent_executions_total` | agent, status | Agent outcomes |
| `opsbrain_agent_execution_duration_seconds` | agent | Agent latency |
| `opsbrain_orchestrator_workflows_total` | status | Workflow outcomes |
| `opsbrain_orchestrator_workflow_duration_seconds` | none | Workflow latency |

Standard Python process metrics supply CPU and memory panels.

## Alerts and initial thresholds

| Alert | Threshold | Reasoning |
|---|---|---|
| `OpsBrainServiceUnavailable` | down 2m | Tolerates a missed scrape |
| `OpsBrainPrometheusScrapeFailure` | rejected samples in 10m for 5m | Detects broken payloads/limits |
| `OpsBrainHighHttpErrorRate` | >5% 5xx for 10m | Sustained degradation |
| `OpsBrainHighRequestLatency` | p95 >2s for 10m | Initial API objective |
| `OpsBrainRepeatedAgentFailures` | >=3 failures/10m for 5m | Ignores a single transient error |
| `OpsBrainHighAgentLatency` | p95 >10s for 10m | Allows slower external dependencies |

These are starting assumptions, not established SLOs. Tune them after a
representative traffic period. Existing Alertmanager routing is reused.

## Troubleshooting and runbooks

### Service unavailable

Check Prometheus **Status > Targets**, then `kubectl -n opsbrain get pods,svc`
and the pod logs. Confirm the Service selects ready pods and `/metrics` is
reachable from inside the cluster.

### Prometheus scrape failure

Open the target's last error, validate `/metrics`, and inspect sample limits or
duplicate timestamps. Application metrics do not emit explicit timestamps.

### High HTTP error rate

Filter logs by service and `severity=~"ERROR|CRITICAL"`, then split the request
counter by route/status. Check downstream configuration without printing
secret values.

### High latency

Compare HTTP and agent histograms to isolate the slow hop. Check backend
latency, saturation, timeouts, and deployments before changing thresholds.

### Repeated agent failures

Inspect the `agent` label, health endpoint, and logs, then its backend:
Gemini/Postgres, monitoring services, AWS/Kubernetes, or GitHub.

For missing Loki logs, check Promtail logs and `/ready`, its Docker socket or
Kubernetes RBAC, then query `{namespace="opsbrain"}`. Non-JSON lines remain
searchable even if they have no `severity` label.

## Validation

```bash
docker compose config --quiet
docker run --rm -v "$PWD/infra/prometheus:/etc/prometheus:ro" prom/prometheus:v2.54.1 \
  promtool check config /etc/prometheus/prometheus.yml
python -m pytest tests/
python -m ruff check agents/ orchestrator/ shared/
```

After deployment, verify targets, both dashboards, a Loki query, and a
controlled stopped-service alert. Do not perform failure injection in
production without an approved change.
