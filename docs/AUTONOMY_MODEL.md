# Autonomy & Policy Model

> See also:
> - [System Vision](SYSTEM_VISION.md) (full blueprint)
> - [Product Scope & Guarantees](PRODUCT_SCOPE.md)
> - [Market Production Roadmap](MARKET_PRODUCTION_ROADMAP.md)
> - [MCP Application Decision Contract](MCP_APPLICATION_DECISION_CONTRACT.md) (technical v0 shape)

## Current status

- Live default job state: **manual_assist** (supervised).
- `safe_auto_apply` exists in the model but is **not broadly enabled** yet.
- All external ATS flows run in **manual_assist** or lower (Workday/Greenhouse: assisted autofill, never `safe_auto_apply` in v1 — [EXTERNAL_ATS_MANUAL_ASSIST.md](EXTERNAL_ATS_MANUAL_ASSIST.md)).

---

## Roles in the system

The system divides responsibility across three main actors:

- **MCP backend (this repo):**
  - The **policy + package engine**.
  - Owns truth inventory, fit scoring, ATS scoring, answer classification, job states, and the `safe_to_submit` decision.

- **Runner / browser automation layer (e.g., OpenClaw or similar):**
  - The **operator**.
  - Owns scheduling, opening pages, verifying page identity, safe prefill, retries, screenshots, and logging.
  - Never invents truth or override policy decisions.

- **Human + assistant client (e.g., Claude Desktop / UI):**
  - The **supervisor**.
  - Reviews boundary‑crossing actions (especially submissions), updates profile/rules, and approves or rejects recommendations.

This separation keeps **truth and policy** inside the backend, and **execution** in a controlled operator layer.

---

## Job state machine

All jobs evaluated by the system are assigned one of the following **job states**:

- `skip`
  - Clear mismatch or hard blocker.
  - No automation or package generation beyond logging.

- `manual_review`
  - Borderline or unclear fit.
  - System may produce a summary and reports, but no browser actions.

- `manual_assist`
  - Good fit, but requires human involvement.
  - System prepares a full application package.
  - Operator may open the form and pre‑fill **safe** fields only.
  - Human reviews and submits.

- `safe_auto_apply`
  - Narrow, high‑confidence class of jobs (e.g., LinkedIn Easy Apply in known patterns).
  - System prepares a full package and, under strict conditions, allows auto‑submit.

- `blocked`
  - Truth or policy prevents safe apply:
    - Critical answers are `blocked` or irreparably `missing`.
    - Form context is unknown or risky.
  - No apply action is allowed.

These states must be **first‑class**: represented in the DB schema, API responses, logs, and UI.

---

## Answer state machine

For each application question or field, the system assigns an **answer state**:

- `safe`
  - Truthful and acceptable for auto‑submit.
  - Grounded in truth inventory and aligned with submission policies.

- `review`
  - Truthful but requires human review before use.
  - Example: sensitive sponsorship wording, special policy questions.

- `missing`
  - Required information is not present in profile/rules/truth inventory.
  - Triggers **profile enrichment** or new rule creation, not just ad‑hoc human typing.

- `blocked`
  - Cannot be answered truthfully and safely.
  - Example: employer asks for something the candidate definitively does not have.

Answer states are used both to gate **auto‑submit** and to drive **profile improvements**.

---

## Truth safety vs submission safety

The system separates two key concepts:

- **Truth safety (`truth_safe`)**
  - Answer content is grounded in:
    - Master resume truth inventory.
    - Candidate profile fields.
    - Explicitly configured rules (e.g., salary band, sponsorship stance).
  - No invented skills, titles, locations, years of experience, or credentials.

- **Submission safety (`submit_safe`)**
  - Even if truth‑safe, an answer may not be suitable for auto‑submit.
  - Evaluates whether the answer is:
    - Appropriate for this job’s jurisdiction and context.
    - Within configured risk tolerance (e.g., legal/HR sensitivities).

Only answers that are both **truth_safe** and **submit_safe** can be auto‑filled in autonomous flows.

---

## Auto‑submit eligibility (`safe_auto_apply`)

A job is eligible for auto‑submit only when **all** of the following conditions are met:

1. **Job state**
   - `job_state == safe_auto_apply`.

2. **Fit and ATS**
   - Fit score ≥ configured threshold.
   - Final internal ATS score ≥ threshold and ≤ truthful ceiling.

3. **Answer safety**
   - All **critical** questions have answer_state = `safe`.
   - No critical question is in `review`, `missing`, or `blocked`.
   - All critical answers are `truth_safe` and `submit_safe`.

4. **Form structure**
   - The apply flow matches a known, previously validated pattern (e.g., specific LinkedIn Easy Apply modal structure).
   - Page identity checks (title, company, location) pass.

5. **Package readiness**
   - Tailored resume and any required documents are generated successfully.
   - No errors in the package pipeline.

If any of these conditions fail, the job must be downgraded to `manual_assist` or `blocked`.

---

## Rewrite / rescore limits

To avoid over‑optimization and hallucinations, the ATS optimization loop is constrained:

- Maximum number of rewrite/rescore passes (e.g., 3–5).
- Early stop when the score improvement per pass is below a small delta.
- Strict fact rules:
  - No new tools, domains, roles, metrics, or achievements.
  - No location or seniority inflation.
  - Only rephrasing, re‑ordering, and emphasizing **existing** facts.

The system maintains:

- An **ATS‑optimized** resume variant.
- A **human‑readable** resume variant using the same facts.

---

## `safe_to_submit` decision

For each job, the backend computes a single boolean:

- `safe_to_submit: true/false`

This value is derived from:

- Job state.
- Answer states + truth_safe/submit_safe.
- Fit and ATS thresholds.
- Form template recognition.

The operator layer must treat `safe_to_submit == false` as a **hard stop** for auto‑submit.

---

## Phase 2 — Shadow mode (v0, implemented)

**Goal:** Exercise the same LinkedIn Easy Apply fill path through **pre‑submit**, but **never click Submit**, and record intent for telemetry.

**How to enable**

- MCP **`apply_to_jobs`**: `shadow_mode=True` (optional `dry_run=True`; shadow labeling wins when both are set).
- REST **`POST /api/ats/apply-to-jobs`**: `"shadow_mode": true` in JSON.
- REST dry-run alias: **`POST /api/ats/apply-to-jobs/dry-run`** with `"shadow_mode": true` for fill + shadow statuses.
- CLI: `python scripts/apply_linkedin_jobs.py jobs.json --shadow`.

**Runner statuses**

- `shadow_would_apply` — filled through pre‑submit; **would** have proceeded to submit under current `block_submit_on_answerer_review` rules (i.e. no pending answerer manual review).
- `shadow_would_not_apply` — same fill path, but **would not** auto‑submit because answerer fields require manual review (or analogous pre‑submit gate).

**Tracker**

- **Status** column: `Shadow`.
- **submission_status**: `Shadow – Would Apply` or `Shadow – Would Not Apply`.
- **`application_decision`** JSON is still computed on log (v0.1 contract) for audit.

**Limits (v0)**

- External ATS (`manual_assist` lane) is unchanged; shadow semantics apply primarily to **LinkedIn Easy Apply** in this iteration.
- Alignment metrics (“shadow vs human”) and UI toggles are **roadmap** on top of these logs.

---

## Phase 3 — Narrow live submit gates (v0, implemented)

**Goal:** Operators can **stop** or **scope** LinkedIn **live** submit (actual Submit click) without changing dry-run / shadow behavior.

**Environment variables** (see `services/autonomy_submit_gate.py`)

| Variable | Effect |
|----------|--------|
| `AUTONOMY_LINKEDIN_LIVE_SUBMIT_DISABLED=1` | Blocks **all** live LinkedIn submits. Runner returns `skipped` with `error` prefix `autonomy: …`. |
| `AUTONOMY_LINKEDIN_PILOT_SUBMIT_ONLY=1` | Live submit **only** if the job has `pilot_submit_allowed: true` (or legacy `pilot_submit: true`), **or** (when allowlists below are non-empty) `user_id` / `authenticated_user_id` matches `AUTONOMY_LINKEDIN_PILOT_USER_IDS`, or `workspace_id` / `organization_id` matches `AUTONOMY_LINKEDIN_PILOT_WORKSPACE_IDS` (comma-separated IDs, trimmed). If both allowlist env vars are empty, only per-job pilot flags apply. |
| `AUTONOMY_LINKEDIN_PILOT_USER_IDS` | Optional comma-separated user IDs; used only when `PILOT_SUBMIT_ONLY` is on and non-empty. |
| `AUTONOMY_LINKEDIN_PILOT_WORKSPACE_IDS` | Optional comma-separated workspace/org IDs; same semantics as user allowlist. |
| `AUTONOMY_LINKEDIN_ROLLBACK_WHEN_FAILURE_RATE_GTE` | Optional float in `(0, 1]`. When set, after at least `AUTONOMY_LINKEDIN_ROLLBACK_MIN_ATTEMPTS` live-submit **attempts** in Redis, blocks new submits if `(attempt − success) / attempt` **≥** this value. Requires Redis (`REDIS_METRICS_URL` / `REDIS_BROKER`). |
| `AUTONOMY_LINKEDIN_ROLLBACK_MIN_ATTEMPTS` | Minimum `linkedin_live_submit_attempt_total` before rollback can trigger (default `10`). |

**Evaluation order (live submit):** `LIVE_SUBMIT_DISABLED` → **telemetry rollback** (if configured) → `PILOT_SUBMIT_ONLY` (if on).

**Default:** none of the blocking env vars set → **same behavior as before** (live submit when the runner would submit).

**Telemetry (optional Redis)**

With `APPLY_RUNNER_METRICS_REDIS=1`, counters include:

- `linkedin_live_submit_attempt_total`
- `linkedin_live_submit_success_total`
- `linkedin_live_submit_blocked_autonomy_total`

**Admin read:** `GET /api/admin/apply-runner-metrics` (admin auth) returns the Redis hash summary via `read_apply_runner_metrics_summary` (or `enabled: false` / error when Redis is unavailable).

**Tracker**

- Blocked jobs log as usual; `submission_status` **Skipped – Autonomy Gate** when `error` starts with `autonomy:`.

**Pilot workflow**

1. Run **shadow** on a cohort; review `tracker.shadow` vs real **Applied**.
2. Enable **`AUTONOMY_LINKEDIN_PILOT_SUBMIT_ONLY=1`**; either add `pilot_submit_allowed: true` to vetted jobs in export JSON, **or** set **`AUTONOMY_LINKEDIN_PILOT_USER_IDS`** / **`AUTONOMY_LINKEDIN_PILOT_WORKSPACE_IDS`** so all jobs for known pilot users/workspaces can live-submit without per-job flags.
3. Use **`AUTONOMY_LINKEDIN_LIVE_SUBMIT_DISABLED=1`** for instant rollback during incidents.
4. Optionally set **`AUTONOMY_LINKEDIN_ROLLBACK_WHEN_FAILURE_RATE_GTE`** so sustained submit failures (from Redis counters) automatically block further live submits until you adjust thresholds or reset counters.

---

## Public readiness (narrow autonomy)

Use this as an **operator / release** checklist before widening live auto-submit beyond a pilot.

1. **Scope:** Document where live submit is allowed (e.g. LinkedIn Easy Apply only; external ATS remains `manual_assist`). Point to this file and [PRODUCT_SCOPE.md](PRODUCT_SCOPE.md).
2. **Evidence:** Run **shadow** on a representative cohort; compare tracker **Shadow – Would Apply** vs **Applied** and review `application_decision` snapshots. Capture a short summary (date range, counts, known limitations).
3. **Controls:** Confirm env gates are set for the target environment — kill switch, pilot-only and/or allowlists, optional **failure-rate rollback** — and that `APPLY_RUNNER_METRICS_REDIS=1` is on if you rely on counters or rollback.
4. **Observability:** Use `GET /api/admin/apply-runner-metrics` (or your own Redis/Grafana views) for `linkedin_live_submit_*` totals; align with tracker `submission_status` and **Skipped – Autonomy Gate** rows.
5. **Incident:** Document who can flip `AUTONOMY_LINKEDIN_LIVE_SUBMIT_DISABLED=1` and how to verify the runner is respecting it (dry-run/smoke job).
