# Production Readiness

## Current status: **Strong prototype, not production-ready**

| Aspect | Status | Notes |
|--------|--------|------|
| Architecture | ✅ Good | Thin entry, modular UI, services layer |
| Prototype completeness | ✅ Good | Real MCP, fit gate, ATS, autofill engine |
| Reliability for live auto-apply | ⚠️ Medium | LinkedIn Easy Apply works; external ATS fragile |
| Production readiness | ❌ Not yet | See gaps below |

## Hard backend rules (enforced in code)

Auto-apply **only** proceeds when all of these are met:

1. **Easy Apply only** — `apply_to_jobs` rejects non–Easy Apply unless `manual_assist=True`
2. **Fit decision = Apply** — When metadata provided, job must have `fit_decision=Apply`
3. **ATS ≥ threshold** — When metadata provided, `ats_score >= 85`
4. **No unsupported requirements** — When metadata provided, `unsupported_requirements` must be empty
5. **External ATS = manual-assist** — Greenhouse/Lever/Workday not auto-submitted; engine skips them by default

## Known gaps

1. **Easy Apply truthfulness** — `easy_apply` can reflect the search filter, not per-job confirmation. Use `easy_apply_confirmed` when MCP provides it.
2. **External ATS autofill** — Workday/Greenhouse/Lever forms vary; heuristic fill is prototype-only. Use manual-assist.
3. **Login automation risk** — LinkedIn checkpoint/challenge pages can break the flow. Code handles this; user may need to complete verification manually.
4. **Dry run first** — Recommended: run with `dry_run=True` before live submit.

## Before trusting for live applying

- Run at least one `dry_run=True` pass
- Confirm Easy Apply jobs only (from export)
- Monitor for LinkedIn verification prompts
- Treat external ATS as manual-assist only
