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
- **Default storage:** **`data/idempotency/`** (override with **`IDEMPOTENCY_DIR`**). File-backed; not safe for high-concurrency multi-host.
- **Phase 4.2 — DB storage:** set **`IDEMPOTENCY_USE_DB=1`**. Uses the tracker database (`DATABASE_URL` / `TRACKER_DATABASE_URL`). **Postgres** requires **`TRACKER_USE_DB=1`** (same as the application tracker). **SQLite** works with `DATABASE_URL=sqlite:///…` or the default `job_applications.db`. Table **`job_idempotency`** is created on first use (Postgres: run **`alembic upgrade head`** for `tracker_0005`). The DB path **inserts before `apply_async`**, so duplicate keys do not spawn duplicate Celery tasks across API replicas.

## Job status API

- `GET /api/jobs/{job_id}` — `status` from Celery.
- `?include_result=true` — result dict when the task has finished successfully (or error payload).
- `?include_task_state=true` — last filesystem snapshot.

## Stuck tasks / worker visibility (Phase 4.2.3)

- **Admin API:** `GET /api/admin/celery/inspect?timeout=2` — Celery `control.inspect`: `ping`, `active`, `reserved`, `scheduled`, `stats`. Requires admin auth; API must use the same broker as workers. **Null** / empty sections usually mean no worker answered (workers down, wrong `REDIS_BROKER`, or inspect timeout too low).
- **Disable:** set `CELERY_ADMIN_INSPECT=0` on the API to return **403** (avoid broker load in sensitive environments).
- **Default timeout:** `CELERY_INSPECT_TIMEOUT` (default `2.0` seconds) or query param `timeout`.
- **Per job:** if `GET /api/jobs/{id}` stays `PENDING` for a long time, workers may not be consuming — check inspect `active` / worker logs / Redis queue depth (operator tooling).

## Future (not done here)

- Postgres-backed **checkpoints** for task state (idempotency DB is done — see above)
- Push **failure_class** to metrics/alerting (PagerDuty, SNS, …)
- Full parity with Streamlit graph (iterative ATS, fit gate branching)
