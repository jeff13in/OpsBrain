# Runbook: High CPU Usage on API Servers

## Overview
Steps to diagnose and resolve sustained high CPU (> 80%) on any OpsBrain agent pod
or on the underlying EC2 nodes in the EKS cluster.

## Symptoms
- Prometheus alert: `HighCPUUsage` firing for > 5 minutes
- API response times increasing (p99 > 2 s)
- Kubernetes HPA scaling pods faster than expected
- Users reporting slow or failed `/ask` requests

## Severity
**P2** — Investigate within 30 minutes. Escalate to P1 if user-facing error rate exceeds 5%.

---

## Diagnosis Steps

### 1. Identify the hot pod
```bash
kubectl top pods -n opsbrain --sort-by=cpu
kubectl top nodes
```

### 2. Check recent logs for the hot pod
```bash
kubectl logs -n opsbrain <pod-name> --tail=200 | grep -i "error\|timeout\|slow"
```

### 3. Check if a recent deployment caused the spike
```bash
kubectl rollout history deployment/<agent-name> -n opsbrain
```

### 4. Check Prometheus for the exact metric
```promql
rate(process_cpu_seconds_total{namespace="opsbrain"}[5m]) * 100
```

### 5. Check for slow database queries (if CPU is in the RAG agent)
Connect to the RDS instance and run:
```sql
SELECT query, calls, mean_exec_time, total_exec_time
FROM   pg_stat_statements
ORDER  BY total_exec_time DESC
LIMIT  10;
```

---

## Immediate Mitigation

### Option A: Scale out horizontally
```bash
kubectl scale deployment <agent-name> -n opsbrain --replicas=5
```

### Option B: Roll back the last deployment
```bash
kubectl rollout undo deployment/<agent-name> -n opsbrain
kubectl rollout status deployment/<agent-name> -n opsbrain
```

### Option C: Increase node capacity (if nodes are the bottleneck)
Update `eks_desired_nodes` in `infra/terraform/variables.tf` and apply:
```bash
terraform apply -var="eks_desired_nodes=4"
```

---

## Root Cause Analysis (post-incident)

After resolving the incident, investigate:

1. **Deployment delta** — diff the last two image tags in ECR
2. **Traffic pattern** — check Grafana "Requests per second" dashboard for anomalies
3. **Embedding batch size** — if the RAG ingestor was running, large batches block the event loop
4. **pgvector index** — a missing HNSW index causes a full table scan on every query

## Prevention
- Set CPU resource limits on every pod (already defined in `k8s/*.yaml`)
- Configure HPA: `kubectl autoscale deployment rag-agent --min=2 --max=10 --cpu-percent=70`
- Run the ingestor as a separate Kubernetes Job, not inline with the API server
- Add pgvector HNSW index after ingesting the first 100 documents

---

*Last updated: 2026-06-26 | Owner: Platform Engineering*
