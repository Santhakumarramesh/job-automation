# Pass/Fail Checklist

Verification checklist for each module. Use this to confirm the repo meets the three core safety rules before live use.

## The 3 Core Rules

| # | Rule | Status |
|---|------|--------|
| 1 | **Easy Apply only** for auto-submit | ✅ Enforced |
| 2 | **Confirmed** Easy Apply ≠ filter-used Easy Apply | ✅ Enforced |
| 3 | Greenhouse / Lever / Workday = **manual-assist only** | ✅ Enforced |

---

## Module-by-Module

### 1. `providers/linkedin_mcp_jobs.py`

| Check | Pass? | Evidence |
|-------|-------|----------|
| `easy_apply` only True when MCP confirms | ✅ | Line 151: `"easy_apply": easy_apply_confirmed` |
| `easy_apply_filter_used` reflects search filter | ✅ | Line 152: `"easy_apply_filter_used": easy_apply` |
| `easy_apply_confirmed` from MCP response only | ✅ | `_extract_easy_apply_confirmed()` |

### 2. `providers/common_schema.py`

| Check | Pass? | Evidence |
|-------|-------|----------|
| `easy_apply_confirmed` field exists | ✅ | `JobListing` dataclass |
| `easy_apply_filter_used` field exists | ✅ | `JobListing` dataclass |
| `apply_mode` field (auto_easy_apply \| manual_assist \| skip) | ✅ | `JobListing` dataclass |

### 3. `services/policy_service.py`

| Check | Pass? | Evidence |
|-------|-------|----------|
| `decide_apply_mode()` uses `easy_apply_confirmed` | ✅ | Returns `manual_assist` when not confirmed |
| LinkedIn + confirmed → `auto_easy_apply` | ✅ | `decide_apply_mode()` |
| External URL → `manual_assist` | ✅ | `"linkedin.com" not in url` check |
| Fit/ATS/skip logic | ✅ | Fit≠apply, ats<85, unsupported → skip |

### 4. `providers/registry.py`

| Check | Pass? | Evidence |
|-------|-------|----------|
| Computes `apply_mode` for each job | ✅ | Calls `decide_apply_mode()` after fetch |

### 5. `mcp_servers/job_apply_autofill/server.py`

| Check | Pass? | Evidence |
|-------|-------|----------|
| Rejects jobs without `easy_apply_confirmed` | ✅ | Filter at lines 154-155 |
| Rejects `apply_mode == "skip"` | ✅ | Line 157 |
| Requires LinkedIn URL when not manual_assist | ✅ | Line 153: `"linkedin.com" in url` |
| `manual_assist=False` → Easy Apply only | ✅ | Default, filter block |

### 6. `agents/application_runner.py`

| Check | Pass? | Evidence |
|-------|-------|----------|
| `easy_apply_only=True` by default | ✅ | `RunConfig` |
| External ATS → skip (not submitted) | ✅ | Returns `skipped` with message |
| External ATS fill → `manual_assist_ready` (never submit) | ✅ | `fill_external_ats_form` returns status, no submit click |
| Strict gate: fit, ATS, apply_mode before LinkedIn | ✅ | `_policy_blocked()` |

### 7. `ui/streamlit_app.py`

| Check | Pass? | Evidence |
|-------|-------|----------|
| Export only `apply_mode == "auto_easy_apply"` | ✅ | Lines 519-521 |
| Export includes `easy_apply_confirmed`, `apply_mode` | ✅ | Lines 524-531 |
| Blocker summary shows apply_mode, fit, ATS | ✅ | Lines 459-466 |

### 8. `application_tracker.py`

| Check | Pass? | Evidence |
|-------|-------|----------|
| Tracks `manual_assist_ready` status | ✅ | status_map |
| Tracks `easy_apply_confirmed`, `apply_mode` | ✅ | TRACKER_COLUMNS |

---

## Quick Smoke Test

Before live use, run:

1. **Find jobs** (LinkedIn MCP, Easy Apply filter on)
2. **Select jobs** → check blocker summary for `apply_mode`
3. **Export** → only `auto_easy_apply` jobs in JSON
4. **Dry run** → `apply_to_jobs(jobs_json, dry_run=True)`
5. **Verify** → no external ATS submitted

---

## Summary

| Aspect | Pass |
|--------|------|
| Easy Apply only for auto-submit | ✅ |
| Confirmed vs filter-used separated | ✅ |
| External ATS = manual-assist | ✅ |
| Architecture | ✅ |
| Prototype completeness | ✅ |
| **Production readiness** | ❌ (login risk, external ATS fragility, dry-run recommended) |
