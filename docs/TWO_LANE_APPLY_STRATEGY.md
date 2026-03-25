# Two-Lane Apply Strategy

**Workday & Greenhouse:** Always **manual_assist** (assisted autofill + human submit). They are **never** `safe_auto_apply` in v1 — see [EXTERNAL_ATS_MANUAL_ASSIST.md](EXTERNAL_ATS_MANUAL_ASSIST.md).

The pipeline uses two lanes to balance automation speed with application quality.
**Easy Apply only is enforced in code** (not just UI): `apply_to_jobs` and `run_application` reject external ATS by default.

## Lane 1 — Auto-apply (Easy Apply only)

**When:** Easy Apply + fit ≥ 85 + truthful match + no blocker

Auto-submit only for:
- **LinkedIn Easy Apply** jobs (fewer custom fields, faster submission)
- **High fit** (fit score ≥ 85, ATS score ≥ 100)
- **No visa blocker** (e.g. US citizen / clearance)
- **No unsupported JD skills** (no fake keyword stuffing)
- **Standard questions** (no unusual mandatory essays)

**Flow:**
1. Search with "Easy Apply only" (default ON in LinkedIn filters)
2. Select high-fit jobs
3. Export for auto-apply (only Easy Apply jobs included)
4. Run `scripts/apply_linkedin_jobs.py` to fill and submit

**Why Easy Apply only:**
- Faster submission
- Fewer custom fields
- Higher automation reliability
- Lower chance of broken flows
- Better volume for your 20-day goal

## Lane 2 — Manual-assist (external portals)

**When:** Non–Easy Apply, Workday, Greenhouse, Lever, or complex forms

Do **not** auto-submit. Instead:
- Save to review queue
- Generate tailored resume + cover letter
- Prepare humanized answers (via Application Profile)
- Apply manually

**Flow:**
1. Select jobs (Easy Apply filter OFF, or jobs from Apify)
2. Click "Generate Documents for Selected Jobs"
3. Download tailored resume + cover letter
4. Apply manually on the company’s careers site

**Why manual for external portals:**
- Different form layouts
- Login walls, CAPTCHA, email verification
- Custom questions, portfolio statements, essays
- Resume re-parsing issues
- Higher risk of wrong submissions

## Decision rule summary

| Condition | Action |
|-----------|--------|
| Easy Apply + fit ≥ 85 + truthful + no blocker | **Auto-apply** |
| Not Easy Apply but fit ≥ 85 | **Prepare package for manual apply** |
| Low fit (score < 85) | **Skip** |

This keeps applications focused on high-fit roles and avoids weak or risky submissions.

When automation hits LinkedIn verification or form issues, see [APPLY_RECOVERY_PLAYBOOKS.md](APPLY_RECOVERY_PLAYBOOKS.md).
