# Worker orchestration (Phase 3.3)

## LangGraph + Celery

- **Graph:** `agents/celery_workflow.py` — headless `StateGraph` with the same linear agent steps as the legacy Celery pipeline.
- **Task:** `app.tasks.run_job` invokes `graph.stream(..., stream_mode="values")` by default.
- **Disable graph:** set `CELERY_USE_LANGGRAPH=0` to use the previous sequential Python calls (fallback).

## Retries

- Env **`CELERY_TASK_MAX_RETRIES`** (default `3`).
- **Automatic retry** with exponential backoff for: `ConnectionError`, `TimeoutError`, `OSError`, and (when `openai` is installed) `RateLimitError`.
- Other errors return `{"status": "error", "failure_class": "permanent"|"transient", ...}` after retries are exhausted.

## Task state on disk

- **`services/task_state_store.py`** writes trimmed snapshots under `data/task_state/{task_id}.json` as the graph streams and on completion/failure.
- Override dir: **`TASK_STATE_DIR`**. Max file size: **`TASK_STATE_MAX_BYTES`** (default `800000`).
- API: `GET /api/jobs/{job_id}?include_task_state=true` (authenticated).

## Idempotent enqueue

- Request body: **`idempotency_key`** (optional string, max 200 chars), or HTTP header **`Idempotency-Key`** (same limits). If both are sent, they must be identical.
- Same **`user_id` + idempotency_key** within **`IDEMPOTENCY_TTL_HOURS`** (default 24) returns the existing Celery task id without enqueueing again.
- Storage: **`data/idempotency/`** (override with **`IDEMPOTENCY_DIR`**). File-backed; not safe for high-concurrency multi-host without Redis.

## Job status API

- `GET /api/jobs/{job_id}` — `status` from Celery.
- `?include_result=true` — result dict when the task has finished successfully (or error payload).
- `?include_task_state=true` — last filesystem snapshot.

## Future (not done here)

- Postgres-backed idempotency + checkpoints
- Push **failure_class** to metrics/alerting (PagerDuty, SNS, …)
- Full parity with Streamlit graph (iterative ATS, fit gate branching)
