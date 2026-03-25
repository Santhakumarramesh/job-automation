# External ATS (Workday, Greenhouse): manual_assist only

**Design rule:** Workday and Greenhouse fit this platform **as assisted autofill**, not as `safe_auto_apply`. Customization and legal/UX risk mean **no full auto-submit** for these providers in a market-ready v1.

**Aligns with:** [TWO_LANE_APPLY_STRATEGY.md](TWO_LANE_APPLY_STRATEGY.md), [AUTONOMY_MODEL.md](AUTONOMY_MODEL.md), [SYSTEM_VISION.md](SYSTEM_VISION.md), `services/policy_service.py`, `providers/ats/protocol.py`.

---

## 1. Principle

- Treat Workday and Greenhouse as **external ATS providers** behind a shared adapter surface (`providers/ats/` — `ATSAdapter`, registry).
- **Never** map them to `safe_auto_apply` in the initial product story; use **high-speed manual_assist**:
  - Autofill fields that are **`truth_safe` and `submit_safe`**.
  - **Stop before submit** for human review.

This matches how serious tools frame ATS overlays: **speed + control**, not full autonomy. See [Careery — AI auto-apply guide](https://careery.pro/blog/ai-job-search/ai-auto-apply-for-jobs-guide) and [Scoutify — SpeedyApply review](https://scoutify.ai/blog/speedyapply-review).

---

## 2. Implementation pattern

### 2.1 Provider abstraction

Concrete providers (existing or planned) implement the same ideas:

- **Detection:** URL/host → Workday vs Greenhouse (see `detect_ats_provider`, form hints).
- **Form understanding:** `analyze_form` / live probe where enabled — toward a `form_schema`.
- **Mapping:** `map_candidate_to_fields(truth_inventory, profile, form_schema) → autofill_values`.
- **Support mode (v1):** `support_mode() -> "manual_assist"` (conceptually; today `supports_auto_apply_v1()` is false for non-LinkedIn per `ATSAdapter`).

Greenhouse integrations in enterprise stacks often standardize **field mapping** before automation; same discipline applies here — [Findem on inbound + Greenhouse](https://www.findem.ai/blog/inbound-applications-greenhouse-ats).

### 2.2 MCP (policy + package engine)

For jobs where `ats_provider in {workday, greenhouse, lever, …}` (any non–LinkedIn Easy Apply auto lane):

- **`job_state` remains `manual_assist`** (not `safe_auto_apply`).
- Return structured outputs:
  - Tailored resume + cover letter + reports (as today).
  - **`autofill_values`** with per-field **answer state** (`safe` / `review` / `missing` / `blocked`).
  - **`truth_safe`** / **`submit_safe`** per field when the [application decision contract](MCP_APPLICATION_DECISION_CONTRACT.md) is implemented end-to-end.
  - Clear **`blocked`** reasons (e.g. unsupported required field).

### 2.3 Operator (OpenClaw / runner)

For Workday / Greenhouse in `manual_assist`:

- Open the application URL; confirm provider + **job identity** (title, company, location).
- Prefill **only** fields MCP marks safe; skip or highlight `review` / `missing` / `blocked`.
- Screenshots + structured logs.
- **Prompt the human** to review, complete remaining fields, and **submit manually**.

---

## 3. Workday variability

Workday differs **by tenant**; “standard” flows are easier to assist than heavily customized instances — [Scoutify — SpeedyApply / Workday](https://scoutify.ai/blog/speedyapply-review).

Production-oriented approach:

- Maintain **templates** (known layouts / field sets) where possible; custom mapping per template.
- **Unknown layout:** fill only **universal** fields (e.g. name, email, phone); treat the rest as **`review`**.
- **Never auto-submit** unknown Workday variants.

---

## 4. Integration hygiene (APIs & data)

If you later use **official APIs** or integrations:

- **Workday:** integration accounts, scoped permissions, least privilege (e.g. ISU-style patterns) — [Bindbee — Workday integrations](https://www.bindbee.dev/blog/beginners-guide-workday-integrations).
- **Greenhouse:** OAuth/scoped APIs per vendor docs; align **candidate, job, and application** fields to avoid duplication or loss — [Zythr — Greenhouse integrations](https://zythr.com/resources/the-best-greenhouse-ats-integrations-a-practical-guide).
- **Testing:** sandboxes / test reqs before production mapping — [Bindbee](https://www.bindbee.dev/blog/beginners-guide-workday-integrations).

---

## 5. Safe product messaging

You can say in README and sales copy:

- “Supports **assisted autofill** for popular ATS such as **Workday** and **Greenhouse**.”
- “External ATS flows run in **`manual_assist`**: we pre-fill **safe** fields; **you control submission**.”
- “We **do not** fully auto-submit on Workday/Greenhouse in v1; variability and risk are handled with **human review**.”

Broader ethics and limits of automation — [FastApply — safe and ethical](https://blog.fastapply.co/job-application-automation-is-it-safe-and-ethical).

---

## 6. Relation to “100% market-ready” story

A defensible **market-ready** promise is:

> A **supervised**, policy-gated candidate-ops platform with **narrow, high-confidence auto-apply** only for **confirmed LinkedIn Easy Apply**, plus **assisted autofill** for external ATS — **not** universal autonomous submit.

Characteristics serious buyers expect (quality, policy, observability, evidence) are summarized in vendor and review content such as [Valasys — automated job application tools](https://valasys.com/top-10-ai-tools-for-automated-job-applications-tested-and-ranked/), [Sapia — screening automation](https://sapia.ai/resources/blog/ai-candidate-screening-automation-tips/), and the Careery guide above.

**One line:** Truthful, supervised candidate-ops with a **narrow, telemetry-backed `safe_auto_apply` lane** (LinkedIn only) and **manual_assist with assisted autofill** for Workday/Greenhouse — promise, policy, and behavior aligned.

---

## References (external)

- [Careery — AI auto-apply guide](https://careery.pro/blog/ai-job-search/ai-auto-apply-for-jobs-guide)
- [Scoutify — SpeedyApply review](https://scoutify.ai/blog/speedyapply-review)
- [Findem — Greenhouse inbound](https://www.findem.ai/blog/inbound-applications-greenhouse-ats)
- [Bindbee — Workday integrations](https://www.bindbee.dev/blog/beginners-guide-workday-integrations)
- [Zythr — Greenhouse integrations](https://zythr.com/resources/the-best-greenhouse-ats-integrations-a-practical-guide)
- [FastApply — automation ethics](https://blog.fastapply.co/job-application-automation-is-it-safe-and-ethical)
- [Valasys — AI job application tools](https://valasys.com/top-10-ai-tools-for-automated-job-applications-tested-and-ranked/)
- [Sapia — AI candidate screening](https://sapia.ai/resources/blog/ai-candidate-screening-automation-tips/)
