# Workflow → module map

Maps the **target operating model** ([TARGET_OPERATING_MODEL.md](TARGET_OPERATING_MODEL.md)) to **repository paths** and implementation status.

**Legend:** ✅ implemented · ⚠️ partial / needs hardening · 📋 planned · ❌ not started

---

## Phase 1 — Identity, truth, profile

| # | Capability | Primary owner (path) | Status |
|---|------------|----------------------|--------|
| 1 | Master resume ingestion (PDF/text) | `ui/streamlit_app.py`, `services/document_service.py` (`extract_text_from_pdf`) | ✅ |
| 1b | Truth inventory from resume | `agents/master_resume_guard.py` — `parse_master_resume()`, `CandidateProfile`, `extract_search_keywords()` | ✅ |
| 2 | Candidate profile load | `config/candidate_profile.json`, `services/profile_service.py` | ✅ |
| 3 | Profile validation | `services/profile_service.py` — `validate_profile()`, `is_auto_apply_ready()` | ⚠️ Enforce stricter gates before auto-apply |
| 4 | Truth inventory as gate for tailoring/fit | `agents/master_resume_guard.py` — `is_job_fit()`, `get_unsupported_requirements()`, `compute_job_fit_score()` | ✅ |

---

## Phase 2 — Job discovery

| # | Capability | Primary owner (path) | Status |
|---|------------|----------------------|--------|
| 5 | Multi-source search | `providers/registry.py`, `providers/apify_jobs.py`, `providers/linkedin_mcp_jobs.py` | ✅ |
| 6 | Search strategy from resume | `agents/master_resume_guard.extract_search_keywords()` → `providers/registry._analyze_resume_keywords()` | ✅ |
| 7 | `easy_apply_filter_used` vs `easy_apply_confirmed` | `providers/common_schema.py` — `JobListing`; LinkedIn detail extraction `providers/linkedin_mcp_jobs.py`; MCP `confirm_easy_apply` | ✅ / ⚠️ Broader confirmation coverage |

---

## Phase 3 — Normalization & ranking

| # | Capability | Primary owner (path) | Status |
|---|------------|----------------------|--------|
| 8 | Normalized job schema | `providers/common_schema.py` — `JobListing`, `job_listing_from_dict()` | ✅ |
| 9 | Preliminary ranking | Provider + dataframe columns (`resume_match_score`, etc.); registry `get_jobs()` | ⚠️ No single ranked “pre-fit” service yet |

---

## Phase 4 — Fit gate

| # | Capability | Primary owner (path) | Status |
|---|------------|----------------------|--------|
| 10–12 | Fit analysis, decisions, score | `agents/master_resume_guard.py` — `is_job_fit()`, `FitResult`; `services/ats_service.py` — `check_fit_gate()` | ✅ |
| 13 | Unsupported requirements | Returned in fit/ATS flows; blocks policy auto-apply | ✅ |

---

## Phase 5 — ATS

| # | Capability | Primary owner (path) | Status |
|---|------------|----------------------|--------|
| 14 | Initial ATS | `enhanced_ats_checker.py` — `EnhancedATSChecker`; `services/ats_service.py` — `score_resume()` | ✅ |
| 15–16 | Iterative optimization | `agents/iterative_ats_optimizer.py`, `services/ats_service.run_iterative_ats()` | ✅ |
| 17 | Truth-safe cap / “max truthful score” messaging | Tailoring respects inventory; explicit **ceiling** UX/API | 📋 |

---

## Phase 6 — Tailoring & package

| # | Capability | Primary owner (path) | Status |
|---|------------|----------------------|--------|
| 18 | Tailored resume | `agents/resume_editor.py` — `tailor_resume()` | ✅ |
| 19 | Resume naming | `services/resume_naming.py` | ✅ |
| 20 | Cover letter | `agents/cover_letter_generator.py`, `services/document_service.py` | ✅ |
| 21 | Application package | `mcp_servers/job_apply_autofill/server.py` — `prepare_application_package` | ✅ |

---

## Phase 7 — Answering

| # | Capability | Primary owner (path) | Status |
|---|------------|----------------------|--------|
| 22–23 | Classified / humanized answers | `agents/application_answerer.py` | ✅ |
| 24 | Low-confidence → manual review | Partially via fallbacks; **structured** `manual_review_required` on fields | ⚠️ |
| 25 | Batch field map | MCP package + runner `qa_audit`, `unmapped_fields` | ✅ / ⚠️ |

---

## Phase 8 — Policy engine

| # | Capability | Primary owner (path) | Status |
|---|------------|----------------------|--------|
| 26–27 | Single policy outcome | `services/policy_service.py` — `decide_apply_mode()` | ✅ |
| 27 | Include profile-valid + no risky unanswered Qs in policy | Today: fit, ATS, unsupported, URL, `easy_apply_confirmed` | ⚠️ Extend with profile + answerer risk |
| 28 | Policy decision audit (per-job reason) | `services/policy_service` — `REASON_*` codes; `policy_reason` on `JobListing` + tracker; MCP `decide_apply_mode` returns `policy_reason` | ✅ |

---

## Phase 9 — Auto-apply

| # | Capability | Primary owner (path) | Status |
|---|------------|----------------------|--------|
| 29 | MCP tools | `mcp_servers/job_apply_autofill/server.py` | ✅ |
| 30–31 | Dry-run & live | `apply_to_jobs`, `agents/application_runner.py` | ✅ |
| 32 | Easy Apply–only enforcement | Runner + MCP filters | ✅ |

---

## Phase 10 — Manual-assist

| # | Capability | Primary owner (path) | Status |
|---|------------|----------------------|--------|
| 33 | Package for human apply | UI exports, MCP package, documents on disk | ✅ |
| 34 | External ATS helper | Runner returns `manual_assist_ready`; fill heuristics | ⚠️ |

---

## Phase 11 — Tracking & audit

| # | Capability | Primary owner (path) | Status |
|---|------------|----------------------|--------|
| 35 | Tracker schema | `services/application_tracker.py`, `services/tracker_db.py` | ✅ incl. `user_id` |
| 36 | DB scale-out | SQLite (`TRACKER_DB_PATH` / `sqlite:///…`); Postgres `TRACKER_DATABASE_URL` or `DATABASE_URL` + `pip install .[postgres]` (`services/tracker_db.py`) | ✅ / pool 📋 |
| 36b | Postgres migrations | `alembic/`, `alembic.ini`, `pip install .[migrations]` — `docs/MIGRATIONS.md` | ✅ baseline `tracker_0001` |
| 37 | Run archive | `agents/application_runner.py` — `save_run_results`, screenshots | ✅ |
| API list scoped | `GET /api/applications` | `app/main.py` | ✅ |
| Artifacts metadata | `artifacts_manifest` column; `build_artifact_metadata` | `services/artifact_metadata.py`, `tracker_db` | ✅ |
| API by job_id | `GET /api/applications/by-job/{job_id}`; admin `GET /api/admin/applications/by-job/{job_id}` | `app/main.py` | ✅ |
| S3 artifacts | `services/object_storage.py`; Celery merge into `artifacts_manifest`; `?signed_urls=true` | `app/tasks.py`, `docs/OBJECT_STORAGE.md` | ✅ |

---

## Phase 3.6 — Observability (summary)

| # | Capability | Primary owner | Status |
|---|------------|---------------|--------|
| O1 | Celery audit + logs | `app/tasks.py`, `services/observability.py` | ✅ |
| O2 | Redis metrics + admin API | `services/metrics_redis.py` | ✅ |
| O3 | Prometheus | `services/prometheus_setup.py` | ✅ optional |

---

## Phase 3.5 — Secrets & config (summary)

| # | Capability | Primary owner | Status |
|---|------------|---------------|--------|
| S1 | Production / strict startup | `services/startup_checks.py` | ✅ |
| S2 | AWS Secrets Manager hydrate | `services/secrets_loader.py` | ✅ |

---

## Phase 3.3 — Worker (summary)

| # | Capability | Primary owner | Status |
|---|------------|---------------|--------|
| W1 | LangGraph Celery pipeline | `agents/celery_workflow.py`, `app/tasks.py` | ✅ |
| W2 | Idempotency / job API | `services/idempotency_keys.py`, `GET /api/jobs/{id}` | ✅ |
| W3 | Task snapshots | `services/task_state_store.py` | ✅ |

---

## Phase 12 — Follow-up

| # | Capability | Primary owner (path) | Status |
|---|------------|----------------------|--------|
| 38 | Recruiter follow-up text | MCP `generate_recruiter_followup` | ✅ |
| 39 | Follow-up columns + queue API | `services/follow_up_service.py`, `GET /api/follow-ups`, `PATCH .../follow-up` | ✅ |
| 40 | Priority follow-up scoring (sorted queue) | `services/follow_up_service.py` (`follow_up_priority_score`), `GET /api/follow-ups?sort_by_priority=`, Streamlit tracker tab | ✅ |
| — | Follow-up email (SMTP) | `services/follow_up_email.py`, `scripts/email_follow_up_digest.py` | ✅ |
| — | Webhook / Slack / Discord digest | `services/follow_up_webhook.py`, `scripts/webhook_follow_up_digest.py`, `FOLLOW_UP_WEBHOOK_*` | ✅ |
| — | Telegram digest (sendMessage) | `services/follow_up_telegram.py`, `scripts/telegram_follow_up_digest.py`, `FOLLOW_UP_TELEGRAM_*` | ✅ |
| — | Multi-channel digest (one cron) | `scripts/notify_follow_up_digest.py` (webhook → Telegram → SMTP) | ✅ |

---

## Phase 13 — Learning loop

| # | Capability | Primary owner (path) | Status |
|---|------------|----------------------|--------|
| 41 | Tracker aggregates + heuristic suggestions | `services/application_insights.py`, `GET /api/insights`, Streamlit tracker tab | ✅ |
| 42 | Audit tail summary (JSONL) | `summarize_audit_log`, `GET /api/insights?include_audit=true`, `GET /api/admin/insights` | ✅ |
| 43 | Answerer QA rollups in insights | `compute_answerer_review_insights` in `application_insights.py`, `GET /api/insights` field `answerer_review` | ✅ (light) |
| 44 | Interview / offer pipeline on tracker + policy correlations | `interview_stage`, `offer_outcome` columns; `PATCH /api/applications/{id}/pipeline`; `pipeline_correlations` in insights; Alembic `tracker_0003` | ✅ |
| — | Tracker crosstabs (submission × policy / apply mode) | `compute_tracker_crosstabs`, `tracker.crosstabs` in `GET /api/insights`, Streamlit | ✅ (light) |
| — | Deep failure correlation, profile auto-tuning | MCP tools + analytics | ⚠️ Manual / future |

---

## Quick module index (by folder)

| Folder / file | Roles in the target workflow |
|---------------|------------------------------|
| `agents/master_resume_guard.py` | Truth inventory, fit gate, search keywords |
| `agents/application_answerer.py` | Humanized employer answers |
| `agents/application_runner.py` | Playwright apply / dry-run execution |
| `agents/resume_editor.py`, `humanize_*.py` | Tailoring + tone |
| `agents/cover_letter_generator.py` | Cover letters |
| `agents/iterative_ats_optimizer.py` | ATS loop |
| `services/profile_service.py` | Profile load/validate |
| `services/ats_service.py` | Fit gate orchestration, ATS, optimizer wiring |
| `services/policy_service.py` | `auto_easy_apply` / `manual_assist` / `skip` |
| `services/application_tracker.py`, `tracker_db.py` | Persistence + `user_id` |
| `services/application_insights.py` | Phase 13 — tracker + audit aggregates, API insights |
| `services/resume_naming.py` | PDF naming convention; `pick_fallback_resume_pdf`, `MASTER_RESUME_PDF` |
| `services/observability.py` | Audit JSONL |
| `providers/registry.py`, `common_schema.py`, `*_jobs.py` | Discovery + `JobListing` |
| `mcp_servers/job_apply_autofill/server.py` | MCP control plane tools |
| `ui/streamlit_app.py` | Tabs, LangGraph workflow, exports |
| `scripts/apply_linkedin_jobs.py` | CLI LinkedIn apply |

---

## Suggested implementation order (gaps)

1. ~~**Policy audit field**~~ — `policy_reason` on tracker, `JobListing`, MCP; `REASON_*` codes in `policy_service`.  
2. ~~**Answerer confidence**~~ — `answer_question_structured()`, `AnswerResult`, MCP `answer_review` / `prepare_application_package`, Streamlit profile tester.  
2a. ~~**Answerer → apply runner**~~ — `RunResult.answerer_review`, `RunConfig.block_submit_on_answerer_review`, `save_run_results` + tracker `qa_audit._answerer_review`.  
3. ~~**Truth-safe ATS ceiling**~~ — `services/truth_safe_ats.py`, `run_iterative_ats` / `run_live_optimizer`, Streamlit + MCP `score_job_fit`.  
4. ~~**Follow-up reminders**~~ — digest API/CLI + optional `scripts/email_follow_up_digest.py` (`services/follow_up_email.py`, `FOLLOW_UP_*` env).  
5. **Postgres + object storage** — Phase 3.2 / 3.4 in `PHASE_3_PLAN.md`.
