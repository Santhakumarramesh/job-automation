# MCP application decision contract (design)

**Status:** **v0.1 implemented** in `services/application_decision.py` (`build_application_decision`), MCP tool `get_application_decision`, and **REST** ``POST /api/ats/application-decision``.

**Implements checklist:** [MARKET_PRODUCTION_AUDIT_CHECKLIST.md](MARKET_PRODUCTION_AUDIT_CHECKLIST.md) §2–§3.

**Product narrative:** [SYSTEM_VISION.md](SYSTEM_VISION.md), [AUTONOMY_MODEL.md](AUTONOMY_MODEL.md), [PRODUCT_SCOPE.md](PRODUCT_SCOPE.md).

**Related code today:** `services/policy_service.py` (`decide_apply_mode`, `policy_reason`), `agents/master_resume_guard.py` (fit gate), `agents/application_answerer.py` (`answer_question_structured`, `build_answerer_preview_for_export`), `agents/application_runner.py` (runtime gates).

---

## Goals

1. **One authoritative payload** per job (or per application attempt) that any client (Claude, OpenClaw, Streamlit) can consume without re-deriving policy.
2. Separate **truth** (grounded in resume + profile) from **submit safety** (OK to auto-fill / auto-submit in context).
3. Stable enums and `reasons[]` for audit logs and UI.

---

## Canonical enums

### `job_state` (external contract name)

| Value | Meaning |
|--------|--------|
| `skip` | Do not apply; policy or fit says no. |
| `manual_review` | Human should decide (borderline fit, ambiguous JD, or “worth a look” but not auto). |
| `manual_assist` | Good to prepare package / prefill; human submits or reviews form. |
| `safe_auto_apply` | Narrow class: policy allows automated Easy Apply submit (today: `auto_easy_apply`). |
| `blocked` | Hard stop (e.g. checkpoint, captcha, unexpected form — set by runner, not MCP policy alone). |

### `answer_state` (per question / canonical screening key)

| Value | Meaning |
|--------|--------|
| `safe` | Has a value; `manual_review_required` false; acceptable for auto pipeline. |
| `review` | Has a value but needs human confirmation before auto-submit (e.g. sponsorship, generic LLM path). |
| `missing` | No truthful value available from profile + rules. |
| `blocked` | Must not auto-answer (compliance / unknown question class — rare; optional). |

### Per-answer flags (orthogonal)

- **`truth_safe`**: Answer text is derived only from allowed sources (profile fields, structured short answers, formatted mailing address, truth inventory rules). *Heuristic:* no `REASON_GENERIC_LLM`, no bare `REASON_PLACEHOLDER_MANUAL` without operator override.
- **`submit_safe`**: Allowed to use this field in an **auto-submit** step. Typically `truth_safe && !manual_review_required` for **critical** question types (sponsorship, salary, work authorization, mailing address, etc.).

---

## Proposed response shape (v0)

```json
{
  "schema_version": "0.1",
  "job_state": "manual_assist",
  "safe_to_submit": false,
  "apply_mode_legacy": "manual_assist",
  "policy_reason": "manual_assist_external_apply_url",
  "fit_decision": "apply",
  "reasons": ["manual_assist_external_apply_url"],
  "answers": {
    "sponsorship": {
      "answer_state": "review",
      "truth_safe": true,
      "submit_safe": false,
      "text": "STEM OPT with valid EAD; discuss long-term sponsorship",
      "reason_codes": []
    },
    "salary": {
      "answer_state": "safe",
      "truth_safe": true,
      "submit_safe": true,
      "text": "Negotiable",
      "reason_codes": []
    }
  },
  "critical_unsatisfied": ["sponsorship"]
}
```

- **`safe_to_submit`**: `true` only if `job_state == "safe_auto_apply"` **and** every **critical** key in `answers` has `submit_safe == true` and `answer_state != "missing"`.
- **`apply_mode_legacy`**: preserves today’s `auto_easy_apply` | `manual_assist` | `skip` for backward compatibility.
- **`critical_unsatisfied`**: list of canonical keys still blocking auto-submit (product-defined list; start with export preview keys from `application_answerer._CANONICAL_EXPORT_KEYS`).

---

## Mapping: today → `job_state`

| Today (`apply_mode`) | Typical `job_state` | Notes |
|----------------------|---------------------|--------|
| `skip` | `skip` | `policy_reason` distinguishes fit vs ATS vs unsupported vs location skip. |
| `manual_assist` | `manual_assist` | External ATS, Easy Apply unconfirmed, profile incomplete, answerer review, etc. |
| `auto_easy_apply` | `safe_auto_apply` | Rename in external contract only; same bar as current auto lane. |

**Fit gate (`fit_decision`):** Today anything other than `apply` yields `skip` + `skip_fit_decision_not_apply`. For richer UX, a future version may emit `job_state: manual_review` when `fit_decision == manual_review` *instead of* lumping into `skip`, without changing runner defaults until explicitly enabled.

---

## Mapping: `AnswerResult` → `answer_state`

From `answer_question_structured` (`agents/application_answerer.py`):

| Condition | `answer_state` | `submit_safe` (default) |
|-----------|----------------|-------------------------|
| `manual_review_required` and empty / placeholder | `missing` or `review` | `false` |
| `manual_review_required` and non-empty (e.g. generic LLM) | `review` | `false` for critical types |
| not `manual_review_required`, non-empty answer | `safe` | `true` for non-sensitive; `false` for sponsorship if policy says “always review” (configurable) |

**`reason_codes`** pass through as today (`reason_codes` list) for debugging.

---

## Implementation phases

| Phase | Deliverable |
|--------|-------------|
| **0** | This document + checklist link. |
| **1** | `build_application_decision` in `services/application_decision.py` + `tests/test_application_decision.py`. |
| **2** | MCP tool `get_application_decision` in `mcp_servers/job_apply_autofill/server.py`. |
| **3** | REST `POST /api/ats/application-decision` mirroring MCP **done**. |
| **4** | Runner sets `job_state: blocked` + reasons when browser hits checkpoint / fatal form mismatch. |

---

## Non-goals (v0)

- OpenClaw or any client inferring policy without reading this payload.
- Promising employer ATS outcomes (see [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md)).
- Auto-submit for non–LinkedIn Easy Apply — Workday/Greenhouse remain **`manual_assist`** only ([EXTERNAL_ATS_MANUAL_ASSIST.md](EXTERNAL_ATS_MANUAL_ASSIST.md)).

---

## Open questions

1. **Critical keys list** — fixed vs per-employer / per-form profile.
2. **Sponsorship** — always `submit_safe: false` until human checks a box in UI (safest v1).
3. **`manual_review` vs `skip`** for borderline fit — product and compliance preference.
