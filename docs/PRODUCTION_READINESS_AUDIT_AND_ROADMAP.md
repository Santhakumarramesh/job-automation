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
- **CI:** [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) — pytest, example profile validation, `check_startup.py app` (extend with ruff/mypy when ready).

---

## Real gaps (what still blocks “100% supervised story”)

| Gap | Detail |
|-----|--------|
| **Persistence** | **Done (v0):** `application_decision` JSON on tracker writes; optional indexed `job_state` column still open. |
| **DB enums** | No Alembic migration adding dedicated `job_state` / `answer_state` columns; tracker uses strings (`apply_mode`, `policy_reason`, etc.). |
| **Streamlit supervision UX** | **Partial:** Job Finder “Supervision — application decision” + tracker snapshot expander + REST tab POST; **open:** explicit “I approve submit” audit + shadow toggle (Phase 2). |
| **Telemetry product** | Prometheus/Redis hooks exist; **no** bundled Grafana job dashboard or “success by job_state” rollup as a shipped artifact. |
| **Shadow mode** | Not implemented as a first-class run mode (log “would have applied” vs human). |
| **CI depth** | Ruff/mypy not required in CI yet; coverage targets not enforced. |

---

## Phase 1 — 10/10 supervised product (order of work)

**Goal:** Credible **supervised, policy-gated** positioning with **visible** policy in UI and durable audit.

### Policy & API (partially done)

- [x] Structured **job_state** / **apply_mode_legacy** / **safe_to_submit** in service + MCP + REST.
- [x] Per canonical screening field: **answer_state**, **truth_safe**, **submit_safe** (heuristic from answerer `reason_codes`).
- [x] **Persist** last decision snapshot on tracker write paths (runner + `log_application` graph state).
- [ ] **Optional:** SQLAlchemy/Alembic columns or JSONB for `application_decision` + indexed `job_state`.

### UI supervision

- [x] Streamlit: show **job_state**, **safe_to_submit**, **critical_unsatisfied**, per-field table from `build_application_decision` (Job Finder preview); tracker column snapshot expander; API tab POST.
- [ ] **manual_assist:** table of fields with safe/review/missing + autofill preview.
- [ ] **safe_auto_apply:** show preconditions checklist + link to dry-run / screenshots (when available).
- [ ] Explicit **“I approve submit”** logging (audit trail) before live submit in UI flows.

### Truth validation

- [x] Truth inventory + profile validation paths (MCP + scripts).
- [ ] **Hard gate:** block or downgrade apply when critical profile/truth missing (single function called from runner + UI).

### CI & observability

- [x] **CI:** pytest + startup smoke on `main`/PRs.
- [ ] Add **ruff** (and optionally **mypy**) to CI when the tree is clean enough.
- [ ] Document or ship example **dashboard queries** (job_state, apply outcomes) using existing metrics/tracker exports.

**Phase 1 exit:** Supervised story is **demonstrable** in UI + DB, not only in MCP/REST payloads.

---

## Phase 2 — Shadow autonomy (4–6 weeks)

- [x] **v0:** LinkedIn **`shadow_mode`** (MCP / REST / CLI): fill through pre-submit, never submit; runner statuses + tracker **Shadow** / submission_status labels.
- [x] **Rollups (v0):** `compute_shadow_insights` + Streamlit insights metrics; heuristic suggestion when many shadow-would-apply vs few Applied.
- [x] **UI:** Streamlit **ATS / REST API** tab — batch apply expander with `dry_run` + **`shadow_mode`** checkboxes.
- [ ] Metrics: formal alignment rate, FP/FN estimates, DOM failure rate (deeper telemetry).
- [ ] Tune fit/ATS thresholds from shadow data (closed loop).
- [ ] Single Streamlit **Job Finder** toggle “next run: shadow” (without opening API tab) — optional.

---

## Phase 3 — Narrow production autonomy (6–8 weeks)

- [x] **v0 gates:** `autonomy_submit_gate` — `AUTONOMY_LINKEDIN_LIVE_SUBMIT_DISABLED`, `AUTONOMY_LINKEDIN_PILOT_SUBMIT_ONLY` + job `pilot_submit_allowed`; Redis apply-runner counters for attempt/success/blocked.
- [x] Pilot cohort playbook (named users/workspaces): `AUTONOMY_LINKEDIN_PILOT_USER_IDS` / `AUTONOMY_LINKEDIN_PILOT_WORKSPACE_IDS` (see [AUTONOMY_MODEL.md](AUTONOMY_MODEL.md)).
- [x] **Telemetry rollback (v0):** `AUTONOMY_LINKEDIN_ROLLBACK_WHEN_FAILURE_RATE_GTE` + `AUTONOMY_LINKEDIN_ROLLBACK_MIN_ATTEMPTS` — auto-block live submit when Redis failure rate exceeds threshold (after min attempts).
- [ ] Broader auto-downgrade (pattern-level / non-submit failures) — roadmap.
- [x] Public readiness checklist: [AUTONOMY_MODEL.md — Public readiness](AUTONOMY_MODEL.md#public-readiness-narrow-autonomy) (release notes still manual).

---

## Phase 4 — Scale & polish (ongoing)

- Multi-tenant hardening, mobile/PWA approvals, role templates, analytics on response rates by state — **roadmap only** until Phase 1–3 are stable.

---

## “Next 48 hours” checklist (reconciled with repo)

| # | Task | Status |
|---|------|--------|
| 1 | Enums / DB columns for `job_state` | **Open** — design migration + tracker write path |
| 2 | MCP decision structured states | **Done** — `get_application_decision` + `build_application_decision` |
| 3 | README “Current production scope” + doc links | **Done** |
| 4 | `.github/workflows/ci.yml` | **Done** (pytest + profile + startup; extend later) |
| 5 | Vision docs committed | **Done** — `SYSTEM_VISION`, `PRODUCT_SCOPE`, `AUTONOMY_MODEL`, `MARKET_PRODUCTION_ROADMAP`, plus audit checklist, external ATS, decision contract |

**Actual immediate priorities:** **ruff in CI**; optional indexed `job_state` on tracker; explicit submit-approval audit log; Phase 2 shadow mode.

---

## External references (background)

- FastAPI + Celery patterns: [TestDriven.io — FastAPI and Celery](https://testdriven.io/blog/fastapi-and-celery/)
- General production mindset (video): [YouTube — Ct6-2x_F-Og](https://www.youtube.com/watch?v=Ct6-2x_F-Og)

These are **context**, not requirements of this codebase.
