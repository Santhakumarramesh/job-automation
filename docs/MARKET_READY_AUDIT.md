# Career Co-Pilot Pro — Market-Ready Audit
**Date:** 2026-03-26
**Auditor:** Session code review (all layers: services/, agents/, app/, ui/, tests/, docs/)
**Scope:** Full repo read — backend, auth, safety gates, observability, UI, tests, docs, autonomy model

---

## Overall Score: 7.8 / 10

> **Verdict:** The repo is technically credible, policy-sound, and operator-ready. It is market-ready for pilots, early adopters, and technical customers. It is not yet market-ready as a broadly accessible end-user SaaS — primarily due to UI complexity and the LinkedIn session auth gap in the MCP layer. No critical architectural rework is needed. The remaining gap is productization, not engineering.

---

## Score by Category

| Category | Score | Status |
|---|---|---|
| Backend Architecture | 9 / 10 | Production-grade |
| Safety & Policy Model | 9.5 / 10 | Exceptional |
| Auth & Multi-tenancy | 8.5 / 10 | Strong |
| Observability & Telemetry | 8.5 / 10 | Strong |
| Test Coverage | 8 / 10 | Solid |
| Decision Layer (state machine) | 9 / 10 | Production-grade |
| Autonomy Phase Maturity | 7.5 / 10 | Phase 1-2 live; Phase 3 env-gated |
| Documentation | 8.5 / 10 | Thorough |
| UI / UX | 5.5 / 10 | Needs split |
| Live Application Reliability | 6 / 10 | LinkedIn session gap blocks MCP apply |
| Productization / Packaging | 6.5 / 10 | Strong internals, packaging not finished |

---

## Category Breakdown

---

### 1. Backend Architecture — 9 / 10

**What is there:**
- FastAPI app (app/main.py) with proper lifespan handler, structured OpenAPI tags for 7 route groups: service, jobs, applications, insights, ats, follow-ups, admin
- Celery background job enqueue (app/tasks.py) for async apply pipeline execution
- CORS middleware, rate limiting (services/rate_limit.py), correlation ID middleware injecting X-Request-ID on every response
- Prometheus metrics setup (services/prometheus_setup.py) + Celery bridge (services/prometheus_celery_bridge.py)
- Structured logging (services/observability.py) configured at lifespan start
- Startup checks (services/startup_checks.py, validate_profile_path) run at server boot
- Idempotency: services/idempotency_keys.py + services/idempotency_db.py — prevents duplicate application submissions
- Object storage abstraction (services/object_storage.py) for PDF artifacts
- Workspace write guard (services/workspace_write_guard.py) — prevents cross-workspace writes
- Alembic migrations (alembic/, alembic.ini) — DB schema is versioned, not ad-hoc
- Docker + docker-compose provided (Dockerfile, docker-compose.yml)
- vercel.json for serverless deploy option

**What is missing (from 10/10):**
- No API versioning strategy beyond API_V1_DUPLICATE_ROUTES env flag — v1/v2 migration path not defined
- Object storage is abstracted but S3/GCS credential wiring is not documented for production deploy

---

### 2. Safety & Policy Model — 9.5 / 10

The safety architecture has three independent gate layers, each evaluated at the right stage:

**Gate 1 — Truth Apply Gate (services/truth_apply_gate.py):**
- Blocks live LinkedIn automation if candidate profile is missing required fields
- Env-controlled (TRUTH_APPLY_HARD_GATE=1); dry_run and shadow_mode bypass cleanly
- assess_truth_apply_profile() returns structured {ok, auto_apply_ready, missing_required_fields, warnings} used by both the runner and the Streamlit UI

**Gate 2 — Autonomy Submit Gate (services/autonomy_submit_gate.py):**
- Kill switch: AUTONOMY_LINKEDIN_LIVE_SUBMIT_DISABLED=1 — blocks all live submits instantly
- Pilot-only mode: AUTONOMY_LINKEDIN_PILOT_SUBMIT_ONLY=1 — restricts to allowlisted user_id/workspace_id or per-job pilot_submit_allowed flag
- Telemetry rollback: AUTONOMY_LINKEDIN_ROLLBACK_WHEN_FAILURE_RATE_GTE — Redis-backed, blocks at configurable failure-rate threshold
- Non-submit pattern rollback: AUTONOMY_LINKEDIN_ROLLBACK_WHEN_NONSUBMIT_RATE_GTE — blocks when login/checkpoint friction rate exceeds threshold
- All gate reasons are surfaced as stable string messages in RunResult — operator always knows why

**Gate 3 — LinkedIn Browser Gate (services/linkedin_browser_gate.py):**
- ATS_ALLOW_LINKEDIN_BROWSER env var — REST layer returns 403 unless enabled; MCP layer unaffected (by design, MCP has separate session management)

**Job and Answer State Machine (agents/state.py, services/application_decision.py):**
- JobState: skip | manual_review | manual_assist | safe_auto_apply | blocked
- AnswerState: safe | review | missing | blocked
- truth_safe AND submit_safe => safe_to_submit — operator hard stop when False
- FitDecision: apply | manual_review | reject

**What holds it from 10/10:**
- The MCP server and the REST API use partially different gate code paths — a divergence risk over time. They should share a single gate evaluation call.

---

### 3. Auth & Multi-tenancy — 8.5 / 10

**What is there:**
- JWT auth with both HS256 secret (JWT_SECRET) and OIDC JWKS (JWT_JWKS_URL + JWT_ISSUER) with 1-hour JWKS cache
- X-API-Key bearer for service clients
- X-M2M-API-Key for service-to-service machine identity (separate from user tokens)
- Role templates (services/role_templates.py) — expand_roles_from_template, normalize_role_template_claim
- require_admin dependency for cross-user admin routes
- get_current_user -> User typed model throughout API handlers
- Demo user pass-through when API_KEY is unset (development only — documented in OpenAPI description)
- Workspace enforcement: workspace_write_guard.py prevents cross-workspace writes

**What is missing (from 10/10):**
- No user self-registration or invite flow — requires manual credential provisioning for each new user
- No session/refresh token model for the Streamlit UI; it writes credentials to .env from sidebar in local mode — acceptable for self-hosted, not for multi-tenant SaaS
- Role definitions are template-based but the actual set of roles is not documented externally

---

### 4. Observability & Telemetry — 8.5 / 10

**What is there:**
- Prometheus metrics via services/prometheus_setup.py with FastAPI integration
- Celery task metrics bridge (prometheus_celery_bridge.py) — worker job states exposed to Prometheus
- Redis-backed apply metrics (apply_runner_metrics_redis.py) — linkedin_live_submit_attempt_total, linkedin_live_submit_success_total, non-submit pattern counters — consumed by autonomy rollback gates
- Structured JSON logging via services/observability.py configured at app startup
- Correlation ID middleware — every request/response carries X-Request-ID
- Application audit trail: application_audit.jsonl + run_results_reports.py
- Tracker DB (job_applications.db) + CSV export with per-row job_state, application_decision JSON, run_id
- Metrics alert webhook (services/metrics_alert_webhook.py) for external alerting integration

**What is missing (from 10/10):**
- No built-in Grafana dashboard definition (would need manual setup)
- REDIS_METRICS_URL dependency not listed in setup docs; Redis is optional for metrics but the autonomy rollback gates silently skip if Redis is unavailable — should warn loudly in startup checks

---

### 5. Test Coverage — 8 / 10

52 test files covering:
- test_application_decision.py — state machine decision logic
- test_autonomy_submit_gate.py — Phase 3 kill switch, pilot allowlists, rollback thresholds
- test_application_answerer.py — field answer generation and state classification
- test_auth_roles.py — JWT role expansion
- test_api.py, test_api_cors.py — REST layer
- test_critical_flows.py — end-to-end happy path
- test_follow_up.py, test_follow_up_email.py, test_follow_up_telegram.py — follow-up pipeline
- test_application_tracker_delete.py — delete safety
- test_check_startup_script.py — startup validation
- conftest.py — shared fixtures

**What is missing (from 10/10):**
- No browser / Playwright tests for the LinkedIn automation layer — the highest-risk code path has no automated browser test
- No load / concurrency tests for the Celery worker queue
- Streamlit UI has no test coverage (acceptable for Streamlit, but worth noting)

---

### 6. Decision Layer — 9 / 10

services/application_decision.py is one of the strongest files in the repo:
- build_application_decision() returns a fully structured decision with per-field AnswerState, truth_safe, submit_safe, reason codes
- safe_auto_apply_precondition_checklist() — structured pre-flight for the UI to surface before any live submit
- Decision dict includes answers, job_state, safe_to_submit, fit_decision, unsupported_requirements, ceiling_limited_by
- Used by both Streamlit UI (decision preview tab) and REST API (manual-assist view)
- services/policy_service.py — enrich_job_dict_for_policy_export() normalizes job dict for tracker safety

**What is missing (from 10/10):**
- Decision caching: build_application_decision is called multiple times per job in the Streamlit flow — could be memoized per run_id

---

### 7. Autonomy Phase Maturity — 7.5 / 10

| Phase | Status | Notes |
|---|---|---|
| Phase 1 — Supervised / Manual Assist | Live | manual_assist job state fully implemented; Streamlit shows decision preview + human confirms |
| Phase 2 — Shadow Mode | Live | shadow_mode=True -> dry-run path, no live submit, results logged to tracker |
| Phase 3 — Narrow Live Submit | Env-gated | safe_auto_apply + AUTONOMY_LINKEDIN_PILOT_SUBMIT_ONLY + kill switch all present; live submit currently blocked by LinkedIn session login_challenge in MCP layer |

**Phase 3 gap:** The MCP apply_to_jobs tool is returning login_challenge — the career copilot LinkedIn session is expired/challenged. This is an auth state issue, not a code defect. Fix: complete LinkedIn re-verification in the career copilot browser session.

---

### 8. Documentation — 8.5 / 10

| Document | Status |
|---|---|
| README.md | Repositioned as supervised candidate-ops platform; updated hero, tagline, operating model |
| docs/PRODUCT_BRIEF.md | New — full market-facing brief with pricing tiers, autonomy ladder, competitor table |
| docs/AUTONOMY_MODEL.md | Comprehensive — job states, answer states, Phase 1/2/3, env gates |
| docs/PRODUCT_SCOPE.md | Level 1/2/3 autonomy modes defined |
| docs/MARKET_PRODUCTION_ROADMAP.md | Three-step target ladder |
| CHANGELOG.md | Versioned with Phase 9 entry |

**What is missing:**
- No DEPLOY.md or OPERATIONS.md covering Redis setup, env var checklist, Prometheus scrape config, and S3 wiring for a production deployment
- The app/auth.py OIDC/JWT model is not documented in any user-facing doc

---

### 9. UI / UX — 5.5 / 10

ui/streamlit_app.py at 2,407 lines is a genuinely powerful operator cockpit covering:
- Single-job apply workflow
- Batch URL processing
- AI job finder
- Live ATS optimizer
- Application tracker + edit view
- Follow-up queue
- Insights / analytics
- Direct API console (ATS/form analysis, platform metadata)
- LinkedIn batch apply supervision
- Decision preview + answer state display
- Manual-assist view

**The problem:** All of this is in one file, one tab bar, one Streamlit session. For a developer or power user this is excellent. For a job seeker who wants to apply to a job, it is overwhelming. The product does not yet have a guided happy path.

**Specific UX issues:**
- The ATS / API tab is an internal debugging surface — it belongs in a separate admin/dev mode, not the primary nav
- Credential entry (OPENAI_API_KEY, ANTHROPIC_API_KEY, LinkedIn email/password) in a sidebar on the main UI exposes secret management to the user-facing surface
- No empty state handling or onboarding checklist for new users
- Tab labels do not map to user goals (e.g. "ATS / API" vs "Check my resume score")

**Path to 8/10:**
1. Split into ui/operator_app.py (current cockpit) and ui/candidate_app.py (guided 4-step flow: paste job -> score resume -> tailor -> confirm + submit)
2. Move API console and credential management out of the primary tab bar
3. Add an onboarding checklist (profile complete? -> resume uploaded? -> first job ready to apply?)

---

### 10. Live Application Reliability — 6 / 10

**What is there:**
- MCP apply_to_jobs -> Celery -> run_application -> truth gate -> autonomy gate -> LinkedIn browser automation or manual_assist
- dry_run and shadow_mode work correctly (confirmed: tracker rows, PDF generation, decision output)
- manual_assist path works correctly (confirmed: 10 rows in tracker DB)
- skip and blocked states correctly prevent apply actions

**Current gap:** The career copilot LinkedIn session is in login_challenge state.
- apply_to_jobs with safe_auto_apply jobs returns login_challenge
- search_jobs via MCP returns 0 results (same session)
- All live Phase 3 submits are blocked

This is not a code defect — it is an auth state requiring a one-time manual re-verification.

**Fix (one-time, 5 minutes):**
1. Open https://www.linkedin.com in the career copilot configured browser
2. Complete any verification challenge (SMS, email code, or captcha)
3. Session cookie saves; apply_to_jobs and search_jobs will work

---

## Summary: What To Do Next

### Immediate (unblocks live applications today)
- Complete LinkedIn re-verification for career copilot session — unblocks apply_to_jobs and search_jobs
- Reconnect Chrome extension — unblocks 7 queued Dice.com AI/ML roles

### Short-term (productization — 1-2 weeks)
- Split Streamlit app into candidate_app.py (guided 4-step UX) and operator_app.py (current cockpit)
- Move credential sidebar to a separate setup/admin page
- Add a DEPLOY.md with env var checklist, Redis setup, Prometheus scrape config, S3 wiring

### Medium-term (SaaS readiness — 4-8 weeks)
- Add user self-registration + invite flow (currently requires manual credential provisioning)
- Replace .env sidebar write with a proper settings model for multi-user deployment
- Add a Playwright browser test for the LinkedIn automation path
- Define and document the v1->v2 API versioning strategy
- Warn loudly at startup if REDIS_METRICS_URL is unset but autonomy rollback gates are configured

### Already done — do not redo
- Backend architecture (FastAPI, Celery, Alembic, CORS, rate limiting, Prometheus)
- Safety gates (truth_apply_gate, autonomy_submit_gate, linkedin_browser_gate)
- Auth model (JWT/OIDC, API key, M2M, role templates, workspace guard)
- State machine (JobState, AnswerState, FitDecision literals, safe_to_submit gate)
- Decision layer (build_application_decision, safe_auto_apply_precondition_checklist)
- Test suite (52 files, critical flows, autonomy gate tests, auth role tests)
- Observability (Prometheus, structured logging, correlation IDs, Redis metrics)
- Documentation (PRODUCT_BRIEF, AUTONOMY_MODEL, PRODUCT_SCOPE, MARKET_PRODUCTION_ROADMAP)

---

Generated from full repo read — services/, agents/, app/, ui/, tests/, docs/
Career Co-Pilot Pro · Phase 9 · 2026-03-26
