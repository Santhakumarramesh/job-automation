# Production Readiness Gap List

**Verdict:** Strong prototype. Not production-ready for multi-user or business use.

| Item | Status | Notes |
|------|--------|-------|
| Strong prototype | ✅ | Real code, MCP, fit gate, apply engine |
| Deployable for controlled personal use | ⚠️ Mostly | Dry-run recommended |
| Production-ready for multi-user | ❌ | See P0–P3 below |

---

## P0 — Must fix before production

### 1. Replace stub auth with real authentication ⚠️ Phase 2

**Current:** `app/auth.py` returns hardcoded `demo-user` when no API_KEY.

**Phase 2 done:** API key auth via `X-API-Key` header. Set `API_KEY` env → routes require it.

**Still needed:** OAuth2/JWT, user binding, role checks.

### 2. Fix packaging so deployments include all modules ✅

**Current:** `pyproject.toml` included only `app*`, `agents*`, `dashboard*`, `config*`.

**Done:** Updated to include `services*`, `providers*`, `ui*`, `mcp_servers*`.

### 3. Make runtime dependencies complete and explicit ✅

**Current:** `mcp`, `playwright`, `fastmcp` were commented out in requirements.txt.

**Done:** Added `[mcp]` and `[full]` optional groups; full install provisions MCP/apply.

### 4. Enforce apply policy in backend ✅

**Current:** UI had two-lane strategy; backend could operate more broadly.

**Done:**
- `services/policy_service.py` — central `decide_apply_mode()`
- MCP `apply_to_jobs` filters by `easy_apply_confirmed`
- Runner strict gate: fit, ATS, unsupported
- External ATS never auto-submits

### 5. Replace CSV with real database ⚠️ Phase 2

**Current:** `application_tracker.py` writes to `job_applications.csv`.

**Phase 2 done:** SQLite-backed tracker via `TRACKER_USE_DB=1`. `services/tracker_db.py`; migrates from CSV on first run.

**Still needed for full production:**
- Postgres (DATABASE_URL) for multi-instance
- Screenshots/artifacts metadata in DB
- Migrations

---

## P1 — Next highest priority

### 6. Harden the API surface ⚠️ Phase 2

**Current:** `app/main.py` has root + single `/api/jobs` endpoint.

**Phase 2 done:** `/health`, `/ready`, `GET /api/jobs/{job_id}`. JobRequest max_length, API key auth.

**Still needed:** Artifact retrieval, rate limiting, structured errors.

### 7. Upgrade worker/orchestration model ❌

**Current:** `app/tasks.py` uses simplified orchestration; notes full production would use LangGraph.

**Needed:**
- Unify with actual graph logic
- Retry semantics, idempotency
- Persist task state transitions
- Separate transient vs permanent failures

### 8. Add observability and operational logging ❌

**Current:** Prints and local files.

**Needed:**
- Structured logs
- Request/job correlation IDs
- Worker metrics, failure dashboards
- Audit logs for apply actions
- Alerting on login/checkpoint failures

### 9. Strengthen secrets and config management ❌

**Current:** `.env` and local credential saving.

**Needed:**
- Secrets in secret manager
- Dev/staging/prod config separation
- No sensitive credentials in hosted flows
- Startup validation and rotation

---

## P2 — Quality upgrades

### 10. Tighten profile answer safety ✅

**Current:** Risky fallback claims when profile incomplete.

**Done:** "Please review manually" when sponsorship/why_role/why_company missing; removed strong defaults.

### 11. Make Easy Apply confirmation explicit per job ✅

**Current:** `easy_apply` could blur filter vs confirmed.

**Done:**
- `easy_apply_filter_used` — search filter
- `easy_apply_confirmed` — MCP/page confirmation
- Only submit when `easy_apply_confirmed`
- `confirm_easy_apply` MCP tool

### 12. Improve artifact and file management ❌

**Current:** Resumes, cover letters, screenshots, run JSON on filesystem.

**Needed:**
- Object storage for artifacts
- Metadata in DB
- Retention policies
- User-scoped access

---

## P3 — Polish and reliability

### 13. Clean up naming and service boundaries ✅

**Current:** Legacy names like `find_jobs_with_apify` despite multi-provider.

**Done:** `find_jobs()`, compatibility wrapper deprecated.

### 14. Improve install and deployment docs ❌

**Needed:**
- One-command local bootstrap
- Staging/prod deployment guides
- Environment matrix
- Smoke-test checklist
- Dependency group documentation

### 15. Add test coverage for critical flows ❌

**Needed:**
- Fit gate decisions
- ATS iteration stopping
- Profile validation
- Apply policy enforcement
- Tracker writes
- MCP tool I/O
- Mock external providers and browser

---

## Recommended execution order

1. Real auth (P0)
2. Database-backed persistence (P0)
3. API and worker hardening (P1)
4. Observability (P1)
5. Secrets/config (P1)
6. Artifact management (P2)
7. Docs and tests (P3)

---

## Already done

| Gap | Resolution |
|-----|------------|
| Packaging | pyproject.toml includes services, providers, ui, mcp_servers |
| Dependencies | requirements.txt has [mcp], [full] groups |
| Backend apply policy | policy_service, MCP filters, runner gate |
| Profile answer safety | No risky defaults; "Please review manually" |
| Easy Apply confirmation | easy_apply_confirmed vs easy_apply_filter_used |
| Naming | find_jobs(), deprecated wrapper |
