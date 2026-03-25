# Phase 6: Container packaging

**Goal:** Ship a reproducible **API + worker** image and a **reference Compose** stack for demos and small deployments.

**Prerequisite:** [Phase 5](PHASE_5_PLAN.md) runbooks and production checks.

---

## Phase 6.1 — Docker image

| Milestone | Deliverable |
|-----------|-------------|
| 6.1.1 | Root **`Dockerfile`** — `pip install ".[production]"`, default `CMD` uvicorn `app.main:app` ✅ |
| 6.1.2 | **`.dockerignore`** — smaller build context (exclude `tests/`, `docs/`, `scripts/`, caches) ✅ |

---

## Phase 6.2 — Compose reference

| Milestone | Deliverable |
|-----------|-------------|
| 6.2.1 | **`docker-compose.yml`** — Redis, API, Celery worker, shared volume for SQLite tracker ✅ |
| 6.2.2 | Env via Compose `${VAR}` substitution from project **`.env`** (including Phase 5 speed-mode knobs) — see [DEPLOY.md](DEPLOY.md#docker) ✅ |

---

## Out of scope (optional later)

- **Playwright / apply** in image — use a derived Dockerfile `pip install ".[apply]"` + `playwright install` (large).
- **Postgres service** in Compose — operator adds `postgres:` + `DATABASE_URL=postgresql://…` (see [MIGRATIONS.md](MIGRATIONS.md)).
- **Streamlit** service — add a service with `streamlit run run_streamlit.py` if you need UI in Compose.

---

## Related docs

- [DEPLOY.md](DEPLOY.md) — Docker usage, prod vs demo env  
- [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md)  
- [PHASE_7_PLAN.md](PHASE_7_PLAN.md) — Quality gates + performance telemetry
