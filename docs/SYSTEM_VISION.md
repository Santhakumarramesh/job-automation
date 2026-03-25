# System Vision: Candidate‑Ops Platform

## Current status

- Core direction: **supervised, policy‑gated candidate‑ops platform**, not a fire‑and‑forget bot.
- Default operating mode: **manual_assist** (supervised + safe prefill).
- Narrow `safe_auto_apply` exists in the model but is **not generally enabled** yet.

> See also:
> - [Product Scope & Guarantees](PRODUCT_SCOPE.md)
> - [Autonomy & Policy Model](AUTONOMY_MODEL.md)
> - [Market Production Roadmap](MARKET_PRODUCTION_ROADMAP.md)
> - [Market Production Audit Checklist](MARKET_PRODUCTION_AUDIT_CHECKLIST.md)
> - [MCP Application Decision Contract](MCP_APPLICATION_DECISION_CONTRACT.md)

---

## 1. Core vision

Build a **production‑minded candidate operations platform** that moves a user from job discovery to application execution in a **truthful, controlled, and progressively automatable** way.

This is **not** a fire‑and‑forget job bot.

It is a **supervised, policy‑gated system** where:

- **MCP backend** is the **brain and policy engine**.
- **OpenClaw (or equivalent runner)** is the **operator and execution layer**.
- **Claude Desktop / UI** is the **command center**.
- **Claude Code / dev tools** are the **development and maintenance workspace**.
- **The human** remains the final authority for risky actions until narrow autonomy is earned via telemetry.

---

## 2. What the product actually is

**Positioning**

> A supervised, policy‑gated candidate‑ops platform for job applications, with narrow high‑confidence auto‑apply only for a small safe class.

**What it does**

- Manages **candidate truth data** (master resume + profile → truth inventory).
- Scores **job fit** and **internal ATS alignment**.
- Prepares **tailored application packages** (resumes, cover letters, reports).
- Classifies **answers and risks** (safe / review / missing / blocked).
- Fills **safe fields automatically** in job forms.
- Supports **manual‑assist** workflows for external ATS.
- Can eventually **auto‑submit** only in a tightly defined `safe_auto_apply` lane.

**What it does *not* claim**

- Guaranteed ATS success or employer shortlist.
- Zero browser failures.
- Universal support for every ATS and form pattern.
- Fully autonomous application behavior across the internet.

Honest scope is part of the design.

---

## 3. High‑level architecture

### 3.1 Candidate truth layer

The **truth layer** is the foundation.

It stores:

- Master resumes.
- Candidate profile (contact details, work authorization, relocation rules, salary rules).
- Short answers and reusable responses.
- Links (LinkedIn, GitHub, portfolio).
- Approved job preferences.
- A **truth inventory** extracted from resumes/profile.

This is the **single source of truth**. Nothing is submitted unless it can be grounded here.

Example structure:

```text
career-co-pilot-pro/
├── Master_Resumes/
├── config/
│   ├── candidate_profile.example.json
│   └── candidate_profile.json
├── generated_resumes/
├── run_results/
├── logs/
├── docs/
└── ...
```

### 3.2 MCP layer (brain + policy engine)

MCP is the **brain** and **policy engine**.

Responsibilities:

- Validate candidate profile and truth base.
- Build truth inventory from resume(s).
- Score job fit; detect unsupported requirements.
- Score internal ATS alignment.
- Classify answers into **safe / review / missing / blocked**.
- Generate:
  - Tailored resume.
  - Humanized resume.
  - Cover letter.
  - Fit report and ATS report.
- Decide job state:
  - `skip`, `manual_review`, `manual_assist`, `safe_auto_apply`, `blocked`.
- Compute:
  - `truth_safe`, `submit_safe` per answer.
  - Global `safe_to_submit` per job.

MCP should return **structured decisions**, not just prose.

### 3.3 OpenClaw layer (operator)

OpenClaw is the **operator**, not the judge.

Responsibilities:

- Open job pages.
- Verify page identity (company/title/location).
- Confirm Easy Apply or known form type.
- Fill only fields marked safe (`truth_safe` & `submit_safe`).
- Upload the approved resume package.
- Take screenshots and collect structured logs.
- Retry on transient errors; abort on DOM mismatch.
- Never invent answers or override MCP decisions.
- Prepare recruiter follow‑up drafts (not auto‑send by default).

OpenClaw handles **mechanics**, not **policy**.

**External ATS (Workday, Greenhouse, Lever, etc.):** Stay in **`manual_assist`** — assisted autofill for `truth_safe` + `submit_safe` fields only; **human submits**. Never **`safe_auto_apply`** for these in v1. Details: [EXTERNAL_ATS_MANUAL_ASSIST.md](EXTERNAL_ATS_MANUAL_ASSIST.md).

### 3.4 Claude Desktop layer (command center)

Claude Desktop (or similar UI) is the **command center**.

Used to request:

- Profile validation.
- Job search and ranking.
- Package generation.
- Dry‑run and audit flows.
- Follow‑up generation.
- Production‑readiness checks.

It orchestrates MCP and the runner in natural language, but it does not change the policy model.

### 3.5 Claude Code / dev tools (builder workspace)

Claude Code and developer tools are the **engineering interface**.

Used to:

- Inspect and refactor the repo.
- Edit config files and rules.
- Improve scoring logic and state models.
- Debug MCP ↔ OpenClaw integration.
- Keep docs aligned with implementation.
- Maintain the production roadmap.

---

## 4. Control model: who decides what

**Principle**

> MCP decides. OpenClaw executes. You supervise.

- MCP decides:
  - Job fit and job state.
  - Truthfulness of answers.
  - Sponsorship/authorization wording.
  - Which resume/package to use.
  - Whether `safe_to_submit` can be true.

- OpenClaw:
  - Executes only within those decisions.
  - Never fabricates or overrides truth/policy.

---

## 5. State‑machine model

### 5.1 Job states

First‑class in API, DB, logs, and UI:

- `skip` – Not worth pursuing. No automation.
- `manual_review` – Needs human judgment before any automation.
- `manual_assist` – Automation may prepare packages and prefill safe fields, but never submit.
- `safe_auto_apply` – Narrow, highly controlled class where auto‑submit can be allowed.
- `blocked` – Hard stop due to truth/policy/technical constraints.

### 5.2 Answer states

Every answer/field is classified as:

- `safe` – Approved and usable automatically.
- `review` – Truthful but requires human judgment.
- `missing` – Required data absent; triggers profile/rule updates.
- `blocked` – Must not be auto‑used.

### 5.3 Two safety flags per answer

For each answer, MCP computes:

- `truth_safe`
  - Grounded in:
    - Master resume.
    - Candidate profile.
    - Explicit rules and approved answer bank.
- `submit_safe`
  - Truth‑safe, and also safe to use automatically in this form context.

Example: a truthful sponsorship answer may still be `review` for submission.

### 5.4 One auto‑submit gate

Per job, MCP exposes:

- `safe_to_submit: true/false`

`safe_to_submit` is `true` only if:

- Job state is `safe_auto_apply`.
- Fit and ATS thresholds are met.
- No critical answers are `review`, `missing`, or `blocked`.
- All critical answers are both `truth_safe` and `submit_safe`.
- Form/page checks pass.
- Package generation succeeded.
- Pacing/rate‑limit rules are respected.

OpenClaw treats `safe_to_submit == false` as **no auto‑submit**.

---

## 6. Application workflow (phases)

1. **Truth base setup**
   - Upload real resumes.
   - Create and complete `candidate_profile.json`.
   - Define work authorization, relocation, salary, short answers.
   - Add approved links and locations.

2. **Validation**
   - MCP validates profile completeness.
   - Extracts truth inventory.
   - Detects missing/blocked answers.
   - Flags risky or incomplete areas.

3. **Job targeting**
   - Discover and normalize jobs.
   - Score fit; detect unsupported requirements.
   - Estimate internal ATS alignment.
   - Assign job state (`skip`, `manual_review`, `manual_assist`, etc.).

4. **Package generation**
   - For qualified jobs:
     - Tailored and humanized resumes.
     - Cover letter.
     - Fit and ATS reports.
     - Autofill values and answer classifications.

5. **Execution support**
   - OpenClaw:
     - Opens job pages; verifies identity and form type.
     - Prefills safe fields.
     - Uploads approved documents.
     - Captures screenshots and logs.

6. **Dry run**
   - Run full flows without live submit:
     - Verify selectors and field mappings.
     - Verify packages and logs.
     - Confirm no unsupported auto‑submit path exists.

7. **Live supervised use (default)**
   - Default job state: `manual_assist`.
   - MCP prepares everything.
   - OpenClaw fills safe fields.
   - Human reviews and submits.

8. **Narrow auto‑submit (later)**
   - Job moved to `safe_auto_apply` only when strict policy & telemetry gates are met.
   - Auto‑submit restricted to safe LinkedIn Easy Apply patterns.

---

## 7. OpenClaw’s safe role

**Good tasks for OpenClaw**

- Collect job links.
- Open pages and verify identity.
- Prefill safe fields.
- Retry transient failures.
- Capture screenshots and logs.
- Prepare recruiter follow‑up drafts.
- Notify about blocked or review‑needed cases.

**Bad tasks for OpenClaw**

- Deciding job fit or job state.
- Inventing answers or changing truth.
- Rewording sponsorship/authorization answers.
- Choosing resume content.
- Answering ambiguous legal/employment questions autonomously.
- Submitting outside the `safe_auto_apply` lane.

OpenClaw is the **worker**, not the judge.

---

## 8. Production scope levels

Explicit autonomy levels:

- **Level 1 – Fully supervised**
  - Human reviews everything.
  - No auto‑submit.
  - System mainly analyzes and prepares.

- **Level 2 – Supervised + safe prefill** (default)
  - MCP decides; OpenClaw pre‑fills safe fields.
  - Human reviews and submits.
  - External ATS = **manual_assist** only.

- **Level 3 – Narrow autonomous**
  - Only for `safe_auto_apply`.
  - Only in supported LinkedIn Easy Apply patterns.
  - Only after shadow‑mode telemetry and pilot data prove safety.

---

## 9. Production‑readiness path

To go from ~7.5/10 → 10/10, work in four areas:

1. **Product truth**
   - Docs, README, and marketing say the same thing:
     - Supervised by default.
     - Narrow auto‑submit only in a safe lane.
     - External ATS manual‑assist only.
     - No universal automation claims.

2. **Technical robustness**
   - CI/CD, tests, lint, type checks.
   - Durable DB and migrations; backups and restore plan.
   - Observability (metrics, correlation IDs).
   - Idempotent job processing, per‑user caps, pacing.
   - Structured error codes; versioned scoring logic.

3. **Safety and policy**
   - First‑class job and answer states.
   - `truth_safe`, `submit_safe`, `safe_to_submit` implemented.
   - Explicit skip/review/block behavior.
   - Hard no‑invention rules for resume claims.

4. **Evidence**
   - Shadow mode for autonomy.
   - Pilot users for narrow `safe_auto_apply`.
   - Telemetry‑based threshold tuning.
   - Failure/rollback analysis.
   - Public readiness checklist.

Without evidence, 10/10 is only a design claim, not a production claim.

---

## 10. North star

> A supervised candidate‑ops platform with a narrow, well‑governed `safe_auto_apply` mode, backed by clear state machines, strong truth guarantees, readiness checks, and real‑world telemetry showing low error rates for exactly the behaviors the product claims.

This document, together with `PRODUCT_SCOPE.md`, `AUTONOMY_MODEL.md`, and `MARKET_PRODUCTION_ROADMAP.md`, is the blueprint for reaching that standard.
