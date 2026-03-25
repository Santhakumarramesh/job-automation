# Production readiness audit & phased roadmap (to 100% supervised + narrow autonomy)

**Purpose:** Honest snapshot of **this repo today** plus a **week-by-week style plan**. Scores are directional (not a formal certification).

**North-star docs:** [SYSTEM_VISION.md](SYSTEM_VISION.md), [PRODUCT_SCOPE.md](PRODUCT_SCOPE.md), [AUTONOMY_MODEL.md](AUTONOMY_MODEL.md), [MARKET_PRODUCTION_ROADMAP.md](MARKET_PRODUCTION_ROADMAP.md), [MARKET_PRODUCTION_AUDIT_CHECKLIST.md](MARKET_PRODUCTION_AUDIT_CHECKLIST.md).

---

## Scorecard (working)

| Dimension | Score | Note |
|-----------|-------|------|
| **Supervised / hosted platform** | **~7.5–8 / 10** | FastAPI, Celery, Redis, Postgres tracker path, Docker, auth, migrations, metrics hooks |
| **Autonomous apply (market claim)** | **~4.5 / 10** | Easy Apply path exists; checkpoints, DOM drift, and policy evidence limit “hands-off” claims |
| **Policy in product surface** | **~7 / 10** | Decision payload (MCP + REST); tracker **application_decision** JSON; Streamlit Job Finder + tracker snapshots + API tab |

---

## Current strengths (accurate for this repo)

- **Platform:** FastAPI + Celery + Redis; Postgres tracker via Alembic; `APP_ENV=production` / strict startup gates; [DEPLOY.md](DEPLOY.md), Docker Compose.
- **Truth & fit:** Master resume guard, truth inventory, fit gate, internal ATS + iterative optimizer (truth-safe ceiling); profile service + validation.
- **Execution:** Playwright apply runner, screenshots, policy in `application_runner` / `policy_service`.
- **Tracking:** Application tracker (CSV / SQLite / Postgres) with rich columns; admin/insights APIs.
- **Policy v0.1:** `services/application_decision.build_application_decision`, MCP `get_application_decision`, `POST /api/ats/application-decision` — structured `job_state`, per-field `answer_state`, `truth_safe`, `submit_safe`, `safe_to_submit` ([MCP_APPLICATION_DECISION_CONTRACT.md](MCP_APPLICATION_DECISION_CONTRACT.md)).
- **Docs & positioning:** README production scope; CI badge; vision/scope/autonomy/roadmap/external ATS strategy docs.
- **CI:** pytest, example profile validation, `check_startup.py app`; **Ruff** + **scoped mypy** (`mypy.ini`) — run locally or via [`contrib/github-actions-ci.yml`](../contrib/github-actions-ci.yml) copied to `.github/workflows/ci.yml` when your PAT can update workflows (**workflow** scope).

---

## Real gaps (what still blocks “100% supervised story”)

| Gap | Detail |
|-----|--------|
| **Persistence** | **Done (v0):** `application_decision` JSON on tracker writes; **indexed `job_state` column** populated on new writes (Postgres: `tracker_0008`; SQLite: `tracker_db` migrate). |
| **DB enums** | **Indexed `job_state` (v0):** VARCHAR + **contract normalization** at ingest (`normalize_job_state_for_tracker`); Postgres optional **ENUM** for `job_state` (`tracker_0010`). Per-field `answer_state` native ENUM remains optional future work. |
| **Streamlit supervision UX** | **Done (v0):** decision preview + tracker snapshot + REST tab; batch-apply **operator_submit_approved** path + **shadow_mode** toggle (Phase 2). |
| **Telemetry product** | Prometheus/Redis hooks exist; **v0** Grafana imports for API/Celery metrics ([`contrib/grafana/dashboard-career-co-pilot-v0.json`](../contrib/grafana/dashboard-career-co-pilot-v0.json)) and tracker `job_state` outcomes ([`contrib/grafana/dashboard-tracker-job-state-v0.json`](../contrib/grafana/dashboard-tracker-job-state-v0.json)). **Still roadmap:** richer SLO/incident panel bundles. |
| **Shadow mode** | **v0 done** (MCP/API/CLI + tracker labels); Job Finder toggle syncs **shadow_mode** to the batch-apply API tab. |
| **CI depth** | **Scoped mypy** + Ruff in [`contrib/github-actions-ci.yml`](../contrib/github-actions-ci.yml) (copy to `.github/workflows/` when PAT allows); coverage targets not enforced. |

---

## Phase 1 — 10/10 supervised product (order of work)

**Goal:** Credible **supervised, policy-gated** positioning with **visible** policy in UI and durable audit.

### Policy & API (partially done)

- [x] Structured **job_state** / **apply_mode_legacy** / **safe_to_submit** in service + MCP + REST.
- [x] Per canonical screening field: **answer_state**, **truth_safe**, **submit_safe** (heuristic from answerer `reason_codes`).
- [x] **Persist** last decision snapshot on tracker write paths (runner + `log_application` graph state).
- [x] **Indexed `job_state`:** column on `applications` + admin analytics `by_job_state`; filled from v0.1 decision JSON on log paths.
- [x] **Optional:** JSONB for `application_decision` (Postgres) — Alembic `tracker_0009`; `tracker_db` PG create/ensure + NULL for empty on write; [TRACKER_DASHBOARD_QUERIES.md](TRACKER_DASHBOARD_QUERIES.md).

### UI supervision

- [x] Streamlit: show **job_state**, **safe_to_submit**, **critical_unsatisfied**, per-field table from `build_application_decision` (Job Finder preview); tracker column snapshot expander; API tab POST.
- [x] **manual_assist:** table of fields with safe/review/missing + autofill preview (Job Finder supervision — sorted table, optional “all fields”, copy bundle).
- [x] **safe_auto_apply:** preconditions checklist + dry-run / shadow / CLI screenshot pointers (Job Finder supervision when `job_state` is `safe_auto_apply`; `safe_auto_apply_precondition_checklist` in `application_decision`).
- [x] Explicit **“I approve submit”** logging: `POST /api/ats/apply-to-jobs` with `operator_submit_approved` + optional `operator_submit_note` writes `operator_submit_approved` to `application_audit.jsonl` on **live** submit; optional gate `ATS_REQUIRE_OPERATOR_SUBMIT_APPROVAL=1`; Streamlit batch-apply requires the approval checkbox for live runs.

### Truth validation

- [x] Truth inventory + profile validation paths (MCP + scripts).
- [x] **Hard gate:** `TRUTH_APPLY_HARD_GATE=1` blocks **live** LinkedIn apply when profile is not auto-apply ready (`assess_truth_apply_profile` / `truth_apply_live_blocked_message` in `services/truth_apply_gate.py`); wired into `apply_to_jobs_payload`, `run_application` (LinkedIn), Streamlit Job Finder banner. Policy still downgrades exports when profile incomplete.

### CI & observability

- [x] **CI:** pytest + startup smoke on `main`/PRs.
- [x] **Ruff:** `[tool.ruff]` in `pyproject.toml` (subset: `E4`, `E7`, `E9`, `F`; per-file `E402` for `run_streamlit.py` / `scripts/regenerate_resume_pdf.py`). Add a CI step after `pip install`: `ruff check .` (requires `ruff` from `.[dev]`). **Note:** committing `.github/workflows/*.yml` may require a GitHub PAT with the **workflow** scope; keep the snippet local until then.
- [x] **mypy (v0 scoped):** `mypy.ini` + CI step `mypy --config-file mypy.ini` on stable API/policy/analytics modules (`app/auth.py`, `app/main.py`, `services/application_decision.py`, `services/application_insights.py`, `services/autonomy_submit_gate.py`, `services/role_templates.py`, `services/tracker_analytics.py`, `services/truth_apply_gate.py`, `services/workspace_write_guard.py`, `services/metrics_redis.py`, `services/prometheus_celery_bridge.py`, `services/prometheus_setup.py`, `services/apply_runner_metrics_redis.py`, `services/rate_limit.py`, `services/api_cors.py`). Broader repo typing remains iterative.
- [x] Example **dashboard queries** — [TRACKER_DASHBOARD_QUERIES.md](TRACKER_DASHBOARD_QUERIES.md) (admin summary API + SQL for `job_state` / JSONB).

**Phase 1 exit:** Supervised story is **demonstrable** in UI + DB, not only in MCP/REST payloads.

---

## Phase 2 — Shadow autonomy (4–6 weeks)

- [x] **v0:** LinkedIn **`shadow_mode`** (MCP / REST / CLI): fill through pre-submit, never submit; runner statuses + tracker **Shadow** / submission_status labels.
- [x] **Rollups (v0):** `compute_shadow_insights` + Streamlit insights metrics; heuristic suggestion when many shadow-would-apply vs few Applied.
- [x] **UI:** Streamlit **ATS / REST API** tab — batch apply expander with `dry_run` + **`shadow_mode`** checkboxes.
- [x] **Metrics (v0):** `compute_shadow_insights` + admin **`shadow_metrics_v0`** — `shadow_positive_rate` (would-apply / decided shadow rows), `shadow_to_applied_ratio`, `runner_issue_proxy_rows` / `_rate` (keyword heuristic on submission_status / status / `qa_audit`); `fp_fn_definitions_v0` documents limits (no employer ground truth). Deeper labeled FP/FN / DOM instrumentation remains roadmap.
- [x] **Tune fit/ATS (v0 advisory):** `closed_loop_hints_v0` + `policy_reference.FIT_THRESHOLD_AUTO_APPLY` in `compute_shadow_insights` / admin `shadow_metrics_v0` and surfaced in `compute_tracker_insights` **suggestions** — operators adjust gates manually; no auto mutation of policy.
- [x] Single Streamlit **Job Finder** toggle for **shadow_mode** on the next **LinkedIn batch apply** (syncs session `api_baj_shadow` with the ATS / REST API tab when LinkedIn rows are selected).

---

## Phase 3 — Narrow production autonomy (6–8 weeks)

- [x] **v0 gates:** `autonomy_submit_gate` — `AUTONOMY_LINKEDIN_LIVE_SUBMIT_DISABLED`, `AUTONOMY_LINKEDIN_PILOT_SUBMIT_ONLY` + job `pilot_submit_allowed`; Redis apply-runner counters for attempt/success/blocked.
- [x] Pilot cohort playbook (named users/workspaces): `AUTONOMY_LINKEDIN_PILOT_USER_IDS` / `AUTONOMY_LINKEDIN_PILOT_WORKSPACE_IDS` (see [AUTONOMY_MODEL.md](AUTONOMY_MODEL.md)).
- [x] **Telemetry rollback (v0):** `AUTONOMY_LINKEDIN_ROLLBACK_WHEN_FAILURE_RATE_GTE` + `AUTONOMY_LINKEDIN_ROLLBACK_MIN_ATTEMPTS` — auto-block live submit when Redis failure rate exceeds threshold (after min attempts).
- [x] **Broader auto-downgrade (v0):** `AUTONOMY_LINKEDIN_ROLLBACK_WHEN_NONSUBMIT_RATE_GTE` + `AUTONOMY_LINKEDIN_ROLLBACK_NONSUBMIT_MIN_EVENTS` in `autonomy_submit_gate` — Redis ratio of `(checkpoint_pause + challenge_abort) / (nonsubmit + live_submit_attempt)`; evaluated after submit-failure rollback; see [AUTONOMY_MODEL.md](AUTONOMY_MODEL.md).
- [x] Public readiness checklist: [AUTONOMY_MODEL.md — Public readiness](AUTONOMY_MODEL.md#public-readiness-narrow-autonomy) (release notes still manual).

---

## Phase 4 — Scale & polish (ongoing)

- [x] **Admin tracker analytics (v0):** `GET /api/admin/tracker-analytics/summary` — rollups by `status`, `submission_status`, `recruiter_response`, cross-tab `status_by_recruiter_response`, `applied_by_recruiter_response`, **`by_applied_iso_week`**, **`by_job_state`** (when column populated), and `rows_with_parseable_applied_at`; optional `user_id` / `workspace_id` filters and `max_rows` cap (`services/tracker_analytics.py`).
- [x] **Versioned CI sample:** [`contrib/github-actions-ci.yml`](../contrib/github-actions-ci.yml) — copy to `.github/workflows/ci.yml` when your token has **workflow** scope (avoids losing the Ruff/pytest steps when workflow files cannot be pushed).
- [x] **Workspace on enqueue (v0):** optional `API_ENFORCE_USER_WORKSPACE_ON_WRITES` + `API_WORKSPACE_ENFORCE_FOR_ADMIN` — `services/workspace_write_guard.py` on `POST /api/jobs` and LinkedIn batch apply (see [DEPLOY.md](DEPLOY.md)).
- [x] **LinkedIn ATS auth (v0):** optional `API_ATS_LINKEDIN_REQUIRE_AUTH` — rejects `demo-user` on confirm/apply routes; batch apply stamps `user_id` when missing.
- [x] Tenant hardening for admin reads: `API_WORKSPACE_ENFORCE_FOR_ADMIN` (full org-level RBAC + fine-grained roles still roadmap).
- [x] **Mobile / operator UI + role templates (v0):** Streamlit mobile-friendly CSS + caption for batch-apply approvals; optional JWT **`JWT_ROLE_TEMPLATE_CLAIM`** + **`JWT_ROLE_TEMPLATE_MAP`** (+ **`M2M_ROLE_TEMPLATE`**) in `services/role_templates.py` / `app/auth.py`. Full installable PWA (manifest/service worker) remains optional / reverse-proxy-owned.
- [x] **Deeper analytics (v0):** `timeseries_v0` on admin tracker summary (`by_applied_iso_week_utc`, `by_applied_month_utc`) + `GET /api/admin/tracker-analytics/export` (`kind=csv|json`, slim columns for BI). Grafana panels remain optional/ops-owned.

---

## Phase 5 — Data quality & ops (ongoing)

- [x] **`job_state` index hygiene (v0):** `normalize_job_state_for_tracker` + `CANONICAL_JOB_STATES` in `services/application_decision.py` — indexed tracker column only accepts contract values (`skip`, `manual_review`, `manual_assist`, `safe_auto_apply`, `blocked`); bad JWT/hand-edited JSON does not pollute `by_job_state` rollups.
- [x] **mypy (v0 scoped):** `mypy.ini` + CI step on stable API/policy/analytics modules; full-repo strict typing remains optional iterative hardening.
- [x] **Postgres ENUM** for `job_state` (optional) — `alembic/versions/tracker_0010_job_state_enum.py` + Postgres write-path stores empty job_state as SQL NULL (SQLite/CSV keep strings).
- [x] **Grafana samples (v0):** [`contrib/grafana/dashboard-career-co-pilot-v0.json`](../contrib/grafana/dashboard-career-co-pilot-v0.json) for API/Celery metrics + [`contrib/grafana/dashboard-tracker-job-state-v0.json`](../contrib/grafana/dashboard-tracker-job-state-v0.json) for tracker `job_state` outcomes.
- [x] **Release notes cadence (v0):** [`docs/RELEASE_NOTES_CADENCE.md`](../docs/RELEASE_NOTES_CADENCE.md) + root [`CHANGELOG.md`](../CHANGELOG.md) — when to update for autonomy/public readiness; links to [AUTONOMY_MODEL.md](AUTONOMY_MODEL.md#public-readiness-narrow-autonomy).

---

## “Next 48 hours” checklist (reconciled with repo)

| # | Task | Status |
|---|------|--------|
| 1 | Enums / DB columns for `job_state` | **Done:** VARCHAR index + ingest normalization + optional Postgres ENUM migration |
| 2 | MCP decision structured states | **Done** — `get_application_decision` + `build_application_decision` |
| 3 | README “Current production scope” + doc links | **Done** |
| 4 | GitHub Actions CI | **Sample in repo:** [`contrib/github-actions-ci.yml`](../contrib/github-actions-ci.yml) — copy to `.github/workflows/ci.yml` when PAT has **workflow** scope (ruff, scoped mypy, pytest, profile, startup) |
| 5 | Vision docs committed | **Done** — `SYSTEM_VISION`, `PRODUCT_SCOPE`, `AUTONOMY_MODEL`, `MARKET_PRODUCTION_ROADMAP`, plus audit checklist, external ATS, decision contract |

**Actual immediate priorities:** expand mypy coverage beyond v0 scope; deepen Grafana/tracker panels beyond the v0 sample ([`contrib/grafana/dashboard-career-co-pilot-v0.json`](../contrib/grafana/dashboard-career-co-pilot-v0.json)); keep [CHANGELOG.md](../CHANGELOG.md) current when autonomy gates or pilot posture changes ([`docs/RELEASE_NOTES_CADENCE.md`](../docs/RELEASE_NOTES_CADENCE.md)).

---

## External references (background)

- FastAPI + Celery patterns: [TestDriven.io — FastAPI and Celery](https://testdriven.io/blog/fastapi-and-celery/)
- General production mindset (video): [YouTube — Ct6-2x_F-Og](https://www.youtube.com/watch?v=Ct6-2x_F-Og)

These are **context**, not requirements of this codebase.
