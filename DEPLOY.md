# Career Co-Pilot Pro — Deployment Guide

Self-hosted, pilot, and production deployment reference.

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | 3.12 recommended |
| SQLite | built-in | default DB; swap for PostgreSQL via DATABASE_URL |
| Redis | optional | required for autonomy rollback gates and Celery broker |
| PostgreSQL | optional | recommended for multi-user production |
| Docker | optional | docker-compose.yml provided |

---

## Quick Start (local / single-user)

```bash
# 1. Clone and install
git clone https://github.com/Santhakumarramesh/career-co-pilot-pro.git
cd career-co-pilot-pro
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. Copy and fill profile
cp config/candidate_profile.example.json config/candidate_profile.json
# Edit config/candidate_profile.json with your details

# 3. Set required env vars (minimum)
export OPENAI_API_KEY=sk-...

# 4. Run database migrations
alembic upgrade head

# 5. Start the candidate UI (guided workflow)
streamlit run run_streamlit.py

# 6. (Optional) Start operator UI
APP_MODE=operator streamlit run run_streamlit.py
```

---

## Environment Variable Reference

### Required

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | OpenAI API key for LLM operations (resume tailoring, ATS scoring, cover letter) |

### Strongly Recommended

| Variable | Description | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key (used by some agents) | — |
| `APIFY_API_KEY` | Apify token for AI job search | — |
| `API_KEY` | X-API-Key for the FastAPI server | dev-only open if unset |
| `JWT_SECRET` | HS256 secret for JWT auth | — |
| `DATABASE_URL` | PostgreSQL DSN (e.g. `postgresql+asyncpg://...`) | SQLite fallback |
| `REDIS_BROKER` | Redis URL for Celery (`redis://localhost:6379/0`) | in-memory fallback |
| `REDIS_METRICS_URL` | Redis URL for apply metrics and rollback gates | gates disabled if unset |

### LinkedIn / Apply

| Variable | Description |
|---|---|
| `LINKEDIN_EMAIL` | LinkedIn account email (for career copilot MCP session) |
| `LINKEDIN_PASSWORD` | LinkedIn account password |
| `ATS_ALLOW_LINKEDIN_BROWSER` | Set to `1` to enable LinkedIn browser automation on REST API |

### Autonomy Gates (Phase 3)

| Variable | Description | Default |
|---|---|---|
| `AUTONOMY_LINKEDIN_LIVE_SUBMIT_DISABLED` | `1` = kill switch, block all live submits | off |
| `AUTONOMY_LINKEDIN_PILOT_SUBMIT_ONLY` | `1` = only pilot-flagged jobs can live-submit | off |
| `AUTONOMY_LINKEDIN_PILOT_USER_IDS` | Comma-separated user IDs allowed for live submit | — |
| `AUTONOMY_LINKEDIN_PILOT_WORKSPACE_IDS` | Comma-separated workspace IDs allowed for live submit | — |
| `AUTONOMY_LINKEDIN_ROLLBACK_WHEN_FAILURE_RATE_GTE` | Float 0–1; auto-rollback when failure rate exceeds threshold | off |
| `AUTONOMY_LINKEDIN_ROLLBACK_WHEN_NONSUBMIT_RATE_GTE` | Float 0–1; auto-rollback on high checkpoint/challenge rate | off |
| `TRUTH_APPLY_HARD_GATE` | `1` = block live apply if profile required fields are missing | off |

### UI / App Mode

| Variable | Description | Default |
|---|---|---|
| `APP_MODE` | `candidate` (guided UX) or `operator` (full cockpit) | `candidate` |
| `ALLOW_ENV_WRITE` | `1` = allow credential save to .env from UI (local only) | off |
| `TRACKER_DEFAULT_USER_ID` | User ID tag for Streamlit tracker rows | `streamlit-local` |
| `STREAMLIT_CAREER_API_BASE` | Base URL for FastAPI calls from Streamlit | `http://127.0.0.1:8000` |

### Auth (FastAPI server)

| Variable | Description |
|---|---|
| `JWT_SECRET` | HS256 signing secret |
| `JWT_JWKS_URL` | OIDC JWKS URL for RS256 (e.g. Auth0, Cognito) |
| `JWT_ISSUER` | OIDC issuer URL (triggers OIDC discovery) |
| `API_KEY_IS_ADMIN` | `1` = the X-API-Key bearer gets admin role |
| `M2M_API_KEY` | Machine-to-machine API key for service identity |

### Object Storage (artifacts)

| Variable | Description |
|---|---|
| `OBJECT_STORAGE_BACKEND` | `s3`, `gcs`, or `local` (default: `local`) |
| `S3_BUCKET` | S3 bucket name |
| `S3_REGION` | AWS region |
| `AWS_ACCESS_KEY_ID` | AWS credentials |
| `AWS_SECRET_ACCESS_KEY` | AWS credentials |

---

## Running the API Server

```bash
# Development
uvicorn app.main:app --reload --port 8000

# Production
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

OpenAPI docs: http://localhost:8000/docs

---

## Running Celery Workers

Redis is required for the Celery broker:

```bash
export REDIS_BROKER=redis://localhost:6379/0

# Start worker
celery -A app.tasks worker --loglevel=info --concurrency=4

# Start beat scheduler (follow-ups, digests)
celery -A app.tasks beat --loglevel=info
```

---

## Database Setup

```bash
# Run migrations (SQLite default, or set DATABASE_URL for PostgreSQL)
alembic upgrade head

# Verify
alembic current
```

---

## Docker Compose

```bash
# Start all services (API, Celery, Redis, Streamlit)
docker-compose up -d

# View logs
docker-compose logs -f api
docker-compose logs -f worker
```

---

## Prometheus Metrics

The FastAPI app exposes Prometheus metrics at `/metrics`.

Example scrape config (`prometheus.yml`):

```yaml
scrape_configs:
  - job_name: career_copilot
    static_configs:
      - targets: ["localhost:8000"]
    metrics_path: /metrics
    scrape_interval: 15s
```

Key metrics:
- `linkedin_live_submit_attempt_total` — live submit attempts
- `linkedin_live_submit_success_total` — successful live submits
- `celery_tasks_total` — Celery task counts by state

---

## Redis Setup for Autonomy Rollback Gates

If you want the Phase 3 autonomy rollback gates to work:

```bash
# Start Redis
redis-server

# Set env vars
export REDIS_METRICS_URL=redis://localhost:6379/1
export REDIS_BROKER=redis://localhost:6379/0

# Enable rollback at 30% failure rate (optional)
export AUTONOMY_LINKEDIN_ROLLBACK_WHEN_FAILURE_RATE_GTE=0.30
```

If `REDIS_METRICS_URL` is unset, the rollback gates are silently skipped (no error, but no auto-rollback protection either). A startup warning is shown if rollback env vars are set but Redis is unavailable.

---

## LinkedIn MCP Session Setup

For the Career Co-Pilot MCP (`apply_to_jobs`, `search_jobs`):

1. Ensure `LINKEDIN_EMAIL` and `LINKEDIN_PASSWORD` are set in your Claude Desktop config (`claude_desktop_config.json`)
2. Open `https://www.linkedin.com` in a browser
3. Complete any verification challenge (SMS code, email code, or captcha)
4. The session cookie is saved to the MCP session store
5. Run `confirm_easy_apply` in Claude Desktop — should return `status: ok`

If `confirm_easy_apply` returns `login_challenge`, the session needs re-verification (step 2–4 above).

---

## Startup Checks

The app runs `services/startup_checks.py` at boot. It validates:
- Profile JSON exists and is parseable
- Required env vars are present (warns if missing)
- Database is reachable

To run manually:

```bash
python3 -c "from services.startup_checks import run_startup_checks; run_startup_checks('manual')"
```

---

## Multi-User / SaaS Deployment Notes

- Set `API_KEY` and `JWT_SECRET` (or `JWT_JWKS_URL` for OIDC) — the API runs in open demo mode if both are unset
- Set `DATABASE_URL` to a PostgreSQL DSN — SQLite is single-writer and not suitable for concurrent users
- Do **not** set `ALLOW_ENV_WRITE=1` in production — credential writes from the UI are for local development only
- Use `workspace_id` scoping on all API calls — `workspace_write_guard.py` enforces this
- Deploy the Streamlit UI as `APP_MODE=candidate` for end users; `APP_MODE=operator` for internal team

---

*Career Co-Pilot Pro · DEPLOY.md · Phase 10 · 2026-03-26*
