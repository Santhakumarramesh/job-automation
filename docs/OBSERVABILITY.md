# Observability (Phase 3.6)

For **retention** of audit files, task-state JSON, idempotency stores, and related paths, see [DATA_RETENTION.md](DATA_RETENTION.md).

## Audit log (JSONL)

`services/observability.audit_log` appends to **`AUDIT_LOG_PATH`** (default `application_audit.jsonl`).

Celery lifecycle actions:

| Action | When |
|--------|------|
| `celery_task_started` | Task begins |
| `celery_task_finished` | Terminal outcome: `success`, `rejected`, or `error` |

Each `celery_task_finished` line includes `duration_sec`, `user_id`, `job_name`, and optional `failure_class` (`transient` / `permanent`).

## Structured logs

- **`LOG_JSON=1`** — JSON lines on the root logger (`services/observability.configure_structured_logging`).
- **`LOG_LEVEL`** — default `INFO`.
- Celery emits `career_co_pilot.celery` INFO lines with duration and outcome.

## Redis metrics (cross-worker)

Enable on **workers** with:

```bash
export CELERY_METRICS_REDIS=1
# optional: dedicated URL (else REDIS_BROKER is used)
# export REDIS_METRICS_URL=redis://localhost:6379/0
```

Counters live in Redis hash **`ccp:metrics:celery`**, including:

- `tasks_total`, `tasks_success_total`, `tasks_rejected_total`, `tasks_error_total`
- `tasks_error_transient`, `tasks_error_permanent` (when applicable)
- `task_duration_seconds_sum`, `task_duration_count` → average duration

**Admin API** (requires admin role):

`GET /api/admin/metrics/summary`

Returns JSON with `fields` from Redis or `enabled: false` if not configured.

> **Prefork:** each worker process updates the same Redis keys — aggregation is correct. Intermediate **retries** do not increment terminal counters until the final outcome.

## Prometheus (API process)

```bash
pip install .[metrics]
export PROMETHEUS_METRICS=1
```

- **`GET /metrics`** — Prometheus text (Python + `ccp_http_requests_total` with grouped paths).
- **Celery counters (Phase 4.3):** when workers use `CELERY_METRICS_REDIS=1`, set the same on the API **or** `PROMETHEUS_CELERY_REDIS=1` so `/metrics` exposes **`ccp_celery_*`** Gauges mirrored from Redis hash `ccp:metrics:celery` on each scrape. Use `increase()` / `rate()` in PromQL (Gauges reflect cumulative Redis values). Set `PROMETHEUS_CELERY_REDIS=0` to omit the bridge while keeping `CELERY_METRICS_REDIS=1` for the admin JSON API.
- Restrict access at the load balancer / mesh in production.

## Alerting

Not built-in. Point your stack at:

- JSONL audit file (e.g. ship to OpenSearch / CloudWatch Logs)
- Redis metrics (poll `GET /api/admin/metrics/summary` or read the hash from monitoring)
- Prometheus scrape of `/metrics`

Raise alerts on spikes in `tasks_error_*` or `tasks_rejected_total` / sustained latency via `avg_duration_seconds`.

**Example PromQL** (after Celery Redis bridge is enabled on `/metrics`; tune windows for your scrape interval):

```text
# Error share over 30m (Gauge mirrors — use increase)
  increase(ccp_celery_tasks_error_total[30m])
/ increase(ccp_celery_tasks_total[30m]) > 0.25

# Permanent failures picking up
increase(ccp_celery_tasks_error_permanent_total[1h]) > 3

# Avg duration from sum/count mirrors
  (ccp_celery_task_duration_seconds_sum - ccp_celery_task_duration_seconds_sum offset 1h)
/ (ccp_celery_task_duration_count - ccp_celery_task_duration_count offset 1h) > 120
```
