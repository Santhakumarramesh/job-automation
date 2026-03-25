# Data retention and on-disk artifacts (Phase 4.4.1)

The application **does not** ship a unified garbage collector. Operators own retention: rotate, truncate, delete, or move data using the paths and env vars below. This doc lists **defaults** and **toggles** so you can plan backups and compliance.

---

## Summary table

| Artifact | Default location / key | Primary env vars | App-enforced expiry |
|----------|------------------------|------------------|---------------------|
| Audit JSONL | `application_audit.jsonl` (project root) | `AUDIT_LOG_PATH` | None — grows until rotated |
| Celery task snapshots | `data/task_state/*.json`, or table `task_state_snapshots`, or S3 prefix | `TASK_STATE_BACKEND`, `TASK_STATE_DIR`, `TASK_STATE_S3_*`, `TASK_STATE_MAX_BYTES` | None — trim only on write; DB/S3 need your TTL policy |
| Idempotency (file mode) | `data/idempotency/*.json` | `IDEMPOTENCY_DIR`, `IDEMPOTENCY_TTL_HOURS` | **Lookup** drops stale keys; files may linger until read |
| Idempotency (DB mode) | Table `job_idempotency` | `IDEMPOTENCY_USE_DB`, same TTL hours | Stale rows removed on **lookup**; periodic SQL cleanup optional |
| Idempotency keys (Redis path) | N/A (not Redis today) | — | — |
| Redis Celery metrics | Hash `ccp:metrics:celery` | `CELERY_METRICS_REDIS`, `REDIS_*` | None — reset via ops / `reset_celery_metrics` (tests/admin tooling) |
| Metrics webhook cooldown | `data/.metrics_alert_last_sent` | `METRICS_ALERT_COOLDOWN_SECONDS`, `scripts/metrics_webhook_alert.py` | File timestamp only — safe to delete to force next alert |
| Tracker DB | SQLite file or Postgres | `DATABASE_URL`, `TRACKER_DATABASE_URL`, `TRACKER_USE_DB` | Application data — **your** backup / retention policy |
| S3 artifacts | Per bucket prefix | `ARTIFACTS_S3_BUCKET`, etc. | **Bucket lifecycle** — see [OBJECT_STORAGE.md](OBJECT_STORAGE.md#example-expire-old-artifact-objects-aws-s3) |

---

## Audit log (`services/observability.py`)

- Append-only JSON lines: `celery_task_started`, `celery_task_finished`, and other `audit_log` calls.
- **Rotation:** use `logrotate`, sidecar agent, or ship to a log platform and truncate local files on a schedule.
- **PII:** lines may include `user_id`, `job_name`, and error snippets — treat as sensitive in production.

---

## Task state (`services/task_state_store.py`)

- **File (default):** one JSON file per Celery `task_id` under `TASK_STATE_DIR` (default `data/task_state`). **Cleanup:** cron `find data/task_state -mtime +N -delete` (tune **N**) or equivalent.
- **DB** (`TASK_STATE_BACKEND=db`): rows in `task_state_snapshots` (same SQLite/Postgres URL as tracker). Postgres: run Alembic `tracker_0006` (SQLite creates the table on first write).
- **S3** (`TASK_STATE_BACKEND=s3`): objects under `TASK_STATE_S3_PREFIX` (default `task_state/`); bucket from `TASK_STATE_S3_BUCKET` or `ARTIFACTS_S3_BUCKET`. Use bucket lifecycle rules like other artifacts.
- Payloads are trimmed (`TASK_STATE_MAX_BYTES` caps written size) but data accumulates until you delete or expire it.

---

## Idempotency

- **File mode:** `IDEMPOTENCY_DIR` (default `data/idempotency`). TTL is enforced when **lookup** runs; orphan files after TTL are removed only when that key is queried again.
- **DB mode:** rows expire logically by TTL on access; for dense traffic, add a scheduled `DELETE FROM job_idempotency WHERE created_at < now() - interval '…'` if you need strict disk bounds.

---

## Prometheus and metrics

- **`GET /metrics`** is scrape-only; no historical retention in-app.
- **Redis** aggregate hash grows by counter keys only (bounded field set) — not unbounded, but no TTL on the hash.

---

## Subject access / erasure (Phase 4.4.2)

Admin API (requires admin role): export JSON for one `user_id` via `GET /api/admin/applications/export`, and remove tracker rows (and matching `job_idempotency` when `IDEMPOTENCY_USE_DB=1`) via `DELETE /api/admin/applications/by-user` with `confirm_user_id` matching `user_id`. This does **not** delete S3 objects, audit JSONL lines, or task-state files — handle those separately if required.

## Related

- [OBSERVABILITY.md](OBSERVABILITY.md) — audit, Redis metrics, Prometheus  
- [WORKER_ORCHESTRATION.md](WORKER_ORCHESTRATION.md) — idempotency, task state  
- [OBJECT_STORAGE.md](OBJECT_STORAGE.md) — S3 lifecycle and presigned URLs  
- [SECRETS_AND_CONFIG.md](SECRETS_AND_CONFIG.md) — env overview  
