# Observability (Phase 3.6)

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
- Restrict access at the load balancer / mesh in production.

## Alerting

Not built-in. Point your stack at:

- JSONL audit file (e.g. ship to OpenSearch / CloudWatch Logs)
- Redis metrics (poll `GET /api/admin/metrics/summary` or read the hash from monitoring)
- Prometheus scrape of `/metrics`

Raise alerts on spikes in `tasks_error_*` or `tasks_rejected_total` / sustained latency via `avg_duration_seconds`.
