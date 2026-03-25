# Market Production Roadmap

> See also:
> - [System Vision](SYSTEM_VISION.md) (full blueprint)
> - [Product Scope & Guarantees](PRODUCT_SCOPE.md)
> - [Autonomy & Policy Model](AUTONOMY_MODEL.md)
> - [Market Production Audit Checklist](MARKET_PRODUCTION_AUDIT_CHECKLIST.md)
> - [Production Readiness Audit & Roadmap](PRODUCTION_READINESS_AUDIT_AND_ROADMAP.md) (repo-accurate status + phases)

## Current status

- **Phase 1–3:** Supervised product, shadow mode, and narrow live-submit gates are implemented (see [AUTONOMY_MODEL.md](AUTONOMY_MODEL.md) and the audit roadmap).
- **Phase 4:** Scale & polish — **in progress** (e.g. admin tracker analytics); multi-tenant RBAC and deeper BI remain roadmap.

---

## Target ladder

The roadmap uses a three‑step target:

1. **10/10 supervised product**
   - Product can be marketed as a **supervised, policy‑gated automation platform**.
   - All high‑risk actions remain human‑approved.

2. **8/10 narrow autonomy in shadow mode**
   - System generates full auto‑apply decisions and payloads but **does not submit**.
   - Logs “would have applied” runs for comparison and tuning.

3. **10/10 narrow autonomy in production**
   - After telemetry and pilot data, enable `safe_auto_apply` for a narrow class of LinkedIn Easy Apply jobs.
   - Maintain clear boundaries and public documentation of where autonomy applies.

---

## Phase 1 – 10/10 supervised product

**Goal:** A credible, production‑ready supervised product.

**Key deliverables:**

- Documentation:
  - `PRODUCT_SCOPE.md` defines what is promised and what is out of scope.
  - `AUTONOMY_MODEL.md` defines job/answer states and safety gates.
- Backend:
  - Truth inventory from master resume + profile.
  - Fit scoring and internal ATS scoring.
  - Job state machine implemented and persisted (`skip`, `manual_review`, `manual_assist`, `safe_auto_apply`, `blocked`).
  - Answer state machine implemented and persisted (`safe`, `review`, `missing`, `blocked`).
  - `truth_safe`, `submit_safe`, and `safe_to_submit` implemented and used in decisions.
  - Resume/cover‑letter package generation stable and covered by tests.
- Platform:
  - CI pipeline (tests, lint, type checks) enforced on main and PRs.
  - Production deployment guide with health, metrics, and logging guidance.
- Browser / operator:
  - Opens job pages and verifies identity.
  - Pre‑fills only fields marked safe.
  - Does **not** auto‑submit by default.
  - Captures screenshots and structured logs for audits.

At the end of Phase 1, the system is safe to market as a **supervised automation product**.

---

## Phase 2 – 8/10 narrow autonomy in shadow mode

**Goal:** Validate autonomy decisions without real submits.

**Key activities:**

- Shadow‑mode runs:
  - For selected users/jobs, system:
    - Computes job_state and `safe_to_submit`.
    - Builds a full `safe_auto_apply` payload.
    - Simulates the application without clicking submit.
  - Logs:
    - “Would have applied” vs actual human decisions.
    - Differences in job_state and answer_state usage.

- Metrics:
  - Alignment rate between shadow decisions and human actions.
  - Frequency of misclassified or later‑corrected `safe_auto_apply`.
  - Error and DOM failure rates in simulated flows.

- Adjustments:
  - Tune fit thresholds and ATS thresholds based on outcomes.
  - Refine critical question lists and answer classification rules.
  - Improve detection of unknown/risky form templates.

At the end of Phase 2, the system has **evidence** for where autonomy is safe.

---

## Phase 3 – 10/10 narrow autonomy in production

**Goal:** Enable real `safe_auto_apply` for a narrow, well‑justified class.

**Prerequisites (this repo, incremental):**

- Use **Phase 2 shadow** runs + tracker rollups (`insights` → `tracker.shadow`) to compare **Shadow – Would Apply** vs real **Applied** on the same job cohort before widening live submit.
- Keep external ATS in **manual_assist**; pilot scope stays **LinkedIn Easy Apply** only until evidence says otherwise.

**Key steps:**

- **Operator gates (v0):** env `AUTONOMY_LINKEDIN_LIVE_SUBMIT_DISABLED` / `AUTONOMY_LINKEDIN_PILOT_SUBMIT_ONLY` + job `pilot_submit_allowed`; Redis `linkedin_live_submit_*` counters. Details: [AUTONOMY_MODEL.md](AUTONOMY_MODEL.md) (Phase 3).

- Pilot enablement:
  - Turn on real `safe_auto_apply` auto‑submit for:
    - A small number of users.
    - Strictly filtered LinkedIn Easy Apply jobs.
  - Keep all external ATS flows in `manual_assist`.

- Telemetry and guardrails:
  - Monitor:
    - Success vs failure rates for auto‑submit.
    - Rollbacks or manual overrides.
    - Any unexpected form changes or mis‑identification.
  - Optional **automatic** pause of live submit when Redis counters exceed a configured failure rate (`AUTONOMY_LINKEDIN_ROLLBACK_WHEN_FAILURE_RATE_GTE` — [AUTONOMY_MODEL.md](AUTONOMY_MODEL.md) Phase 3).
  - Immediate downgrade of jobs or patterns that show issues.

- Public readiness checklist:
  - Use [AUTONOMY_MODEL.md — Public readiness](AUTONOMY_MODEL.md#public-readiness-narrow-autonomy) (scope, evidence, controls, observability, incident).
  - Keep release notes aligned with what is enabled in each environment.

At the end of Phase 3, the system can truthfully claim **narrow, well‑governed autonomy** in line with the documented scope.

---

## Phase 4 — Scale & polish (ongoing)

**Goal:** Operate safely across more users and workspaces with better observability.

**Started (v0):**

- **Admin tracker analytics:** `GET /api/admin/tracker-analytics/summary` (admin API key) — pipeline and outcome counts, recruiter-response breakdown for applied rows, optional `user_id` / `workspace_id` filters. See [PRODUCTION_READINESS_AUDIT_AND_ROADMAP.md](PRODUCTION_READINESS_AUDIT_AND_ROADMAP.md) Phase 4.
- **Enqueue / batch apply workspace guard:** optional `API_ENFORCE_USER_WORKSPACE_ON_WRITES` so tenants cannot stamp another `workspace_id` on `POST /api/jobs` or LinkedIn `apply-to-jobs` (batch default or per-job) ([DEPLOY.md](DEPLOY.md)).
- **LinkedIn ATS auth:** optional `API_ATS_LINKEDIN_REQUIRE_AUTH` so headless apply / confirm routes require a real API key or JWT (not open `demo-user`).

**Still roadmap:** multi-tenant RBAC hardening, mobile/PWA approvals, role templates, time-series / BI exports.

---

## Evidence as a release gate

Autonomy is earned by **telemetry**, not by design confidence alone.

For each step up in autonomy:

- Require:
  - Measured shadow performance.
  - Pilot data with low error/rollback rates.
  - Updated docs and safeguards.
- Only then:
  - Extend `safe_auto_apply` to more users or job classes.

---

## North star

> This project aims to be a **supervised candidate‑ops platform with a narrow, well‑governed `safe_auto_apply` mode**, where the marketed promise, policy model, technical controls, and real‑world telemetry all match.
