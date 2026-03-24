# Technical Architecture: Career Co-Pilot Pro

**Vision:** A truthful high-fit job application copilot that uses your master resume to find the right jobs, maximize internal ATS alignment, generate tailored application materials, and auto-apply only when it is safe and appropriate.

**See also**

- **[TARGET_OPERATING_MODEL.md](TARGET_OPERATING_MODEL.md)** — Full upgraded product workflow (north star, phases 1–13).
- **[WORKFLOW_MODULE_MAP.md](WORKFLOW_MODULE_MAP.md)** — Numbered capabilities → repo paths + ✅/⚠️/📋 status.

---

## High-Level Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase A: Setup                                                               │
│ Master Resume → profile_service, master_resume_guard                          │
│ candidate_profile.json → profile_service, application_answerer               │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase B: Job Discovery                                                       │
│ providers/ (Apify, LinkedIn MCP) → registry → normalized JobListing         │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase C: Qualify                                                             │
│ fit gate (master_resume_guard) → ATS (enhanced_ats_checker) → tailor → CL    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase D: Apply Mode Decision                                                  │
│ policy_service.decide_apply_mode() → auto_easy_apply | manual_assist | skip   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                 ▼
           ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
           │ Auto Apply   │  │Manual-Assist │  │    Skip      │
           │ MCP + runner │  │ Package only │  │ No output    │
           └──────────────┘  └──────────────┘  └──────────────┘
                    │                 │
                    └────────┬────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase E–F: Execute, Track, Follow-up                                          │
│ services/application_tracker, MCP apply_to_jobs, audit log, recruiter follow-up │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Layer-by-Layer Mapping

### 1. Candidate Setup Layer

| Component | Path | Status |
|-----------|------|--------|
| Master resume | Uploaded in UI; `base_resume_text` in state | ✅ |
| Master resume parsing | `agents/master_resume_guard.py` – `parse_master_resume()` → `CandidateProfile` (skills, tools, projects, education, companies, raw_text_lower) | ✅ |
| Candidate profile | `config/candidate_profile.json`; `services/profile_service.py` – `load_profile()`, `validate_profile()`, `is_auto_apply_ready()` | ✅ |
| Profile answerer | `agents/application_answerer.py` – answers from `short_answers`, profile fields | ✅ |

**Truth inventory:** Master resume defines what can be claimed. `CandidateProfile` is the structured inventory used by fit gate and tailoring.

---

### 2. Job Discovery Layer

| Component | Path | Status |
|-----------|------|--------|
| Apify provider | `providers/apify_jobs.py` | ✅ |
| LinkedIn MCP provider | `providers/linkedin_mcp_jobs.py` | ✅ |
| Provider registry | `providers/registry.py` – `get_jobs()`, `list_providers()` | ✅ |
| Normalization | `providers/common_schema.py` – `JobListing` | ✅ |
| Role keyword extraction | Implicit in search params (target title, keywords from resume) | ⚠️ Partial |

**Flow:** Master resume text → search params → providers → normalized jobs. Ranking by recency and Easy Apply is provider-driven.

---

### 3. Job Normalization and Classification Layer

| Field | Source |
|-------|--------|
| job_id, source, title, company, location | `JobListing`, provider output |
| description, job_url, apply_url | Normalized in schema |
| `easy_apply_filter_used` | Search filter flag (Apify, LinkedIn MCP filter) | ✅ |
| `easy_apply_confirmed` | Per-job confirmation (MCP `confirm_easy_apply`) | ✅ |
| posted date, work mode, salary | Provider-dependent | ⚠️ Partial |

**Distinction enforced:** `easy_apply_filter_used` = search filter; `easy_apply_confirmed` = per-job verified. See `providers/linkedin_mcp_jobs.py`, `providers/common_schema.py`.

---

### 4. Truthful Fit Gate Layer

| Component | Path | Status |
|-----------|------|--------|
| Fit gate | `services/ats_service.py` – `check_fit_gate()` | ✅ |
| Master resume + JD check | `agents/master_resume_guard.py` – `is_job_fit()`, `compute_job_fit_score()` | ✅ |
| Fit decisions | `apply`, `review`, `reject` | ✅ |
| Unsupported requirements | Extracted and returned; blocks auto-apply | ✅ |
| Work authorization / clearance | Checked via `CandidateProfile` | ✅ |

**Flow:** `base_resume_text` → `parse_master_resume()` → `is_job_fit(profile, job)` → `FitResult(decision, score, reasons, unsupported_requirements)`.

---

### 5. ATS Scoring Layer

| Component | Path | Status |
|-----------|------|--------|
| ATS checker | `enhanced_ats_checker.py` – `comprehensive_ats_check()` | ✅ |
| Iterative optimizer | `agents/iterative_ats_optimizer.py`, `services/ats_service.run_iterative_ats()` | ✅ |
| Truth-safe mode | `truth_safe=True`; no unsupported keyword stuffing | ✅ |
| Target score 100 | Internal repo score; not employer ATS guarantee | ✅ Documented |

**Flow:** JD + resume → missing keywords → tailor → re-score → loop until target or max attempts.

---

### 6. Truth-Safe Tailoring Layer

| Component | Path | Status |
|-----------|------|--------|
| Resume tailoring | `agents/resume_editor.py` – `tailor_resume()` | ✅ |
| Humanization | `agents/humanize_resume.py`, `humanize_cover_letter.py` | ✅ |
| Resume naming | `services/resume_naming.py` – `{Name}_{Position}_at_{Company}_Resume.pdf` | ✅ |
| Cover letter | `agents/cover_letter_generator.py`, `services/document_service.generate_cover_letter_from_state()` | ✅ |

---

### 7. Application Package Assembly Layer

| Component | Path | Status |
|-----------|------|--------|
| Package contents | Resume PDF, cover letter PDF, ATS score, fit decision, autofill values | ✅ |
| MCP tool | `prepare_application_package` in `mcp_servers/job_apply_autofill/server.py` | ✅ |
| Short answers | From `application_answerer`; included in package | ✅ |

---

### 8. Humanized Application Answer Layer

| Component | Path | Status |
|-----------|------|--------|
| Answerer | `agents/application_answerer.py` | ✅ |
| Profile-backed answers | sponsorship, work auth, relocation, notice, salary, years-*, why_role, why_company | ✅ |
| Safe fallback | "Please review manually" when data missing | ✅ |

---

### 9. Apply-Mode Decision Layer

| Component | Path | Status |
|-----------|------|--------|
| Policy service | `services/policy_service.py` – `decide_apply_mode()`, `decide_apply_mode_with_reason()`, `policy_from_exported_job()` | ✅ |
| Inputs | job URL, fit_decision, ats_score, unsupported_requirements, easy_apply_confirmed, optional `profile_ready` | ✅ |
| Outputs | `auto_easy_apply` \| `manual_assist` \| `skip` + stable `policy_reason` codes (`REASON_*`) | ✅ |
| Threshold | `FIT_THRESHOLD_AUTO_APPLY = 85` | ✅ |

**Logic:**

- `skip` if fit ≠ apply, ATS < 85, or unsupported requirements
- `manual_assist` if not LinkedIn or Easy Apply not confirmed
- `auto_easy_apply` only when all conditions pass

---

### 10. Auto-Apply Execution Layer

| Component | Path | Status |
|-----------|------|--------|
| MCP server | `mcp_servers/job_apply_autofill/server.py` – `apply_to_jobs()` | ✅ |
| Runner | `agents/application_runner.py` – Playwright, field fill, upload | ✅ |
| Filters | Only jobs with `easy_apply_confirmed` and `apply_mode != "skip"` | ✅ |
| External ATS | Returns `manual_assist_ready`; never auto-submits | ✅ |
| Screenshots, Q&A audit | Captured and logged | ✅ |

---

### 11. Manual-Assist Lane

| Output | Status |
|--------|--------|
| Tailored resume | ✅ |
| Tailored cover letter | ✅ |
| Prefilled Q/A | ✅ |
| Links (LinkedIn, company) | ✅ |
| Checklist / paste guide | ⚠️ Partial (UI shows blocker summary) |

---

### 12. Tracking and Audit Layer

| Component | Path | Status |
|-----------|------|--------|
| Tracker schema | `services.application_tracker.TRACKER_COLUMNS` | ✅ |
| Fields | source, company, position, job_url, apply_url, fit_decision, ats_score, apply_mode, **policy_reason**, easy_apply_confirmed, resume_path, cover_letter_path, screenshots_path, qa_audit, submission_status, user_id | ✅ |
| Persistence | CSV or SQLite via `TRACKER_DB_PATH` / `sqlite:///…`; Postgres via `TRACKER_DATABASE_URL` or `DATABASE_URL` (`postgresql://…`) + `pip install .[postgres]`; schema revisions `alembic/` + `docs/MIGRATIONS.md` + `pip install .[migrations]` | ✅ |
| Audit log | `services/observability.audit_log()` → `application_audit.jsonl` | ✅ |

---

### 13. Post-Apply Follow-Up Layer

| Component | Path | Status |
|-----------|------|--------|
| Recruiter follow-up | `generate_recruiter_followup` MCP tool | ✅ |
| LinkedIn note, email template | In MCP tool | ⚠️ Partial |
| Reminders, prioritization | ❌ Not implemented |

---

### 14. Feedback Loop Layer

| Component | Path | Status |
|-----------|------|--------|
| Unmapped fields | `review_unmapped_fields` MCP tool | ✅ |
| Audit report | `application_audit_report` MCP tool | ✅ |
| Correlation (fit → recruiter response) | Tracked in schema; analysis manual | ⚠️ Partial |

---

## Full Workflow Chain (Implementation Map)

| # | Step | Module / Path |
|---|------|----------------|
| 1 | Upload master resume | `ui/streamlit_app.py` – Tab 1 |
| 2 | Fill candidate profile | `config/candidate_profile.json`, `profile_service` |
| 3 | Validate profile | `validate_profile()`, `is_auto_apply_ready()` |
| 4 | Search (LinkedIn MCP / Apify) | `providers/registry.get_jobs()` |
| 5 | Normalize jobs | `JobListing`, provider outputs |
| 6 | Confirm Easy Apply | MCP `confirm_easy_apply` |
| 7 | Rank by fit, recency | Provider + registry |
| 8 | Run fit gate | `check_fit_gate()` |
| 9 | Reject bad-fit | `decide_apply_mode` → skip |
| 10 | Score ATS | `run_iterative_ats()` |
| 11 | Tailor resume | `tailor_resume()`, `humanize_resume()` |
| 12 | Generate cover letter | `generate_cover_letter_from_state()` |
| 13 | Build application package | `prepare_application_package` |
| 14 | Decide apply mode | `decide_apply_mode()` |
| 15 | Auto / manual / skip | MCP filter, UI export |
| 16 | Autofill | `apply_to_jobs()` |
| 17 | Upload resume | Application runner |
| 18 | Answer questions | `application_answerer` |
| 19 | Submit when policy allows | Runner enforces |
| 20 | Capture screenshots | Runner |
| 21 | Log to tracker | `log_application_from_result()` |
| 22 | Generate follow-up | `generate_recruiter_followup` |
| 23 | Review failures | `review_unmapped_fields`, tracker |
| 24 | Improve profile, mappings | Manual + feedback tools |
| 25 | Improve policy | `policy_service` |

---

## Decision Logic Summary

### Auto Easy Apply (all must be true)

- LinkedIn job
- `easy_apply_confirmed = True`
- `fit_decision = "apply"`
- `ats_score >= 85`
- No unsupported requirements
- Profile validated (auto_apply_ready)
- No risky unanswered questions

### Manual-Assist

- Non–Easy Apply LinkedIn
- Greenhouse, Lever, Workday
- Longer custom forms
- Needs manual judgment

### Skip

- Poor fit
- Unsupported requirements
- Work authorization blocker
- ATS improvement not feasible truthfully

---

## Module Index

| Module | Purpose |
|--------|---------|
| `agents/master_resume_guard` | Parse resume, fit gate, job fit score |
| `agents/application_answerer` | Humanized answers; `answer_question_structured` + `manual_review_required` |
| `agents/application_runner` | Playwright apply; `answerer_review` + optional submit block |
| `agents/resume_editor` | Tailor resume |
| `agents/cover_letter_generator` | Generate cover letter |
| `services/policy_service` | `decide_apply_mode()` |
| `services/ats_service` | Fit gate, ATS, iterative optimization |
| `services/truth_safe_ats` | Truth-safe ATS ceiling heuristic |
| `services/profile_service` | Load, validate profile |
| `services/application_service` | Tracker access, get by job_id |
| `services/follow_up_service.py` | Phase 12 — follow-up queue from tracker |
| `services/follow_up_email.py` | Optional SMTP for follow-up digest script |
| `services/application_insights.py` | Phase 13 — tracker rollups, audit tail summary, hints; `GET /api/insights` |
| `services/application_tracker.py` | Log, load applications; `get_application_row_by_job_id` |
| `services/artifact_metadata.py` | Phase 3.2.3 — parse tracker row → structured artifacts for API |
| `services/object_storage.py` | Phase 3.4 — optional S3 upload + presigned URLs (`pip install .[s3]`) |
| `agents/celery_workflow.py` | Phase 3.3 — headless LangGraph for Celery workers |
| `app/tasks.py` | Celery `run_job`, enqueue, retries, S3 merge |
| `services/task_state_store.py` | Trimmed on-disk snapshots per task id |
| `services/idempotency_keys.py` | File-backed idempotent `POST /api/jobs` |
| `services/secrets_loader.py` | Phase 3.5 — optional AWS Secrets Manager → env |
| `services/startup_checks.py` | Phase 3.5 — production/strict validation, worker rules |
| `services/metrics_redis.py` | Phase 3.6 — Celery counters in Redis |
| `services/prometheus_setup.py` | Phase 3.6 — optional `/metrics` + HTTP counter |
| `providers/registry` | Job discovery, provider selection |
| `providers/common_schema` | `JobListing` |
| `mcp_servers/job_apply_autofill` | Apply tools, package prep, follow-up |
| `ui/streamlit_app` | UI tabs, graph, export |

---

## Gaps vs. Ideal Vision

| Gap | Current | Ideal |
|-----|---------|-------|
| Role keyword extraction | ✅ `extract_search_keywords()` from master resume | — |
| Reminders / follow-up scheduling | None | 3–5 day reminders, prioritization |
| Feedback correlation analysis | Manual | Automated fit vs. response correlation |
| Manual-assist checklist | Blocker summary | Paste-ready checklist, field mapping |
| Salary in job object | Provider-dependent | Normalized when available |

---

## Related Documents

- [TARGET_OPERATING_MODEL.md](TARGET_OPERATING_MODEL.md) – Target end-state workflow (qualification + execution + tracking + follow-up)
- [WORKFLOW_MODULE_MAP.md](WORKFLOW_MODULE_MAP.md) – Phase/item → module map
- [TWO_LANE_APPLY_STRATEGY.md](TWO_LANE_APPLY_STRATEGY.md) – Auto vs manual-assist
- [FIX_ROADMAP.md](FIX_ROADMAP.md) – Red / yellow / green reconciliation
- [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) – Status and known gaps
- [PHASE_3_PLAN.md](PHASE_3_PLAN.md) – Multi-user roadmap
- [setup/](setup/) – LinkedIn MCP & Job Apply MCP guides
