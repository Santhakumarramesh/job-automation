# Phase 3: Multi-User Production

**Goal:** Production-ready multi-user operation.

**Prerequisite:** Phase 2 complete ✅

---

## Phase 3.1 — Auth & users

| Milestone | Deliverable |
|-----------|-------------|
| 3.1.1 | OAuth2 / OpenID Connect (Auth0, Clerk, Supabase) — future |
| 3.1.2 | User binding — `user_id` on tracker rows; `GET /api/applications` scoped; Celery payload ✅ |
| 3.1.3 | JWT validation — `JWT_SECRET` + `Authorization: Bearer` (HS256) ✅ |
| 3.1.4 | Role checks — `User.roles`, `is_admin`, `require_admin`, `GET /api/admin/applications` ✅ |

**JWT:** Set `JWT_SECRET`, install `pip install .[auth]` (PyJWT). Optional `JWT_ALGORITHM` (default `HS256`). Token must include `sub` or `user_id`.

## Phase 3.2 — Database scale-out

| Milestone | Deliverable |
|-----------|-------------|
| 3.2.1 | Postgres tracker via `TRACKER_DATABASE_URL` or `DATABASE_URL` + `pip install .[postgres]` ✅ |
| 3.2.2 | Schema migrations (Alembic) — `alembic/`, `pip install .[migrations]`, see `docs/MIGRATIONS.md` ✅ |
| 3.2.3 | Artifacts metadata in DB — `artifacts_manifest` column + `GET /api/applications/by-job/{job_id}` ✅ |
| 3.2.4 | Postgres `ThreadedConnectionPool` (`TRACKER_PG_POOL`, min/max) ✅; `TRACKER_PG_POOL=0` for single-conn mode |

## Phase 3.3 — Worker & orchestration

| Milestone | Deliverable |
|-----------|-------------|
| 3.3.1 | Celery runs headless LangGraph (`agents/celery_workflow.py`); `CELERY_USE_LANGGRAPH=0` fallback ✅ |
| 3.3.2 | Retries w/ backoff (`CELERY_TASK_MAX_RETRIES`); API **`idempotency_key`** + file store (`docs/WORKER_ORCHESTRATION.md`) ✅ |
| 3.3.3 | Task snapshots — `services/task_state_store.py` + `?include_task_state=true` (filesystem; not DB) ✅ / DB 📋 |
| 3.3.4 | **`failure_class`** transient/permanent on errors + `save_task_failure`; metrics/alerts 📋 |

## Phase 3.4 — Artifacts & storage

| Milestone | Deliverable |
|-----------|-------------|
| 3.4.1 | Optional S3 upload after Celery `save_documents`; `artifacts_manifest.s3` keys ✅ |
| 3.4.2 | Presigned GET URLs — `?signed_urls=true` on by-job application endpoints ✅ |
| 3.4.3 | Retention / lifecycle — operator-owned (S3 bucket policies); see `docs/OBJECT_STORAGE.md` 📋 |
| — | GCS native client — future 📋 |

Install: `pip install .[s3]`. Doc: [OBJECT_STORAGE.md](OBJECT_STORAGE.md).

## Phase 3.5 — Secrets & config

| Milestone | Deliverable |
|-----------|-------------|
| 3.5.1 | `APP_ENV` / `STRICT_STARTUP`; production fatal checks; `collect_startup_report()` ✅ |
| 3.5.2 | Optional **AWS Secrets Manager** JSON → `os.environ` (`services/secrets_loader.py`) ✅ |
| 3.5.3 | Streamlit runs `run_startup_checks("streamlit")` in `run_streamlit.py` ✅ |

Doc: [SECRETS_AND_CONFIG.md](SECRETS_AND_CONFIG.md).

## Phase 3.6 — Observability (extended)

| Milestone | Deliverable |
|-----------|-------------|
| 3.6.1 | Celery audit events + `career_co_pilot.celery` logs with duration/outcome ✅ |
| 3.6.2 | Redis aggregate metrics (`CELERY_METRICS_REDIS`) + `GET /api/admin/metrics/summary` ✅ |
| 3.6.3 | Optional Prometheus `GET /metrics` + `ccp_http_requests_total` (`pip install .[metrics]`, `PROMETHEUS_METRICS=1`) ✅ |
| 3.6.4 | Dashboards / PagerDuty-style hooks | 📋 operator-owned |

Doc: [OBSERVABILITY.md](OBSERVABILITY.md).

---

## Execution order

1. **3.1** Auth  
2. **3.2** Postgres / migrations  
3. **3.4** Artifacts (parallel with 3.2)  
4. **3.3** Worker unification  
5. **3.5** Secrets  
6. **3.6** Observability  

## Out of scope

Multi-tenant billing, white-label, deep ATS integrations beyond current providers.
