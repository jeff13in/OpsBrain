# OPU-54: Helm chart with services, probes, resources and autoscaling

Validated October 14, 2026 (UTC) on branch `joint` (after `5702e4d`), Helm
v4.3.0, Docker Desktop Kubernetes v1.34.3 with metrics-server v0.8.0.

## What the chart provides (`helm/opsbrain`)

| Requirement | Implementation |
| --- | --- |
| Chart per service | One chart; `services.<name>` in `values.yaml` drives the Orchestrator, `rag-agent`, `monitoring-agent`, `infra-agent`, `code-agent` |
| Service definitions | ClusterIP Service per service on its port, with Prometheus scrape annotations; Orchestrator uses `sessionAffinity: ClientIP` (in-process history). Optional Ingress exposes the Orchestrator only |
| Probes | `startupProbe` (up to 2 min for imports and the Kafka connection), then strict `livenessProbe` and `readinessProbe` on `/health` |
| Requests/limits | Per service in values (e.g. RAG 250m/512Mi → 1/1Gi) |
| Autoscaling | `autoscaling/v2` HPA on CPU (70%), 5-minute scale-down stabilization; Orchestrator 2–5 and RAG 1–3 on by default, other agents opt-in. Rendering fails if an agent's `maxReplicas` exceeds the dev Kafka partition count |
| Config/secrets | `opsbrain-chat` ConfigMap (Groq/Gemini models; a checksum rolls pods on change). Secrets come from an existing `opsbrain-secrets` Secret; GitHub and Grafana tokens are optional |
| Hardening | `automountServiceAccountToken: false` except Infra; seccomp `RuntimeDefault`; no privilege escalation; all capabilities dropped |
| Infra access | ServiceAccount + ClusterRole with get/list on pods, nodes, deployments and `metrics.k8s.io` only; `KUBE_IN_CLUSTER=true`; IRSA annotation hook for read-only AWS |
| Images | `ghcr.io/jeff13in/opsbrain-<service>:<tag>`, matching what CI pushes |
| Dev Kafka (optional) | KRaft StatefulSet `bitnamilegacy/kafka:3.7` (same as Compose), advertised listener `kafka:9092`, 3 partitions |

## Defects in the old `k8s/` manifests that the chart fixes

- RAG received `POSTGRES_HOST`/`POSTGRES_PASSWORD`, but the agent reads `DATABASE_URL`.
- Infra had no ServiceAccount, RBAC or `KUBE_IN_CLUSTER`, so it could not read the cluster.
- Code had no `GITHUB_REPO`.
- Readiness probes were missing on four of five services.
- Kafka used the deprecated `bitnami/kafka` image, had no advertised listener,
  and its headless Service would deadlock KRaft (see below).
- Images pointed at placeholder ECR URLs; CI pushes to GHCR.

## Results

| Check | Result |
| --- | --- |
| `helm lint` | Passed (info: no icon) |
| `kubectl apply --dry-run=server` on rendered output (dev Kafka on, and Ingress) | All 20 objects accepted by the API server |
| Partition guard (`rag-agent maxReplicas=5`, 3 partitions) | Render fails with a clear message |
| `helm upgrade --install` with `values-docker-desktop.yaml` | Deployed; Kafka and all five Deployments Available, 0 restarts |
| Agent readiness | Each logged `listening on opsbrain.agent.<agent>.requests`; Orchestrator listening on replies |
| `/ask` via `port-forward svc/orchestrator` | Monitoring, RAG, Infra and Code each `ok` with real sources over in-cluster Kafka |
| Infra in-cluster | Reads the cluster through its ServiceAccount (18 pods, 8 deployments, all healthy) |
| RBAC (`auth can-i` as the SA) | list pods/nodes/deployments/node metrics: yes; get secrets, delete pods, patch deployments: no |
| HPA metrics | Both HPAs report live CPU (e.g. orchestrator 40%/70%) |
| HPA scaling under load | 8 busybox workers on `/health` for 150s: CPU 102%/70% → orchestrator scaled 2 → 3, settled at ~68% |

## Defect found during the live install

**KRaft Kafka deadlocked on startup.** The controller resolves
`kafka-0.kafka-headless`, but headless Services only publish Ready pods, so the
broker never became Ready and the liveness probe restarted it in a loop.
Fixed with `publishNotReadyAddresses: true` on the headless Service and a
`startupProbe` (up to 3 minutes). After the fix Kafka was Ready in ~30s with no restarts.

## Local trial notes

Docker Desktop's kind-based cluster has its own image store, so images built
by Compose were loaded into the node with
`docker save … | docker exec -i desktop-control-plane ctr -n k8s.io images import -`,
and `values-docker-desktop.yaml` uses `pullPolicy: Never`. Postgres and
Prometheus/Grafana/Alertmanager were reused from Compose via `host.docker.internal`.

## Not covered

- An EKS deployment and the ArgoCD Application (Week 4/6; AWS is deferred).
- Pulling from GHCR in-cluster (packages may need `imagePullSecrets` if private).
- The legacy `k8s/` manifests are left in place for whatever ArgoCD path still
  references them; switch ArgoCD to `helm/opsbrain` and then delete them.
