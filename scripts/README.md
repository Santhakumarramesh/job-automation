# CLI scripts

| Script | Purpose |
|--------|---------|
| `apply_linkedin_jobs.py` | Playwright LinkedIn apply from exported JSON (`--allow-answerer-submit` optional) |
| `follow_up_digest.py` | Print due follow-ups as plain text (cron / email paste) |
| `email_follow_up_digest.py` | Email due follow-ups via SMTP (`FOLLOW_UP_SMTP_*` / `FOLLOW_UP_EMAIL_*`; `--dry-run`) |
| `webhook_follow_up_digest.py` | POST due follow-ups to `FOLLOW_UP_WEBHOOK_URL` (Slack/Discord/raw; `--dry-run`) |
| `telegram_follow_up_digest.py` | Telegram `sendMessage` (`FOLLOW_UP_TELEGRAM_BOT_TOKEN`, `FOLLOW_UP_TELEGRAM_CHAT_ID`; `--dry-run`) |
| `notify_follow_up_digest.py` | One-shot: webhook + Telegram + SMTP for due items (each if configured; `--dry-run`) |
| `print_insights.py` | Phase 13 tracker insights to stdout (`--json`, `--user-id`, `--no-audit`; no API) |
| `validate_profile.py` | Check `candidate_profile.json` for auto-apply readiness (`--strict`, `--json`; exit 0/1) |
| `check_startup.py` | Phase 3.5 env report: `app` \| `worker` \| `streamlit` (`--json`, `--fail-on-errors`) |
| `regenerate_resume_pdf.py` | Build resume PDF from markdown |

Run from repository root, e.g.:

```bash
python scripts/apply_linkedin_jobs.py jobs.json --no-headless
python scripts/apply_linkedin_jobs.py jobs.json --allow-answerer-submit
PYTHONPATH=. python scripts/follow_up_digest.py --user-id streamlit-local
PYTHONPATH=. python scripts/email_follow_up_digest.py --dry-run
PYTHONPATH=. python scripts/webhook_follow_up_digest.py --dry-run
PYTHONPATH=. python scripts/telegram_follow_up_digest.py --dry-run
PYTHONPATH=. python scripts/notify_follow_up_digest.py --dry-run
PYTHONPATH=. python scripts/print_insights.py --no-audit
PYTHONPATH=. python scripts/print_insights.py --json --no-audit | head -c 2000
PYTHONPATH=. python scripts/validate_profile.py --strict
PYTHONPATH=. python scripts/check_startup.py app
PYTHONPATH=. python scripts/check_startup.py worker --json
python scripts/regenerate_resume_pdf.py input.md out.pdf "Your Name"
```

## ATS / REST (optional)

With the API running (`uvicorn app.main:app` or your deploy), you can query ATS metadata and static form hints without the MCP client. The Streamlit **ATS / API** tab mirrors most `POST/GET /api/ats/*` flows (including score-job-fit, search-jobs, batch-prioritize, truth-inventory, prepare-package, run reports, live form probe, and more); set `STREAMLIT_CAREER_API_BASE` if the API is not on `http://127.0.0.1:8000`. For authenticated routes (applications, insights, follow-ups, digest, jobs, **PATCH** follow-up / pipeline, **admin** list/insights/metrics/**celery/inspect**/follow-ups/digest/by-job plus **admin PATCH** follow-up/pipeline, etc.), use **X-API-Key** or **Bearer JWT** in that tab (`STREAMLIT_CAREER_API_BEARER` / `CAREER_API_JWT` optional defaults). **Service health** includes **GET /**, **GET /health**, **GET /ready**, and **GET /metrics** (Prometheus text only when `PROMETHEUS_METRICS=1` and related settings — see `.env.example`); **Authenticated routes** has an **Admin** nested expander for ops (403 without admin).

```bash
# Platform summary (listing vs apply-target provider, v1 auto policy)
curl -sS "http://127.0.0.1:8000/api/ats/platform?job_url=https://linkedin.com/jobs/view/1&apply_url=" | python -m json.tool

# Truth inventory from master resume (MCP parity; inline text or server defaults)
curl -sS -X POST http://127.0.0.1:8000/api/ats/truth-inventory \
  -H "Content-Type: application/json" \
  -d '{"master_resume_text":"","master_resume_path":""}' | python -m json.tool

# LinkedIn job search via MCP bridge (MCP ``search_jobs`` parity; needs linkedin-mcp-server)
curl -sS -X POST http://127.0.0.1:8000/api/ats/search-jobs \
  -H "Content-Type: application/json" \
  -d '{"keywords":"machine learning engineer","location":"United States","work_type":"remote","max_results":10}' | python -m json.tool

Optional: `API_RATE_LIMIT_ATS_SEARCH_JOBS_PER_MINUTE` caps **only** this endpoint (see `.env.example`).

# Fit + ATS snapshot (MCP ``score_job_fit`` parity; body needs real JD + resume text)
curl -sS -X POST http://127.0.0.1:8000/api/ats/score-job-fit \
  -H "Content-Type: application/json" \
  -d '{"job_description":"Senior Python engineer with AWS. ","master_resume_text":"Python developer AWS APIs experience. ","job_title":"Engineer","company":"ACME","location":"USA"}' | python -m json.tool

# Mailing address for a job (uses candidate_profile.json)
curl -sS -X POST http://127.0.0.1:8000/api/ats/address-for-job \
  -H "Content-Type: application/json" \
  -d '{"job_location":"Remote","job_title":"Engineer"}' | python -m json.tool

# Apply policy: auto_easy_apply | manual_assist | skip
curl -sS -X POST http://127.0.0.1:8000/api/ats/decide-apply-mode \
  -H "Content-Type: application/json" \
  -d '{"job":{"url":"https://www.linkedin.com/jobs/view/1/","easy_apply_confirmed":true},"fit_decision":"apply","ats_score":90,"unsupported_requirements":[]}' | python -m json.tool

# Form type from URL (linkedin | greenhouse | lever | workday | generic)
curl -sS "http://127.0.0.1:8000/api/ats/form-type?url=https://www.linkedin.com/jobs/view/1/" | python -m json.tool

# Validate candidate profile (optional project-relative profile_path; default loads config/candidate_profile.json)
curl -sS -X POST http://127.0.0.1:8000/api/ats/validate-profile \
  -H "Content-Type: application/json" \
  -d '{"profile_path":""}' | python -m json.tool

# Autofill map from profile (MCP ``get_autofill_values`` parity)
curl -sS -X POST http://127.0.0.1:8000/api/ats/autofill-values \
  -H "Content-Type: application/json" \
  -d '{"form_type":"linkedin","question_hints":"sponsorship,salary"}' | python -m json.tool

# Job-named resume PDF under generated_resumes/ (MCP ``prepare_resume_for_job`` parity)
curl -sS -X POST http://127.0.0.1:8000/api/ats/prepare-resume-for-job \
  -H "Content-Type: application/json" \
  -d '{"job_title":"ML Engineer","company":"ACME","resume_source_path":""}' | python -m json.tool

# Manual-assist bundle: autofill map, short answers, optional fit gate (MCP ``prepare_application_package``)
curl -sS -X POST http://127.0.0.1:8000/api/ats/prepare-application-package \
  -H "Content-Type: application/json" \
  -d '{"job_title":"Engineer","company":"ACME","job_description":"","master_resume_text":"","job_location":"","work_type":""}' | python -m json.tool

# Batch prioritize jobs — same body as MCP ``batch_prioritize_jobs``: ``{ "jobs": [...], "master_resume_text": "...", "max_scored": 20 }`` (max 500 jobs). Each row needs ``description`` (~100+ chars) for full fit/ATS; see OpenAPI ``POST /api/ats/batch-prioritize-jobs``.

# Run-result JSON rows (same shape as on-disk apply batch output): unmapped field hints + audit counts
curl -sS -X POST http://127.0.0.1:8000/api/ats/review-unmapped-fields \
  -H "Content-Type: application/json" \
  -d '{"run_results":[{"unmapped_fields":["Salary expectation"]}]}' | python -m json.tool
curl -sS -X POST http://127.0.0.1:8000/api/ats/application-audit-report \
  -H "Content-Type: application/json" \
  -d '{"run_results":[{"status":"applied","unmapped_fields":[]}]}' | python -m json.tool

# Recruiter follow-up drafts from profile (MCP ``generate_recruiter_followup``; needs OpenAI)
curl -sS -X POST http://127.0.0.1:8000/api/ats/generate-recruiter-followup \
  -H "Content-Type: application/json" \
  -d '{"job_title":"PM","company":"ACME","application_date":""}' | python -m json.tool

# Static form section hints (Greenhouse example)
curl -sS -X POST http://127.0.0.1:8000/api/ats/analyze-form \
  -H "Content-Type: application/json" \
  -d '{"job_url":"https://boards.greenhouse.io/acme/jobs/1","apply_url":""}' | python -m json.tool
```

**Root, liveness, readiness, metrics** (no `/api` prefix; usually no auth):

```bash
curl -sS http://127.0.0.1:8000/
curl -sS http://127.0.0.1:8000/health | python -m json.tool
curl -sS http://127.0.0.1:8000/ready | python -m json.tool
# Prometheus exposition (404 unless PROMETHEUS_METRICS=1 on the API; see .env.example)
curl -sS http://127.0.0.1:8000/metrics
```

Use `X-API-Key` or Bearer auth if your server requires it (open **demo-user** when `API_KEY` is unset in dev).

```bash
# List applications for the authenticated user (JWT: JWT_SECRET + PyJWT on server)
curl -sS -H "Authorization: Bearer $JWT" http://127.0.0.1:8000/api/applications | python -m json.tool

# Same with API key
curl -sS -H "X-API-Key: $API_KEY" http://127.0.0.1:8000/api/applications | python -m json.tool

# Insights (optional audit tail); tune query params as needed
curl -sS -H "X-API-Key: $API_KEY" \
  "http://127.0.0.1:8000/api/insights?include_audit=true&audit_max_lines=500" | python -m json.tool

# Follow-up queue
curl -sS -H "X-API-Key: $API_KEY" \
  "http://127.0.0.1:8000/api/follow-ups?due_only=true&limit=20&sort_by_priority=true" | python -m json.tool

# Due follow-ups as plain text + JSON items (email / reminders)
curl -sS -H "X-API-Key: $API_KEY" \
  "http://127.0.0.1:8000/api/follow-ups/digest?limit=25&include_snoozed=true" | python -m json.tool

# Enqueue a Celery job (202 Accepted)
curl -sS -X POST http://127.0.0.1:8000/api/jobs \
  -H "Content-Type: application/json" -H "X-API-Key: $API_KEY" \
  -d '{"name":"my-task","payload":{"url":"https://example.com/job"}}' | python -m json.tool

# Optional idempotency (header or body field; if both, they must match)
curl -sS -X POST http://127.0.0.1:8000/api/jobs \
  -H "Content-Type: application/json" -H "X-API-Key: $API_KEY" -H "Idempotency-Key: my-key-1" \
  -d '{"name":"my-task","payload":{},"idempotency_key":"my-key-1"}' | python -m json.tool

# Multi-replica APIs: set IDEMPOTENCY_USE_DB=1 on the API (tracker DB + alembic tracker_0005 for Postgres); see docs/WORKER_ORCHESTRATION.md

# Poll job status (use job_id from enqueue response)
curl -sS -H "X-API-Key: $API_KEY" \
  "http://127.0.0.1:8000/api/jobs/00000000-0000-0000-0000-000000000000?include_result=false" | python -m json.tool

# Update follow-up fields on a tracker row (application_id = items[].id from GET /api/applications)
curl -sS -X PATCH "http://127.0.0.1:8000/api/applications/ROW_UUID/follow-up" \
  -H "Content-Type: application/json" -H "X-API-Key: $API_KEY" \
  -d '{"follow_up_at":"2025-12-01T15:00:00Z","follow_up_status":"pending","follow_up_note":"Check in"}' | python -m json.tool

# Update interview pipeline fields on a tracker row
curl -sS -X PATCH "http://127.0.0.1:8000/api/applications/ROW_UUID/pipeline" \
  -H "Content-Type: application/json" -H "X-API-Key: $API_KEY" \
  -d '{"interview_stage":"scheduled","offer_outcome":""}' | python -m json.tool

# --- Admin (403 unless admin: JWT role in JWT_ADMIN_ROLES, API_KEY_IS_ADMIN=1, or DEMO_USER_IS_ADMIN) ---
curl -sS -H "X-API-Key: $API_KEY" http://127.0.0.1:8000/api/admin/applications | python -m json.tool
curl -sS -H "X-API-Key: $API_KEY" \
  "http://127.0.0.1:8000/api/admin/insights?include_audit=true&audit_max_lines=1000" | python -m json.tool
curl -sS -H "X-API-Key: $API_KEY" http://127.0.0.1:8000/api/admin/metrics/summary | python -m json.tool
# Live Celery workers: ping / active / reserved / scheduled / stats (None if no worker replied; optional ?timeout=2)
curl -sS -H "X-API-Key: $API_KEY" \
  "http://127.0.0.1:8000/api/admin/celery/inspect?timeout=2" | python -m json.tool
curl -sS -H "X-API-Key: $API_KEY" \
  "http://127.0.0.1:8000/api/admin/follow-ups?due_only=true&limit=50&sort_by_priority=true" | python -m json.tool
curl -sS -H "X-API-Key: $API_KEY" \
  "http://127.0.0.1:8000/api/admin/follow-ups/digest?limit=30&include_snoozed=true" | python -m json.tool
curl -sS -H "X-API-Key: $API_KEY" \
  "http://127.0.0.1:8000/api/admin/applications/by-job/EXTERNAL_JOB_ID?signed_urls=false" | python -m json.tool

# Admin PATCH — same JSON bodies as user PATCH; targets any row by internal application id (no user scope)
curl -sS -X PATCH "http://127.0.0.1:8000/api/admin/applications/ROW_UUID/follow-up" \
  -H "Content-Type: application/json" -H "X-API-Key: $API_KEY" \
  -d '{"follow_up_status":"pending","follow_up_note":"Admin update"}' | python -m json.tool
curl -sS -X PATCH "http://127.0.0.1:8000/api/admin/applications/ROW_UUID/pipeline" \
  -H "Content-Type: application/json" -H "X-API-Key: $API_KEY" \
  -d '{"interview_stage":"scheduled","offer_outcome":""}' | python -m json.tool
```

**Live DOM probe (optional):** set `ATS_ALLOW_LIVE_FORM_PROBE=1` on the API server, install Playwright (`pip install .[apply]` and `playwright install chromium`). If the flag is off, the API returns **403** with the same JSON as MCP `analyze_form_live` (`status: disabled`, `message: …`). Then:

```bash
export ATS_ALLOW_LIVE_FORM_PROBE=1
# same shell as uvicorn, or add to .env
curl -sS -X POST http://127.0.0.1:8000/api/ats/analyze-form/live \
  -H "Content-Type: application/json" \
  -d '{"apply_url":"https://boards.greenhouse.io/your-board/jobs/123","job_url":"","max_fields":30}' | python -m json.tool
```

Read-only (no submit). Many sites require login or block automation — check `live.status` and `live.message`.

Optional: set `API_RATE_LIMIT_LIVE_FORM_PROBE_PER_MINUTE` (e.g. `10`) to cap **only** this endpoint in its own bucket (see `.env.example`).

**LinkedIn apply / Easy Apply confirm (optional):** unlike MCP, the HTTP API gates Playwright login + apply behind `ATS_ALLOW_LINKEDIN_BROWSER=1` (set on the uvicorn process). Without it, these return **403** with `status: disabled`. Requires `LINKEDIN_EMAIL` / `LINKEDIN_PASSWORD`, Playwright, and (for default apply mode) Easy Apply–confirmed job rows. Bodies are capped at **50** jobs per request.

```bash
export ATS_ALLOW_LINKEDIN_BROWSER=1
# Confirm Easy Apply control on a listing URL
curl -sS -X POST http://127.0.0.1:8000/api/ats/confirm-easy-apply \
  -H "Content-Type: application/json" \
  -d '{"job_url":"https://www.linkedin.com/jobs/view/123456/"}' | python -m json.tool

# Batch apply (dry_run true recommended first); see OpenAPI for full job object fields
curl -sS -X POST http://127.0.0.1:8000/api/ats/apply-to-jobs \
  -H "Content-Type: application/json" \
  -d '{"jobs":[{"title":"Eng","company":"Co","url":"https://www.linkedin.com/jobs/view/1","easy_apply_confirmed":true}],"dry_run":true,"rate_limit_seconds":90}' | python -m json.tool

# Same as apply with dry_run forced (MCP ``dry_run_apply_to_jobs`` parity)
curl -sS -X POST http://127.0.0.1:8000/api/ats/apply-to-jobs/dry-run \
  -H "Content-Type: application/json" \
  -d '{"jobs":[{"title":"Eng","company":"Co","url":"https://www.linkedin.com/jobs/view/1","easy_apply_confirmed":true}]}' | python -m json.tool
```

Optional: `API_RATE_LIMIT_LINKEDIN_BROWSER_PER_MINUTE` caps **confirm-easy-apply**, **apply-to-jobs**, and **apply-to-jobs/dry-run** in one shared bucket (works even when the global API limiter is off).

**CI (GitHub Actions):** copy [`docs/setup/github-actions-ci.yml`](../docs/setup/github-actions-ci.yml) to `.github/workflows/ci.yml`. Pushing workflow files needs a GitHub PAT with the **workflow** scope.
