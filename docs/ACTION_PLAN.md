# Career Co-Pilot Pro — Top 10 Priority Action Plan
**Based on:** Code audit (2026-03-26) + implementation review  
**Combined scores:** 7.4 / 10 supervised readiness · 4.8 / 10 broad autonomous readiness  
**Goal:** Close the gap to 8.5+ / 10 polished commercial product  

The next leap is not more features. It is simplification and packaging.  
Everything below is ordered by impact-to-effort ratio — highest leverage first.

---

## Fix 1 — Redesign the primary UX around one guided path (Impact: Critical)

**Current problem:**  
The Streamlit app opens to 6 tabs: Single Job, Batch URL Processor, AI Job Finder, Live ATS Optimizer, My Applications, ATS / API. A new user has no idea where to start. There is no narrative. The UI presents options, not a journey.

**Fix:**  
Replace the 6-tab structure with a single guided flow of named stages. The tab bar becomes a progress indicator, not a menu.

```
Stage 1: Setup        (profile complete? resume uploaded? LinkedIn ready?)
Stage 2: Discover     (paste URL · batch import · AI job search)
Stage 3: Score        (fit score · ATS gap · truth ceiling)
Stage 4: Prepare      (tailored resume · cover letter · answer preview)
Stage 5: Review       (decision checklist · safe_to_submit gate · manual confirm)
Stage 6: Apply        (assisted submit · manual assist hand-off · shadow/dry run)
Stage 7: Track        (tracker · follow-ups · insights)
```

Every feature already exists. This is a reorganization, not a rebuild.  
The current 6 tabs map to stages 2–7 almost exactly — they just need to be reframed as a flow.

**Files to change:** `ui/streamlit_app.py` — restructure tab labels and entry points  
**Effort:** Medium (2–3 days) · **Impact:** Transforms first impression completely

---

## Fix 2 — Split candidate UX from operator cockpit (Impact: Critical)

**Current problem:**  
`ui/streamlit_app.py` is 2,407 lines serving two completely different audiences in one file:
- **Candidate user:** wants to apply to a job cleanly
- **Operator / developer:** wants to debug form detection, probe ATS platforms, run batch jobs, inspect decisions, test API endpoints

These two audiences have incompatible UX needs. Mixing them makes both experiences worse.

**Fix:**  
```
ui/candidate_app.py    — guided 7-stage flow (Fix 1 above); this is the product
ui/operator_app.py     — current app.py essentially as-is; this is the cockpit
```

Run both from `run_streamlit.py` with an env var:
```python
APP_MODE=candidate  # default for end users
APP_MODE=operator   # for dev / pilot ops
```

**Files to change:** Extract `ui/streamlit_app.py` into two files  
**Effort:** High (3–5 days) · **Impact:** Biggest single UX improvement possible

---

## Fix 3 — Move credentials out of the main sidebar (Impact: High)

**Current problem:**  
`ui/streamlit_app.py` lines 382–440 put OpenAI API key, Apify API key, candidate name, resume upload, and a "Save credentials to .env" button all in the primary sidebar — visible on every screen, every session. This:
- Exposes internal API key management to the user-facing surface
- Signals "developer tool" immediately to any non-technical user
- Is a security anti-pattern for any multi-user deployment (keys written to a shared .env file)

**Fix:**  
Create a one-time Setup screen (`ui/pages/setup.py` in multi-page Streamlit, or a `st.session_state.setup_complete` gate):
- First run: guided setup (profile JSON, API keys via env vars, LinkedIn creds)
- Subsequent runs: sidebar shows only candidate name and resume selector (non-sensitive)
- Never write API keys to .env from the UI in production mode; use env vars or a secrets manager

**Files to change:** `ui/streamlit_app.py` sidebar section (lines 382–457)  
**Effort:** Low-Medium (1–2 days) · **Impact:** Immediately feels more like a product

---

## Fix 4 — Remove ATS / API tab from customer-facing nav (Impact: High)

**Current problem:**  
Tab 6 ("ATS / API") contains:
- Raw API endpoint calls
- Form probe / live form analysis
- Platform metadata lookups
- ATS registry inspection
- Recruiter follow-up generator via direct POST

This is excellent for internal validation and development. It is disqualifying in a customer-facing product. Any investor, recruiter, or non-technical user who sees it immediately reads the product as "developer tool, not finished."

**Fix:**  
Move the ATS / API tab behind an operator mode flag:
```python
if os.getenv("APP_MODE", "candidate") == "operator":
    # show ATS / API tab
```
Or move it entirely into `ui/operator_app.py` (Fix 2).  
The Recruiter Follow-up generator from this tab can be promoted into the Track stage of the candidate flow — that is genuinely user-facing.

**Files to change:** `ui/streamlit_app.py` tab6 block  
**Effort:** Low (half a day) · **Impact:** Immediately cleaner product impression

---

## Fix 5 — Add onboarding state / setup checklist (Impact: High)

**Current problem:**  
A new user opening the app sees a full cockpit with no guidance. There is no "you're not ready yet" signal, no profile completion indicator, no clear starting point. The app assumes the user already knows what they are doing.

**Fix:**  
Add a setup gate that runs on first load and whenever setup is incomplete:

```python
def setup_complete(profile: dict) -> tuple[bool, list[str]]:
    missing = []
    if not profile.get("full_name"): missing.append("Name")
    if not profile.get("email"): missing.append("Email")
    if not profile.get("phone"): missing.append("Phone")
    if not profile.get("location"): missing.append("Location")
    if not os.getenv("OPENAI_API_KEY"): missing.append("OpenAI API Key")
    return len(missing) == 0, missing
```

Show a setup checklist card at the top of Stage 1 (Setup) until all items are green. Once complete, the checklist collapses and the flow is unlocked. This is the single highest-signal "this is a real product" UX pattern.

**Files to change:** `ui/streamlit_app.py` or new `ui/candidate_app.py`  
**Effort:** Low (1 day) · **Impact:** Immediately feels like onboarded software, not a script

---

## Fix 6 — Write DEPLOY.md (Impact: Medium-High)

**Current problem:**  
The repo has no deployment guide. To run this in production you need to know: which env vars to set, whether Redis is required (it is for autonomy rollback gates), how to wire S3/GCS for artifact storage, how to run Celery workers, what Prometheus scrape endpoint to configure, and what the Alembic migration command is. None of this is documented. A new operator or technical pilot user cannot self-serve.

**Fix:**  
Create `DEPLOY.md` with:
```
1. Prerequisites (Python 3.11+, Redis optional but recommended, PostgreSQL or SQLite)
2. Environment variable reference table (required vs optional, what breaks without each)
3. Database setup: alembic upgrade head
4. Running the API: uvicorn app.main:app
5. Running workers: celery -A app.tasks worker
6. Running the UI: streamlit run ui/streamlit_app.py (or candidate_app.py)
7. Prometheus scrape config snippet
8. Redis setup for autonomy rollback gates (REDIS_METRICS_URL)
9. Object storage wiring (OBJECT_STORAGE_BACKEND, S3_BUCKET, etc.)
10. LinkedIn session setup for MCP apply
```

**Files to change:** New `DEPLOY.md`  
**Effort:** Low (1 day) · **Impact:** Unblocks self-service pilots and technical evaluators

---

## Fix 7 — Translate the policy model into user-legible trust signals (Impact: Medium)

**Current problem:**  
The policy model is the strongest differentiator in the repo. `truth_safe`, `submit_safe`, `safe_to_submit`, the three autonomy gates, the answer state table — all of this is genuinely excellent. But it is implemented better than it is presented. A user in the decision preview screen sees raw field names and state codes, not a clear story about "here is why we are confident / not confident in this application."

**Fix:**  
Replace the raw state table in the decision preview with a plain-language trust card:

```
Application Readiness
  Resume fit score:        87 / 100
  Truth-safe ceiling:      91 / 100 (we can honestly claim 91)
  Missing fields:          Work authorization (needs your review)
  Submit recommendation:   Ready for assisted submit

  Why we are confident:    All screening answers are truth-safe.
                           No unsupported requirements detected.
  Why you should review:   Work authorization field is unset in profile.
```

The data is already there in `build_application_decision()`. This is a rendering / copy change, not a logic change.

**Files to change:** Decision preview section in `ui/streamlit_app.py` (the `_decision_answer_rows` display block)  
**Effort:** Low-Medium (1 day) · **Impact:** Makes your best feature immediately legible to non-technical users

---

## Fix 8 — Replace .env sidebar write with a proper secrets model (Impact: Medium)

**Current problem:**  
Lines 438–440 of `ui/streamlit_app.py` save API keys to a `.env` file on disk from a UI button. This is:
- Fine for a single-user local tool
- A credential management anti-pattern for any shared or deployed instance
- A security concern if the repo or server directory is ever shared or exposed

**Fix:**  
For local/self-hosted: keep the current behavior but gate it behind `APP_MODE=local` or `ALLOW_ENV_WRITE=1`.  
For deployed/multi-user: use Streamlit secrets (`~/.streamlit/secrets.toml`) or env vars only — never write from the UI.  
Add a startup check that warns clearly if `API_KEY` is unset in a non-local mode.

**Files to change:** `ui/streamlit_app.py` `_save_creds()` function + `services/startup_checks.py`  
**Effort:** Low (half a day) · **Impact:** Required for any multi-user or hosted deployment

---

## Fix 9 — Fix LinkedIn MCP session (live apply blocker) (Impact: Medium)

**Current problem:**  
The career copilot MCP `apply_to_jobs` and `search_jobs` tools return `login_challenge`. This means Phase 3 narrow live submit is entirely blocked. All 23 tracker rows are `manual_assist` or `skip` — no live submit has ever succeeded through the MCP path.

**Fix (one-time, ~5 minutes):**  
1. Confirm the career copilot MCP is running (check Claude Desktop config)  
2. Open `https://www.linkedin.com` in a browser  
3. Complete any verification challenge (SMS code, email code, captcha)  
4. Session cookie saves to the career copilot session store  
5. Call `confirm_easy_apply` — should return `status: ok` instead of `login_challenge`  
6. Phase 3 apply is now unblocked  

**Files to change:** None — this is an auth state, not a code issue  
**Effort:** Trivial (5 minutes) · **Impact:** Unblocks the entire live apply pipeline

---

## Fix 10 — Add a Playwright test for the LinkedIn browser automation path (Impact: Medium)

**Current problem:**  
The LinkedIn automation path (`services/linkedin_browser_automation.py`, `services/linkedin_easy_apply.py`) is the highest-risk code in the repo — it directly interacts with a third-party platform on behalf of the user, and a bug here could result in accidental submissions or auth lockouts. Yet it has zero automated test coverage.

**Fix:**  
Add a Playwright test using a LinkedIn test account (or a mock/stub) that covers:
- Login flow → session capture
- Easy Apply modal detection
- Field fill attempt (dry run)
- Checkpoint / challenge detection → abort with `login_challenge` reason
- Successful submit path (against a test job or sandbox)

This does not need to run in CI against real LinkedIn. A stub server or recorded response is sufficient for regression prevention.

**Files to change:** New `tests/test_linkedin_browser_automation.py`  
**Effort:** Medium (2–3 days) · **Impact:** Protects the highest-risk code path from regressions

---

## Summary Table

| # | Fix | Impact | Effort | Addresses Score Gap |
|---|---|---|---|---|
| 1 | Redesign primary UX around guided flow | Critical | Medium | UX 5.8 → 7.5 |
| 2 | Split candidate UX from operator cockpit | Critical | High | UX 5.8 → 8.0, Accessibility 5.9 → 7.5 |
| 3 | Move credentials out of main sidebar | High | Low-Med | Security 7.1 → 8.0, Accessibility 5.9 → 7.0 |
| 4 | Remove ATS / API tab from customer nav | High | Low | UX 5.8 → 7.0, Positioning 7.7 → 8.5 |
| 5 | Add onboarding state / setup checklist | High | Low | Accessibility 5.9 → 7.5 |
| 6 | Write DEPLOY.md | Med-High | Low | Reliability 7.8 → 8.5, Demo value |
| 7 | Translate policy model to user-legible trust signals | Medium | Low-Med | Positioning 7.7 → 8.5, Trust model |
| 8 | Replace .env sidebar write with secrets model | Medium | Low | Security 7.1 → 8.5 |
| 9 | Fix LinkedIn MCP session (one-time) | Medium | Trivial | Reliability 6.0 → 8.0 |
| 10 | Add Playwright test for LinkedIn browser path | Medium | Medium | Reliability 7.8 → 8.5 |

---

## Projected scores after top 5 fixes

| Category | Current | After fixes 1–5 |
|---|---|---|
| UX and product polish | 5.8 | 8.2 |
| End-user accessibility | 5.9 | 8.0 |
| Security and multi-user readiness | 7.1 | 8.2 |
| Commercial positioning readiness | 7.7 | 8.8 |
| Overall supervised readiness | 7.4 | 8.6 |

The backend, policy model, decision layer, observability, and test coverage do not need to change. Those are already at 8.5–9.5. Every remaining point is earned by making what already works easier to understand and use.

---

*Career Co-Pilot Pro · Phase 9 Action Plan · 2026-03-26*  
*Based on: combined code review (services/, agents/, app/, ui/, tests/, docs/) + implementation audit*
