# Market & production audit checklist

**Purpose:** Roadmap for **supervised product now, narrow autonomous later** — truthful positioning, MCP-first policy, and explicit gaps vs today’s code.

**Related:** [SYSTEM_VISION.md](SYSTEM_VISION.md) (blueprint), [PRODUCT_SCOPE.md](PRODUCT_SCOPE.md), [AUTONOMY_MODEL.md](AUTONOMY_MODEL.md), [MARKET_PRODUCTION_ROADMAP.md](MARKET_PRODUCTION_ROADMAP.md), [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md), [TWO_LANE_APPLY_STRATEGY.md](TWO_LANE_APPLY_STRATEGY.md), [VISION_ARCHITECTURE_MAP.md](VISION_ARCHITECTURE_MAP.md), [REPO_HEALTH.md](REPO_HEALTH.md), `services/policy_service.py`, `mcp_servers/job_apply_autofill/server.py`.

**Terminology:** *OpenClaw* below means any external operator shell (browser automation, schedulers, or a named product) that **must not** override MCP policy outputs.

---

## Scores (working consensus)

| Dimension | Score | Note |
|--------|-------|------|
| Core platform readiness | **7.5 / 10** | API, tracker, MCP tools, policy hooks |
| Autonomous apply readiness | **4.5 / 10** | Keep out of marketing claims for v1 |
| Safe supervised product readiness | **8 / 10** | Credible with dry-run + human-in-the-loop |

---

## 1. Product positioning & messaging

**Goal:** Truthful, defensible market claim.

- [x] README tagline + opening paragraph: **production-minded candidate-ops**, **supervised, policy-gated**, narrow auto-submit wording.
- [x] README states: Easy Apply + policy; external ATS **manual-assist**; browser automation **supervised**, not hands-off production.
- [x] README **“What this is not”** (autonomous bot, browser guarantees, employer ATS guarantees).

**Status:** README **green** for core claims; marketing/site copy outside the repo is still **yellow** until aligned.

---

## 2. MCP as policy + package engine

**Goal:** MCP is the authority; other layers execute.

**Design + v0.1 code:** [MCP_APPLICATION_DECISION_CONTRACT.md](MCP_APPLICATION_DECISION_CONTRACT.md); `services/application_decision.build_application_decision`, MCP `get_application_decision`.

- [x] **Job states** in service/MCP payload: `skip`, `manual_assist`, `safe_auto_apply` (from `auto_easy_apply`), `blocked` (runner `blocked_reason` or error). `manual_review` for fit still maps to `skip` in policy until explicitly changed.
- [x] **Answer states** per canonical screening field: `safe` | `review` | `missing` (+ `blocked` reserved).
- [x] **`truth_safe` / `submit_safe`** per field (heuristic from answerer `reason_codes`).
- [x] Single payload: `job_state`, `answers`, `safe_to_submit`, `reasons`, `critical_unsatisfied`.
- [x] REST ``POST /api/ats/application-decision`` (MCP parity).
- [ ] Persist `job_state` / decision snapshot on tracker rows.

**Map to code today:** `enrich_job_dict_for_policy_export` + canonical answerer preview feed `build_application_decision`.

**Status:** Contract **green** for MCP/service; persistence + REST **yellow**.

---

## 3. Truth vs submission safety

**Goal:** Never lie; never auto-submit borderline truths.

- [ ] **Truth gate:** content only from truth inventory + profile + explicit rules; forbid new tools, years, locations, titles, credentials not in truth base.
- [ ] **Submission gate:** some truthful fields still `review` for auto (e.g. sponsorship, legal/compliance questions).
- [ ] Auto-submit only when:
  - Truth gate passes for **all critical** fields.
  - Submission gate passes — no `review` / `missing` / `blocked` on **critical** questions.

**Status:** Truth emphasis **green** conceptually; split truth vs submission enforcement **yellow**.

---

## 4. Resume optimization loop guardrails

**Goal:** Strong internal ATS alignment without hallucination.

- [ ] Cap loop: max **N** iterations (e.g. 3–5); early stop if score gain &lt; delta.
- [ ] Hard constraints: reuse existing facts/metrics only; no new tools/domains/achievements; no fake locations or seniority inflation.
- [ ] Structured output: `baseline_score`, `final_internal_ats_score`, `truthful_ceiling`, `iterations`.
- [ ] Two variants: ATS-oriented + human-readable (same facts).

**Status:** ATS direction **green**; formal loop caps + dual-variant contract **yellow** (partially present in iterative optimizer + truth-safe ceiling).

---

## 5. OpenClaw’s role and limits

**Goal:** Operator only — **never** policy.

OpenClaw **must not:**

- Decide job fit or final `job_state` (must consume MCP).
- Invent sponsorship / work authorization wording.
- Pick resume variant without MCP instruction.
- Submit when form structure diverges from expected template without human escalation.

OpenClaw **should:**

- Schedule runs; collect job links.
- Open pages; verify company / title / location.
- Confirm Easy Apply presence when instructed.
- Prefill only fields flagged **`truth_safe` & `submit_safe`**.
- Screenshots, logs, transient retry.
- Draft follow-ups from MCP text (**do not send** unless human approves).

**Status:** Architecture **green** in docs; enforced limits in configs + runbooks **yellow**.

---

## 6. Safe v1 vs narrow v2 automation

**V1 (ship credibly now)**

- **MCP:** truth inventory; fit + ATS; job / answer classification (evolve toward §2); tailored resume + cover + reports; `manual_assist` packages.
- **OpenClaw:** open page; identity check; Easy Apply check; safe prefill for manual-assist; screenshots + audit; transient retries; draft follow-ups.

**V2 (after telemetry)**

- **MCP:** mature loop tuning; threshold suggestions; profile improvement prompts from failures.
- **OpenClaw:** narrow `safe_auto_apply` class on LinkedIn only; capped daily volume.

---

## 7. CI, tests, and visibility

**Goal:** Obvious production discipline.

- [x] Visible CI: **`.github/workflows/ci.yml`** — pytest, example profile validation, `check_startup.py app` (template also kept at [setup/github-actions-ci.yml](setup/github-actions-ci.yml)).
- [x] README: CI badge + production links; health/metrics paths documented in [DEPLOY.md](DEPLOY.md) / [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md).
- [ ] Example prod env narrative in README (beyond badge): short pointer block for `APP_ENV=production`, auth, `TRACKER_USE_DB`, rate limits — [.env.example](../.env.example) + [SECRETS_AND_CONFIG.md](SECRETS_AND_CONFIG.md) remain source of truth.

**Status:** Public CI signal **green** once the workflow runs on `main` after push; extend with ruff/mypy when ready.

---

## 8. Browser apply stance

**Goal:** Correct risk expectations.

- [ ] Label browser apply: **supervised**; **dry-run first** for new environments.
- [ ] Document: LinkedIn checkpoints; external ATS fragility; manual-assist default off LinkedIn.
- [ ] Operating modes: human-in-the-loop for all non–`safe_auto_apply`; dry-run before hands-off.

**Status:** Docs **green** in [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md); marketing must stay aligned **yellow**.

---

## Short summary (reuse)

Position as a **supervised, policy-gated candidate-ops automation platform**, not a fire-and-forget job bot. Next upgrade: MCP as the formal package-and-decision engine with explicit **job** and **answer** states; external operators (e.g. OpenClaw) stay inside **`truth_safe` & `submit_safe`** and never cross **`safe_to_submit`** without MCP + human rules.
