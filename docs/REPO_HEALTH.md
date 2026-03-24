# Repo health — career-co-pilot-pro

Single-page snapshot: **strong prototype**, **not production-ready** for unattended large-scale apply without the guardrails below.

| Dimension | Rating | Notes |
|-----------|--------|--------|
| Architecture | Good | Entrypoints, `services/`, `providers/`, UI, MCP/apply layers separated |
| Prototype completeness | Good | Real fit gate, ATS loop, tracker, answerer, Playwright runner |
| Operational safety | Medium | Policy gates exist; LinkedIn/UI still need human oversight |
| Production readiness | Low | Requires auth, DB tracker, deps, and process discipline |

---

## Green (in good shape)

- Modular layout: `run_streamlit.py`, `app/main.py`, `services/`, `providers/`, `agents/`, `ui/`, `mcp_servers/`.
- README and [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) state limits (internal ATS score ≠ employer guarantee).
- LinkedIn MCP provider and multi-provider job discovery.
- Fit gate, iterative ATS optimizer, Streamlit workflow wiring.
- Candidate profile, application answerer, [resume naming](services/resume_naming.py) (deterministic master PDF fallback), application tracker (CSV/SQLite/Postgres).
- MCP autofill server and Playwright-based apply runner with policy checks in [application_runner.py](agents/application_runner.py).

---

## Yellow (works but rough)

- Internal ATS target (e.g. 100) is a **model/tooling score**, not a promise about external ATS vendors.
- Two-lane strategy is documented; keep verifying **per-job** Easy Apply signals (`easy_apply_confirmed` vs search filters) in exports and MCP payloads.
- External ATS (Greenhouse/Lever/Workday) is **prototype** — prefer **manual_assist**; runner defaults to Easy Apply–only auto path.
- Tracker **defaults to CSV** in dev; **production/strict startup now requires `TRACKER_USE_DB=1`** ([startup_checks.py](services/startup_checks.py)).
- Candidate profile supports optional **`application_locations`** (target markets / remote) and **`mailing_address`** (structured street/city/state); answerer uses them for location and address questions ([profile_service.py](services/profile_service.py), [application_answerer.py](agents/application_answerer.py)).

---

## Red (blockers for “production”)

- **Auth**: JWT + API key are supported; **open demo-user** is only acceptable outside production — startup fails in `APP_ENV=production` without credentials.
- **API surface**: useful but not a full hardened public API product — rate limits, versioning, and WAF are operator-owned.
- **Workers**: Celery + Redis; treat broker/backend URLs and secrets as production infrastructure.
- **Packaging**: `setuptools` includes `services`, `providers`, `ui`, `mcp_servers`, etc. **MCP/Playwright** are optional: `pip install -e ".[apply]"`. **Production bundle**: `pip install -e ".[production]"`.
- **Easy Apply**: Auto-apply paths require **confirmed** Easy Apply on the job record and policy `auto_easy_apply`; otherwise **manual_assist** or **skip**.

---

## Recommended next moves (ordered)

1. **Production deploy**: `APP_ENV=production`, `TRACKER_USE_DB=1`, `DATABASE_URL`, `API_KEY` or `JWT_SECRET`, `pip install -e ".[production]"`.
2. **Strict backend policy**: Keep using [policy_service.py](services/policy_service.py) + runner `_policy_blocked`; do not bypass for LinkedIn auto-submit.
3. **Apply stack**: Install `.[apply]` wherever MCP or Playwright apply runs.
4. **Per-job Easy Apply**: Set `easy_apply_confirmed` from MCP/job source before exporting auto-apply jobs.
5. **Structured work location / address** (if needed): extend candidate profile beyond `current_location` — not implemented yet.

---

## Related docs

- [FIX_ROADMAP.md](FIX_ROADMAP.md) — pass/fail checklist vs code  
- [PHASE_3_PLAN.md](PHASE_3_PLAN.md) — multi-user / DB / artifacts roadmap  
- [SECRETS_AND_CONFIG.md](SECRETS_AND_CONFIG.md) — env and secrets  
