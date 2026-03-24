# Red / Yellow / Green Fix Roadmap

Reconciliation of the full pass/fail checklist with current implementation. Items marked **Fixed** have been implemented; remaining gaps are prioritized.

---

## Core repo health

| # | Item | Status | Notes |
|---|------|--------|-------|
| 1 | Repo structure | ✅ Pass | `run_streamlit.py` entrypoint, `app/` (FastAPI), `ui/`, `services/`, `providers/`, `agents/`, `mcp_servers/` |
| 2 | README honesty | ✅ Pass | Prototype wording, no guaranteed ATS/hiring claims |

---

## Job discovery layer

| # | Item | Status | Notes |
|---|------|--------|-------|
| 3 | LinkedIn MCP exists | ✅ Pass | `providers/linkedin_mcp_jobs.py` |
| 4 | Multi-provider support | ✅ Pass | Apify + LinkedIn MCP, registry selection |
| 5 | Easy Apply truthfulness | ✅ **Fixed** | `easy_apply_confirmed` vs `easy_apply_filter_used`; `easy_apply` only True when MCP confirms |

---

## Matching and fit logic

| # | Item | Status | Notes |
|---|------|--------|-------|
| 6 | Fit gate exists | ✅ Pass | UI graph, `check_fit_gate` |
| 7 | Truth-safe ATS | ✅ Pass | Designed into pipeline |
| 8 | Centralized apply policy | ✅ **Fixed** | `services/policy_service.py` → `decide_apply_mode()` |

---

## Application profile and answer system

| # | Item | Status | Notes |
|---|------|--------|-------|
| 9 | Candidate profile | ✅ Pass | `profile_service.py`, validation |
| 10 | Question answerer | ✅ Pass | `application_answerer.py` |
| 11 | Answer safety | ✅ **Fixed** | Sponsorship/why_role/why_company return "Please review manually" when missing |

---

## Resume and document handling

| # | Item | Status | Notes |
|---|------|--------|-------|
| 12 | Job-specific resume naming | ✅ Pass | `services/resume_naming.py` |
| 13 | Resume source deterministic | ✅ Pass | `MASTER_RESUME_PDF` / `DEFAULT_RESUME_PDF`, then `Master_Resumes` name hints + sorted paths (`pick_fallback_resume_pdf`) |

---

## UI and workflow enforcement

| # | Item | Status | Notes |
|---|------|--------|-------|
| 14 | Easy Apply only in UI | ✅ Pass | Export only `apply_mode == "auto_easy_apply"` |
| 15 | Easy Apply only in backend | ✅ **Fixed** | MCP filters; runner skips external ATS; external ATS never auto-submits |
| 16 | Logical credential gating | ✅ **Fixed** | Apify not required for LinkedIn MCP only; warning only |

---

## Auto-apply engine

| # | Item | Status | Notes |
|---|------|--------|-------|
| 17 | MCP autofill server | ✅ Pass | Real server, tools |
| 18 | LinkedIn apply runner | ✅ Pass | Playwright logic in `application_runner.py` |
| 19 | External ATS support | ✅ Pass | Greenhouse / Lever / Workday (prototype) |
| 20 | External ATS unattended-safe | 🔴 Fail | Too much variation; **manual-assist only** by design |
| 21 | Login challenge resilience | 🟡 Partial | Detects challenges; no robust recovery |

---

## Tracking and auditability

| # | Item | Status | Notes |
|---|------|--------|-------|
| 22 | Application tracking | ✅ Pass | Tracker in UI and services |
| 23 | Run audit | ✅ Pass | Results, screenshots, Q&A saved |
| 24 | Tracker richness | 🟡 Partial | fit_decision, ats_score, apply_mode in schema; persistence could be stronger |

---

## Red / Yellow / Green Priorities

### 🔴 Red — must fix before trusting live auto-apply

| Priority | Item | Action |
|----------|------|--------|
| R1 | External ATS unattended use | **Already mitigated:** External ATS returns `manual_assist_ready`, never submits. Document as intentional. |
| R2 | — | *(No other red blockers; core policy is enforced.)* |

### 🟡 Yellow — improve for robustness

| Priority | Item | Status |
|----------|------|--------|
| Y1 | Resume source fallback | ✅ Fixed: Master_Resumes only; prefer Master_Resume.pdf, else most recent |
| Y2 | Login challenge recovery | ✅ Fixed: Clearer error + docs section with manual-retry steps |
| Y3 | Tracker persistence | ✅ Fixed: `log_application_from_result(job_metadata=...)` from MCP |

### 🟢 Green — done or acceptable as-is

- Easy Apply truthfulness ✅
- Centralized policy ✅
- Backend Easy Apply only ✅
- Answer safety ✅
- Credential gating ✅
- Repo structure, README, providers, fit gate, profile, answerer, resume naming, UI export, MCP server, runner, tracking ✅

---

## Bottom-line verdict (updated)

| Aspect | Status |
|--------|--------|
| Architecture | ✅ Pass |
| Prototype usability | ✅ Pass |
| Policy enforcement | ✅ Pass (centralized, backend-strict) |
| Production-safe auto-apply | ⚠️ Partial (LinkedIn Easy Apply OK with dry-run; external ATS = manual-assist) |

**Verdict:** The repo is in good shape for a **LinkedIn Easy Apply–only** pipeline with dry-run first. External ATS remains manual-assist by design.
