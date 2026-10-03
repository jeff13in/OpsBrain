# Runbook: PostgreSQL Connection Pool Exhaustion

## Overview
Covers the scenario where the RAG agent (or any agent) exhausts the PostgreSQL
connection pool, causing new requests to queue or fail with `FATAL: too many connections`.

## Symptoms
- API errors: `500 — FATAL: remaining connection slots are reserved`
- Prometheus alert: `PostgresConnectionsNearLimit`
- RAG agent health check returns 500
- Grafana shows `pg_stat_activity.count` near `max_connections`

## Severity
**P1** — Investigate immediately. All agent reads/writes are blocked.

---

## Diagnosis

### 1. Count active connections
```sql
SELECT count(*), state, wait_event_type, wait_event
FROM   pg_stat_activity
GROUP  BY state, wait_event_type, wait_event
ORDER  BY count DESC;
```

### 2. Find long-running queries holding connections
```sql
SELECT pid, now() - pg_stat_activity.query_start AS duration, query, state
FROM   pg_stat_activity
WHERE  (now() - pg_stat_activity.query_start) > interval '30 seconds'
ORDER  BY duration DESC;
```

### 3. Check what `max_connections` is set to
```sql
SHOW max_connections;
```

### 4. Check the agent logs for connection errors
```bash
kubectl logs -n opsbrain deployment/rag-agent --tail=100 | grep -i "connection\|pool"
```

---

## Immediate Mitigation

### Option A: Kill idle/idle-in-transaction connections
```sql
SELECT pg_terminate_backend(pid)
FROM   pg_stat_activity
WHERE  state IN ('idle', 'idle in transaction')
  AND  query_start < now() - interval '5 minutes';
```

### Option B: Restart the affected agent pod (forces connection close)
```bash
kubectl rollout restart deployment/rag-agent -n opsbrain
```

### Option C: Deploy PgBouncer as a connection pooler
Add a PgBouncer sidecar or a separate deployment to pool connections before
they reach RDS. This is the permanent fix for connection saturation.

---

## Root Cause Analysis

The most common causes in this codebase:

1. **No connection pooling** — the RAG agent opens a new `psycopg2` connection
   per request and closes it at the end. Under load, connections pile up faster
   than Postgres recycles them. **Fix:** use `psycopg2.pool.ThreadedConnectionPool`
   or switch to `asyncpg` with an async pool.

2. **Leaked connections** — an unhandled exception exits the request handler
   before `conn.close()` is called. **Fix:** use `with` context managers for
   all connections.

3. **Ingestor running concurrently** — the ingestor opens its own connection
   while the API is serving requests. **Fix:** run ingestion as a separate Job
   or add a semaphore.

## Prevention
- Add `max_connections` monitoring alert at 80% threshold
- Use a connection pool (PgBouncer or `psycopg2.pool`) from the start
- Set `statement_timeout = '30s'` on the database to kill runaway queries
- Use `WITH` blocks for all psycopg2 connections:
  ```python
  with psycopg2.connect(...) as conn:
      with conn.cursor() as cur:
          cur.execute(...)
  ```

---

*Last updated: 2026-06-26 | Owner: Platform Engineering*
