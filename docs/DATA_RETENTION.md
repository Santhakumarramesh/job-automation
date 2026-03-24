# Data retention and on-disk artifacts (Phase 4.4.1)

The application **does not** ship a unified garbage collector. Operators own retention: rotate, truncate, delete, or move data using the paths and env vars below. This doc lists **defaults** and **toggles** so you can plan backups and compliance.

---

## Summary table

| Artifact | Default location / key | Primary env vars | App-enforced expiry |
|----------|------------------------|------------------|---------------------|
| Audit JSONL | `application_audit.jsonl` (project root) | `AUDIT_LOG_PATH` | None — grows until rotated |
| Celery task snapshots | `data/task_state/*.json` | `TASK_STATE_DIR`, `TASK_STATE_MAX_BYTES` | None per file — trim only on write |
| Idempotency (file mode) | `data/idempotency/*.json` | `IDEMPOTENCY_DIR`, `IDEMPOTENCY_TTL_HOURS` | **Lookup** drops stale keys; files may linger until read |
| Idempotency (DB mode) | Table `job_idempotency` | `IDEMPOTENCY_USE_DB`, same TTL hours | Stale rows removed on **lookup**; periodic SQL cleanup optional |
| Idempotency keys (Redis path) | N/A (not Redis today) | — | — |
| Redis Celery metrics | Hash `ccp:metrics:celery` | `CELERY_METRICS_REDIS`, `REDIS_*` | None — reset via ops / `reset_celery_metrics` (tests/admin tooling) |
| Tracker DB | SQLite file or Postgres | `DATABASE_URL`, `TRACKER_DATABASE_URL`, `TRACKER_USE_DB` | Application data — **your** backup / retention policy |
| S3 artifacts | Per bucket prefix | `ARTIFACTS_S3_BUCKET`, etc. | **Bucket lifecycle** — see [OBJECT_STORAGE.md](OBJECT_STORAGE.md) |

---

## Audit log (`services/observability.py`)

- Append-only JSON lines: `celery_task_started`, `celery_task_finished`, and other `audit_log` calls.
- **Rotation:** use `logrotate`, sidecar agent, or ship to a log platform and truncate local files on a schedule.
- **PII:** lines may include `user_id`, `job_name`, and error snippets — treat as sensitive in production.

---

## Task state files (`services/task_state_store.py`)

- One JSON file per Celery `task_id` under `TASK_STATE_DIR` (default `data/task_state`).
- Payloads are trimmed (`TASK_STATE_MAX_BYTES` caps written size) but files accumulate for every finished task until deleted.
- **Cleanup:** cron `find data/task_state -mtime +N -delete` (tune **N**) or equivalent.

---

## Idempotency

- **File mode:** `IDEMPOTENCY_DIR` (default `data/idempotency`). TTL is enforced when **lookup** runs; orphan files after TTL are removed only when that key is queried again.
- **DB mode:** rows expire logically by TTL on access; for dense traffic, add a scheduled `DELETE FROM job_idempotency WHERE created_at < now() - interval '…'` if you need strict disk bounds.

---

## Prometheus and metrics

- **`GET /metrics`** is scrape-only; no historical retention in-app.
- **Redis** aggregate hash grows by counter keys only (bounded field set) — not unbounded, but no TTL on the hash.

---

## Related

- [OBSERVABILITY.md](OBSERVABILITY.md) — audit, Redis metrics, Prometheus  
- [WORKER_ORCHESTRATION.md](WORKER_ORCHESTRATION.md) — idempotency, task state  
- [OBJECT_STORAGE.md](OBJECT_STORAGE.md) — S3 lifecycle and presigned URLs  
- [SECRETS_AND_CONFIG.md](SECRETS_AND_CONFIG.md) — env overview  
