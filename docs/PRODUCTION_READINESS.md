# Production Readiness

## Current status: **API + workers deployable with discipline; auto-apply remains higher risk**

| Aspect | Status | Notes |
|--------|--------|------|
| Architecture | ✅ Good | Modular UI, `services/`, FastAPI `app/`, agents |
| Prototype completeness | ✅ Good | Real MCP, fit gate, ATS, autofill engine |
| Hosted API / tracker / workers | ✅ Good | Auth (API key, JWT HS256 or OIDC JWKS, M2M), startup gates, metrics hooks — see [PHASE_5_PLAN.md](PHASE_5_PLAN.md), [DEPLOY.md](DEPLOY.md) |
| Reliability for live auto-apply | ⚠️ Medium | LinkedIn Easy Apply works; external ATS fragile; login checkpoints |
| “Hands-off” production for browser apply | ❌ Not guaranteed | Treat as operator-supervised; see Known gaps |

## Enforced at startup (`APP_ENV=production` or `STRICT_STARTUP=1`)

| Check | Behavior |
|--------|----------|
| Auth | At least one of `API_KEY`, JWT (`JWT_SECRET` / `JWT_JWKS_URL` / `JWT_ISSUER`), or `M2M_API_KEY` in production so the API is not demo-open (`services/startup_checks.py`). |
| Tracker | **`TRACKER_USE_DB=1`** required for `app`, `worker`, and `streamlit` contexts in production or strict mode — use SQLite (`DATABASE_URL=sqlite:///./job_applications.db`) or Postgres. |
| Demo admin | `DEMO_USER_IS_ADMIN` forbidden when `APP_ENV=production`. |

Install common production extras: `pip install -e ".[production]"` (Postgres driver, JWT, Alembic/SQLAlchemy, boto3, Prometheus client). For MCP + Playwright apply flows: `pip install -e ".[apply]"`. **Containers:** root `Dockerfile` + `docker-compose.yml` — [DEPLOY.md](DEPLOY.md#docker), [PHASE_6_PLAN.md](PHASE_6_PLAN.md).

Packages shipped in the wheel/sdist include `app`, `agents`, `services`, `providers`, `ui`, `mcp_servers`, `dashboard`, `config` (`pyproject.toml` `[tool.setuptools.packages.find]`).

## Hard backend rules (enforced in code)

Auto-apply **only** proceeds when all of these are met:

1. **Easy Apply only** — `apply_to_jobs` rejects non–Easy Apply unless `manual_assist=True`
2. **Fit decision = Apply** — When metadata provided, job must have `fit_decision=Apply`
3. **ATS ≥ threshold** — When metadata provided, `ats_score >= 85`
4. **No unsupported requirements** — When metadata provided, `unsupported_requirements` must be empty
5. **External ATS = manual-assist** — Greenhouse/Lever/Workday not auto-submitted; engine skips them by default

## API rate limiting (optional)

Set `API_RATE_LIMIT_ENABLED=1` for a per-client sliding window on the FastAPI process (`services/rate_limit.py`). Exempt paths include `/health`, `/ready`, `/metrics`, and OpenAPI UI routes. Prefer **ingress / WAF limits** when running multiple API replicas (in-memory counts are not shared). With `APP_ENV=production`, startup warns if in-app rate limiting is off unless you set `API_RATE_LIMIT_SKIP_STARTUP_WARN=1` (after confirming edge limits).

**Versioned base URL:** the same routes are mounted at `/api` and `/api/v1` by default. Set `API_V1_DUPLICATE_ROUTES=0` to expose only `/api` (slimmer OpenAPI).

**CORS:** set `API_CORS_ORIGINS` to a comma-separated allowlist (or `*` for local dev only). Unset = no CORS middleware (`services/api_cors.py`). **`API_CORS_ORIGINS=*` is rejected at startup when `APP_ENV=production`** unless `API_CORS_SKIP_WILDCARD_PROD_CHECK=1`.

## Known gaps

1. **Easy Apply truthfulness** — `easy_apply_confirmed` (MCP) vs `easy_apply_filter_used` (search filter).
2. **External ATS autofill** — Workday/Greenhouse/Lever forms vary; heuristic fill is prototype-only. Use manual-assist.
3. **Login automation risk** — LinkedIn checkpoint/challenge pages can break the flow.
4. **Dry run first** — Recommended: run with `dry_run=True` before live submit.

## Before trusting for live applying

- Run at least one `dry_run=True` pass
- Confirm Easy Apply jobs only (from export)
- Monitor for LinkedIn verification prompts
- Treat external ATS as manual-assist only
