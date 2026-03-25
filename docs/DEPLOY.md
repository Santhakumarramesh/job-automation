# Deployment runbook

Concise guide for running **FastAPI**, **Celery workers**, and optional **Streamlit** beyond local development.

## Processes

| Process | Entry | Notes |
|---------|--------|------|
| API | `uvicorn app.main:app --host 0.0.0.0 --port 8000` | Set `PYTHONPATH` to repo root if needed |
| Worker | `celery -A app.tasks:celery worker --loglevel=info` | Same Redis URLs as API ([WORKER_ORCHESTRATION.md](WORKER_ORCHESTRATION.md)) |
| Streamlit | `streamlit run run_streamlit.py` or project entrypoint | Calls API with optional Bearer / API key |

## Docker

**Image:** build from repo root: `docker build -t ccp-api:latest .`

- Default command runs **uvicorn** on port **8000** (installs `pip install ".[production]"` in the image).
- **Celery:** use the same image with a different command, e.g.  
  `docker run ... ccp-api:latest celery -A app.tasks:celery worker --loglevel=info`

**Compose (reference):** [docker-compose.yml](../docker-compose.yml) starts **Redis**, **API**, and **worker** with a shared volume for **SQLite** at `sqlite:////data/job_applications.db`.

1. Copy `.env.example` → `.env` and set at least `OPENAI_API_KEY`.
2. For a production-like gate, set `API_KEY` (or JWT / `M2M_API_KEY`), `APP_ENV=production`, and review [startup_checks.py](../services/startup_checks.py). The sample Compose defaults to `APP_ENV=development` so a blank auth `.env` still starts.
3. Run: `docker compose up --build`

See [PHASE_6_PLAN.md](PHASE_6_PLAN.md).

## Health and metrics

- **Liveness:** `GET /health` (or your platform’s TCP check on the API port).
- **Readiness:** `GET /ready` — confirm DB/Redis dependencies as implemented in `app/main.py`.
- **Metrics:** `GET /metrics` when `PROMETHEUS_METRICS=1` — see [OBSERVABILITY.md](OBSERVABILITY.md).

## Environment checklist (production)

Set `APP_ENV=production` (or rely on `STRICT_STARTUP=1`) and satisfy [startup_checks.py](../services/startup_checks.py):

1. **Auth:** At least one of `API_KEY`, JWT (`JWT_SECRET` and/or `JWT_JWKS_URL` / `JWT_ISSUER`), or `M2M_API_KEY`.
2. **Tracker:** `TRACKER_USE_DB=1` and `DATABASE_URL` (or `TRACKER_DATABASE_URL`) — SQLite or Postgres.
3. **CORS:** Not `*` unless you explicitly set `API_CORS_SKIP_WILDCARD_PROD_CHECK=1`.
4. **JWT (JWKS):** Prefer `JWT_AUDIENCE` when using `JWT_JWKS_URL` or `JWT_ISSUER`.
5. **Multi-tenant writes (optional):** `API_ENFORCE_USER_WORKSPACE_ON_WRITES=1` makes `POST /api/jobs` and LinkedIn batch apply (`POST /api/ats/apply-to-jobs`, `…/dry-run`) require that per-job (or batch default) `workspace_id` / `organization_id` matches the caller’s JWT / `X-Workspace-Id` workspace (admins exempt unless `API_WORKSPACE_ENFORCE_FOR_ADMIN=1`). See `services/workspace_write_guard.py`.
6. **LinkedIn ATS auth (optional):** `API_ATS_LINKEDIN_REQUIRE_AUTH=1` returns **401** for the anonymous `demo-user` on `POST /api/ats/confirm-easy-apply`, `POST /api/ats/apply-to-jobs`, and `POST /api/ats/apply-to-jobs/dry-run` — callers must send `X-API-Key`, `Authorization: Bearer`, or `X-M2M-API-Key`.
7. **GitHub Actions:** If you cannot push `.github/workflows/*.yml` (PAT missing **workflow** scope), copy [`contrib/github-actions-ci.yml`](../contrib/github-actions-ci.yml) into `.github/workflows/ci.yml` locally or in the GitHub UI.

Optional: `AWS_SECRETS_MANAGER_SECRET_ID` to merge secrets at startup ([SECRETS_AND_CONFIG.md](SECRETS_AND_CONFIG.md)).

## Database migrations

Tracker / idempotency / task-state schemas: follow [MIGRATIONS.md](MIGRATIONS.md) and run Alembic against the same `DATABASE_URL` the API uses.

## Multi-replica API and workers

### API horizontal scaling

The FastAPI app is **mostly stateless**: safe behind a load balancer with round-robin. Two important **per-process** behaviors:

| Concern | Behavior | Production guidance |
|--------|----------|---------------------|
| **Rate limits** | `services/rate_limit.py` keeps counters **in memory** per API process. | Prefer **ingress / WAF / API gateway** limits so all replicas share one budget. If you enable `API_RATE_LIMIT_ENABLED=1`, each pod enforces its own window — effective global budget ≈ `N × per_minute`. |
| **OIDC JWKS cache** | `app/auth.py` caches discovery / JWKS URL in-process (~1h TTL). | Normal: each pod warms its own cache. Ensure pods can reach `JWT_ISSUER` / `JWT_JWKS_URL` (egress). |

No sticky sessions are required for REST JSON APIs. **Streamlit** is different: one session per browser; scale with **one replica per “seat”** or put Streamlit behind auth and accept shared state carefully.

### Celery: one graph, many workers

All workers must share the **same** `REDIS_BROKER` (and usually `REDIS_BACKEND` if you use a result backend). Tasks are dequeued by any worker; **do not** point different deployments at different brokers unless you intend separate queues.

- **Concurrency:** tune `celery worker --concurrency` vs CPU and I/O (LLM, Playwright).
- **Idempotency / tracker / task state:** when `IDEMPOTENCY_USE_DB=1` or `TASK_STATE_BACKEND=db|s3`, all workers must use the **same** DB and object-store configuration as the API that enqueues jobs.

### Metrics across replicas

- **`GET /metrics`** (per API pod): process-local HTTP metrics; scrape **each** pod or use Prometheus Kubernetes SD.
- **Celery counters on `/metrics`:** when `PROMETHEUS_CELERY_REDIS=1` (or equivalent), Gauges reflect the **shared** Redis hash `ccp:metrics:celery` — any API replica’s scrape shows the same cumulative worker totals.

## LinkedIn / browser apply

Treat unattended browser apply as **operator-supervised**. See [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) and [APPLY_RECOVERY_PLAYBOOKS.md](APPLY_RECOVERY_PLAYBOOKS.md).
