# Changelog

Notable changes to **Career Co-Pilot Pro** are listed here. For autonomy and operator-facing expectations, also follow [docs/RELEASE_NOTES_CADENCE.md](docs/RELEASE_NOTES_CADENCE.md).

The format is inspired by [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased — Market Positioning & State Machine Hardening] — 2026-03-26

### Added
- **`docs/PRODUCT_BRIEF.md`** — market-ready product brief: problem statement, target user, core workflows, autonomy ladder (Phase 1/2/3), competitive differentiators, MVP scope, pricing direction, and priority build list. Primary external-facing document for investors, users, and contributors.

### Changed
- **`README.md`** — repositioned hero from "Job Application Automation" to "Supervised Candidate-Ops Platform". New tagline: *"Career Co-Pilot Pro is a supervised candidate-ops platform that helps serious job seekers run a truthful, high-signal, faster application workflow."* Clarified operating model (MCP = policy brain, browser = executor, human = final authority). Added PRODUCT_BRIEF to the doc table. Updated Overview section to name the target user and link to brief.
- **`agents/state.py`** — hardened `AgentState` TypedDict with first-class state fields:
  - `JobState` literal type: `skip | manual_review | manual_assist | safe_auto_apply | blocked`
  - `AnswerState` literal type: `safe | review | missing | blocked`
  - `FitDecision` literal type: `apply | manual_review | reject`
  - New fields: `job_state`, `previous_job_state`, `answer_states` (dict), `critical_fields` (list)
  - Truth/submission safety gates: `truth_safe`, `submit_safe`, `safe_to_submit` (bool) — with docstring enforcing operator hard-stop on `safe_to_submit=False`
  - Telemetry fields: `run_id`, `shadow_mode`, `dry_run`, `application_decision`, `submission_status`, `error`
  - `workspace_id` for multi-tenant isolation
- **`mcp_servers/job_apply_autofill/server.py`** — updated module docstring and `_MCP_INSTRUCTIONS` to reflect supervised candidate-ops positioning, job/answer state model, and link to PRODUCT_BRIEF and AUTONOMY_MODEL docs. Removed "autofill bot" framing.

### Positioning note
> **Do not present this as a bot. Present it as a candidate operating system.**
> Market-ready as a supervised candidate-ops platform (Phase 1). Shadow autonomy (Phase 2) and narrow live-submit (Phase 3) are implemented and available with pilot evidence gates.

## [Unreleased]

### Changed

- Set `asyncio_default_fixture_loop_scope = "function"` in `pyproject.toml` to remove pytest-asyncio default-scope deprecation noise and keep test behavior explicit.
- Added `CCP_FAST_PIPELINE=1` speed mode and `CCP_OPENAI_MODEL` model override for the Celery worker LLM pipeline (resume tailoring + cover letter; optionally skips humanization and project generation).
- In `CCP_FAST_PIPELINE=1` mode, if `CCP_OPENAI_MODEL` is unset the pipeline now defaults to `gpt-4o-mini` automatically (faster LLM responses).
- Added `CCP_FAST_BROWSER_PIPELINE=1` + `CCP_BROWSER_WAIT_MULTIPLIER` to reduce Playwright runner wait delays (`agents/application_runner.py`) when you want faster fills.
- In fast browser mode, scoped Easy Apply DOM scans to the modal dialog and added a field-fill cap (`CCP_FAST_BROWSER_FIELDS_MAX`) to reduce per-application latency.
- Expanded scoped `mypy.ini` coverage to infra utility services: `services/observability.py`, `services/secrets_loader.py`, `services/task_state_store.py`, `services/idempotency_keys.py`, `services/idempotency_db.py`.
- Added `tests/conftest.py` autouse fixture to isolate tracker DB/CSV per test (`tmp_path`), preventing row-count bleed between tests.
- Expanded scoped `mypy.ini` coverage to HTTP/metrics middleware: `services/prometheus_setup.py`, `services/apply_runner_metrics_redis.py`, `services/rate_limit.py`, `services/api_cors.py`.
- Expanded scoped `mypy.ini` coverage to policy/tracker/startup/profile services: `services/policy_service.py`, `services/tracker_db.py`, `services/application_tracker.py`, `services/startup_checks.py`, `services/profile_service.py`.
- Expanded scoped `mypy.ini` coverage to queue/context surfaces: `app/tasks.py`, `services/tracker_context.py`.
- Truthful ATS optimizer now classifies JD keywords into supported/partial/unsupported, filters additions to supported evidence only, and returns supported keyword buckets + truth-safe ceiling metadata in resume packages.
- Discovery flow now applies a high-confidence prefilter with role/seniority/location/work-auth/ATS feasibility gates and annotates job search results with prefilter buckets.
- Added ATS-safe one-page resume designer with deterministic templates, date normalization, optional PDF rendering, and package-level PDF generation hooks.
- Added fit-to-one-page compression engine with deterministic formatting ladder, summary/bullet/project trimming, and compression logs.
- Apply queue now enforces review-first states, moves to ready_for_approval only after package generation, and surfaces recommended actions + unsupported counts in queue rows.
- Added user approval workflow with explicit approve/hold/reject/send-back actions, approval metadata binding to resume version, and review payload snapshots.
- Added resume version store + upload binding to lock approved PDFs, plus queue bindings for approved resume version/path.
- Added portal resume replacement engine with LinkedIn Easy Apply adapter, resume state detection, upload verification, and runner blocking when resume verification fails.
- Apply queue execution now enforces approved resume bindings and passes job-specific approved resume paths through the runner.
- Hardened apply_queue schema migration to backfill missing columns on older DBs.
- Added Phase 10 one-by-one queue runner with guardrails, runner_state tracking, and MCP `run_approved_queue` wired to the approved-queue executor.
- Added Phase 11 lifecycle tracking: new tracker columns for fit/package/approval/queue/runner/final states, audit events for package generation/approval, resume replacement, runner transitions, and application submission.
- Phase 12 UI refactor: `ui/streamlit_app.py` now routes by `APP_MODE` to candidate vs operator UIs, and candidate workflow shows one-page resume previews plus runner/queue lifecycle states.
- Added MCP orchestration tool `evaluate_job_and_prepare_action_plan` to return normalized job, fit, ATS, policy job_state, answer risk summary, package artifacts, and next action.
- Added approved-answer memory store with MCP tools (get/save/list/suggest/mark-review) and answerer integration that reuses approved answers without bypassing truth/policy gates.

### Documentation

- CI sample now runs a deterministic tracker-isolation regression slice before full pytest.
- Added tracker Grafana starter: [contrib/grafana/dashboard-tracker-job-state-v0.json](contrib/grafana/dashboard-tracker-job-state-v0.json) for `job_state` counts / applied-rate / weekly trend.
- Added [docs/RELEASE_NOTES_CADENCE.md](docs/RELEASE_NOTES_CADENCE.md) describing when and how to update release notes alongside [AUTONOMY_MODEL.md](docs/AUTONOMY_MODEL.md) public readiness.

---

## Earlier history

Commits before this changelog: see repository history on your Git host.
