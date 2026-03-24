# Workflow → module map

Maps the **target operating model** ([TARGET_OPERATING_MODEL.md](TARGET_OPERATING_MODEL.md)) to **repository paths** and implementation status.

**Legend:** ✅ implemented · ⚠️ partial / needs hardening · 📋 planned · ❌ not started

---

## Completion snapshot (target workflow)

Rough **~93–96%** of the end-to-end vision in [TARGET_OPERATING_MODEL.md](TARGET_OPERATING_MODEL.md) / [VISION_ARCHITECTURE_MAP.md](VISION_ARCHITECTURE_MAP.md): core loop (truth → discovery → fit → ATS → package → policy → apply → track → follow-up → insights) is **implemented**. Recent upgrades include **job-source labeling**, **truth-safe ATS ceiling**, **pre-fit ranker**, **`get_address_for_job`** + profile **`alternate_mailing_addresses`**, MCP **`prepare_application_package`** address block. Remaining: **Easy Apply confirmation breadth** (DOM hardening), **deeper closed-loop learning**, **hosted multi-tenant / compliance** polish. Core **ATS adapter stubs**, **tracker audit columns**, and **MCP `describe_ats_platform`** are in place.

| Phase band | Theme | Status (high level) |
|------------|--------|----------------------|
| 1–2 | Truth + profile + discovery | ✅ strong + **alternate mailing** routing; ⚠️ stricter auto-apply profile gates; ⚠️ Easy Apply confirmation breadth |
| 2.5 | Job source & ATS labeling | ✅ `providers/job_source.py` — detect Greenhouse/Lever/Workday/Dice/LinkedIn jobs vs other; policy uses listing + apply URL |
| 3 | Normalization & ranking | ✅ schema + source labels; ✅ unified pre-fit ranker (`services/prefit_ranker.py` + registry) |
| 4–6 | Fit + ATS + tailoring | ✅; ✅ truth-safe ceiling in `services/truth_safe_ats.py` + ATS service + Streamlit + MCP `score_job_fit` |
| 7–8 | Answers + policy | ✅; ✅ answerer manual-review → policy; ✅ external apply URL → `manual_assist`; ⚠️ batch field map polish |
| 9–10 | Auto-apply + manual-assist | ✅ LinkedIn **/jobs/** Easy Apply only; v1 **no auto** if apply target is external board; ⚠️ per-ATS adapter tools |
| 11–13 + 3.x | Track, follow-up, learn, prod | ✅ Postgres/SQLite + **`tracker_0004`** audit columns + `tracker_context` merge on log; ⚠️ deep auto-tuning |

**Suggested next implementation slices:** (1) **Real `analyze_form` / field-map** per board (Playwright + templates), building on `providers/ats/` + MCP `analyze_form`. (2) **MCP `confirm_easy_apply`** — further DOM tuning via `services/linkedin_easy_apply.py` selector list. (3) **Streamlit** — optional column picker / address column in jobs grid. (4) **Insights** — deeper charts on `by_ats_provider_apply_target` vs outcomes.

---

## Phase 1 — Identity, truth, profile

| # | Capability | Primary owner (path) | Status |
|---|------------|----------------------|--------|
| 1 | Master resume ingestion (PDF/text) | `ui/streamlit_app.py`, `services/document_service.py` (`extract_text_from_pdf`) | ✅ |
| 1b | Truth inventory from resume | `agents/master_resume_guard.py` — `parse_master_resume()`, `CandidateProfile`, `extract_search_keywords()` | ✅ |
| 2 | Candidate profile load | `config/candidate_profile.json`, `services/profile_service.py` | ✅ |
| 2a | Structured `application_locations` + `mailing_address` + **`alternate_mailing_addresses`** | `profile_service.format_*`, `validate_profile`; **`services/address_for_job.get_address_for_job`**; `job_location_match.job_location_haystack` / `haystack_matches_region`; MCP `get_address_for_job`; `prepare_application_package.address_selection` | ✅ |
| 3 | Profile validation | `services/profile_service.py` — `validate_profile()`, `is_auto_apply_ready()`; CLI `scripts/validate_profile.py` | ⚠️ Enforce stricter gates before auto-apply |
| 4 | Truth inventory as gate for tailoring/fit | `agents/master_resume_guard.py` — `is_job_fit()`, `get_unsupported_requirements()`, `compute_job_fit_score()` | ✅ |

---

## Phase 2 — Job discovery

| # | Capability | Primary owner (path) | Status |
|---|------------|----------------------|--------|
| 5 | Multi-source search | `providers/registry.py`, `providers/apify_jobs.py`, `providers/linkedin_mcp_jobs.py` | ✅ |
| 6 | Search strategy from resume | `agents/master_resume_guard.extract_search_keywords()` via `services/prefit_ranker.prefit_keyword_bundle()` → `providers/registry.get_jobs()` | ✅ |
| 7 | `easy_apply_filter_used` vs `easy_apply_confirmed` | `providers/common_schema.py` — `JobListing`; LinkedIn detail extraction `providers/linkedin_mcp_jobs.py`; MCP `confirm_easy_apply`; shared selectors `services/linkedin_easy_apply.py` + `agents/application_runner.py` | ✅ / ⚠️ DOM drift — extend selector list as LinkedIn changes |

---

## Phase 2.5 — Job source & ATS labeling

| # | Capability | Primary owner (path) | Status |
|---|------------|----------------------|--------|
| 7b | URL → board label (`linkedin_jobs`, `greenhouse`, `lever`, `workday`, `dice`, …) | `providers/job_source.py` — `detect_ats_provider()`, `ats_metadata_for_job()` | ✅ |
| 7c | Policy: listing must be LinkedIn **jobs** path; apply target must stay on LinkedIn jobs for v1 auto | `services/policy_service.py` — `REASON_MANUAL_NON_LINKEDIN`, `REASON_MANUAL_EXTERNAL_APPLY_TARGET` | ✅ |
| 7d | Export / Streamlit enrich attaches `ats_provider`, `ats_provider_apply_target` | `enrich_job_dict_for_policy_export()` | ✅ |
| 7e | ATS **adapter** interface (`supports_auto_apply_v1`, `analyze_form`, manual-assist capabilities) | `providers/ats/` — `form_hints`, `registry`; MCP + REST parity (`GET /api/ats/platform`, `GET /api/ats/form-type`, validate/autofill/batch-prioritize/analyze/search/score/address/policy — `services/autofill_values.py`, `batch_prioritize_jobs.py`, `form_type_detection.py`, `rate_limit.py`, etc.) | ✅ static + optional read-only DOM probe + REST MCP parity |

---

## Phase 3 — Normalization & ranking

| # | Capability | Primary owner (path) | Status |
|---|------------|----------------------|--------|
| 8 | Normalized job schema | `providers/common_schema.py` — `JobListing`, `job_listing_from_dict()`; optional `ats_*` via enrich / future column | ✅ |
| 9 | Preliminary ranking | `services/prefit_ranker.py` — `prefit_score_job`, `rank_job_listings`, `add_prefit_scores_to_dataframe`; `providers/registry.get_jobs()` sets `resume_match_score` | ✅ |

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
| 17 | Truth-safe cap / “max truthful score” messaging | `services/truth_safe_ats.compute_truth_safe_ats_ceiling`; `run_iterative_ats` / `score_resume` / MCP `score_job_fit`; Streamlit metrics | ✅ |

---

## Phase 6 — Tailoring & package

| # | Capability | Primary owner (path) | Status |
|---|------------|----------------------|--------|
| 18 | Tailored resume | `agents/resume_editor.py` — `tailor_resume()` | ✅ |
| 19 | Resume naming | `services/resume_naming.py` | ✅ |
| 20 | Cover letter | `agents/cover_letter_generator.py`, `services/document_service.py` | ✅ |
| 21 | Application package | `mcp_servers/job_apply_autofill/server.py` — `prepare_application_package` (+ optional `job_location` / `work_type`, address selection) | ✅ |

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
| 27 | Include profile-valid + answerer manual-review in policy | `decide_apply_mode_with_reason` — `answerer_manual_review_required`, `answerer_review` (JSON or dict); `REASON_MANUAL_ANSWERER_REVIEW`; optional `POLICY_ENFORCE_JOB_LOCATION` + `application_locations` ([job_location_match.py](services/job_location_match.py)) | ✅ / ⚠️ Tighter profile + field-level gates still optional |
| 27b | External boards never v1 auto-submit | Job source + apply-target checks; Greenhouse/Lever/etc → `manual_assist` even if listing is LinkedIn | ✅ |
| 28 | Policy decision audit (per-job reason) | `services/policy_service` — `REASON_*` codes; `policy_reason` on `JobListing` + tracker; MCP `decide_apply_mode` returns `policy_reason` | ✅ |

---

## Phase 9 — Auto-apply

| # | Capability | Primary owner (path) | Status |
|---|------------|----------------------|--------|
| 29 | MCP tools | `mcp_servers/job_apply_autofill/server.py` | ✅ |
| 30–31 | Dry-run & live | `apply_to_jobs`, `agents/application_runner.py` | ✅ |
| 32 | Easy Apply–only enforcement | Runner + MCP filters; policy requires LinkedIn **`/jobs/`** URL + on-LinkedIn apply target | ✅ |

---

## Phase 10 — Manual-assist

| # | Capability | Primary owner (path) | Status |
|---|------------|----------------------|--------|
| 33 | Package for human apply | UI exports, MCP package, documents on disk | ✅ |
| 34 | External ATS helper | Runner returns `manual_assist_ready`; fill heuristics; future `providers/ats/*` + MCP `analyze_form` / `review_unmapped_fields` | ⚠️ |

---

## Phase 11 — Tracking & audit

| # | Capability | Primary owner (path) | Status |
|---|------------|----------------------|--------|
| 35 | Tracker schema | `services/application_tracker.py`, `services/tracker_db.py`, `services/tracker_context.py` | ✅ `ats_provider`, `ats_provider_apply_target`, `truth_safe_ats_ceiling`, `selected_address_label`, `package_field_stats`; Alembic `tracker_0004` |
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
| S1 | Production / strict startup | `services/startup_checks.py`, `scripts/check_startup.py` (report / CI) | ✅ |
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
| 41b | Insights CLI (local / cron) | `scripts/print_insights.py` — same payload as API without server | ✅ |
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
| `services/profile_service.py` | Profile load/validate; location + mailing formatters |
| `services/address_for_job.py` | `get_address_for_job` — default vs `alternate_mailing_addresses` |
| `services/job_location_match.py` | Location policy gate + shared haystack / region match helpers |
| `services/ats_service.py` | Fit gate orchestration, ATS, optimizer wiring |
| `services/truth_safe_ats.py` | Truth-safe internal ATS ceiling estimate + reasons |
| `services/prefit_ranker.py` | Pre-fit overlap score + sort (before deep fit/ATS) |
| `services/policy_service.py` | `auto_easy_apply` / `manual_assist` / `skip` |
| `services/application_tracker.py`, `tracker_db.py`, `tracker_context.py` | Persistence + `user_id` + audit merge on log |
| `services/application_insights.py` | Phase 13 — tracker + audit aggregates, API insights |
| `services/resume_naming.py` | PDF naming convention; `pick_fallback_resume_pdf`, `MASTER_RESUME_PDF` |
| `services/observability.py` | Audit JSONL |
| `providers/registry.py`, `common_schema.py`, `job_source.py`, `ats/`, `*_jobs.py` | Discovery + `JobListing` + ATS URL labels + adapter registry |
| `mcp_servers/job_apply_autofill/server.py` | MCP control plane tools |
| `ui/streamlit_app.py` | Tabs, LangGraph workflow, exports |
| `scripts/apply_linkedin_jobs.py` | CLI LinkedIn apply |

---

## Suggested implementation order (gaps)

1. ~~**Policy audit field**~~ — `policy_reason` on tracker, `JobListing`, MCP; `REASON_*` codes in `policy_service`.  
2. ~~**Answerer confidence**~~ — `answer_question_structured()`, `AnswerResult`, MCP `answer_review` / `prepare_application_package`, Streamlit profile tester.  
2a. ~~**Answerer → apply runner**~~ — `RunResult.answerer_review`, `RunConfig.block_submit_on_answerer_review`, `save_run_results` + tracker `qa_audit._answerer_review`.  
3. ~~**Job source + external apply gate**~~ — `providers/job_source.py`; policy `REASON_MANUAL_EXTERNAL_APPLY_TARGET`; enrich sets `ats_provider` / `ats_provider_apply_target`.  
4. ~~**Pre-fit ranking service**~~ — `services/prefit_ranker.py`; registry `get_jobs` + `EnhancedJobFinder.analyze_resume_for_keywords`.  
5. ~~**Truth-safe ATS ceiling UX**~~ — `services/truth_safe_ats.py`; `run_iterative_ats` + `score_resume`; Streamlit; MCP `score_job_fit`.  
6. ~~**`providers/ats/` adapter stubs**~~ — `providers/ats/` + MCP `describe_ats_platform`.  
7. ~~**`get_address_for_job` service**~~ — `services/address_for_job.py`; MCP + package `address_selection`.  
8. ~~**Tracker columns + Alembic**~~ — `tracker_0004` + `tracker_context.build_tracker_row_extras` on log.  
9. **DOM `analyze_form` implementations** — extend adapters beyond stubs (**next slice**).  
10. **Postgres pool / scale** — Phase 3.2 / 3.4 in `PHASE_3_PLAN.md` where applicable.  
11. ~~**Follow-up reminders**~~ — digest API/CLI + optional `scripts/email_follow_up_digest.py` (`services/follow_up_email.py`, `FOLLOW_UP_*` env).  
12. ~~**Answerer → policy**~~ — `answerer_manual_review_required` / `answerer_review` in `decide_apply_mode_with_reason` (`REASON_MANUAL_ANSWERER_REVIEW`).  
13. ~~**Streamlit export + answerer preview**~~ — `build_answerer_preview_for_export` + `enrich_job_dict_for_policy_export` on exports (`ui/streamlit_app.py`).
