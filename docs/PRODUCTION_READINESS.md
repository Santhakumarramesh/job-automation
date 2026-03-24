# Production Readiness

## Current status: **Strong prototype, not production-ready**

| Aspect | Status | Notes |
|--------|--------|------|
| Architecture | ✅ Good | Modular UI, `services/`, FastAPI `app/`, agents |
| Prototype completeness | ✅ Good | Real MCP, fit gate, ATS, autofill engine |
| Reliability for live auto-apply | ⚠️ Medium | LinkedIn Easy Apply works; external ATS fragile |
| Production readiness | ❌ Not yet | See [FIX_ROADMAP.md](FIX_ROADMAP.md) and [PHASE_3_PLAN.md](PHASE_3_PLAN.md) |

## Hard backend rules (enforced in code)

Auto-apply **only** proceeds when all of these are met:

1. **Easy Apply only** — `apply_to_jobs` rejects non–Easy Apply unless `manual_assist=True`
2. **Fit decision = Apply** — When metadata provided, job must have `fit_decision=Apply`
3. **ATS ≥ threshold** — When metadata provided, `ats_score >= 85`
4. **No unsupported requirements** — When metadata provided, `unsupported_requirements` must be empty
5. **External ATS = manual-assist** — Greenhouse/Lever/Workday not auto-submitted; engine skips them by default

## Known gaps

1. **Easy Apply truthfulness** — `easy_apply_confirmed` (MCP) vs `easy_apply_filter_used` (search filter).
2. **External ATS autofill** — Workday/Greenhouse/Lever forms vary; heuristic fill is prototype-only. Use manual-assist.
3. **Login automation risk** — LinkedIn checkpoint/challenge pages can break the flow.
4. **Dry run first** — Recommended: run with `dry_run=True` before live submit.

## Before trusting for live applying

- Run at least one `dry_run=True` pass
- Confirm Easy Apply jobs only (from export)
- Monitor for LinkedIn verification prompts
- Treat external ATS as manual-assist only
