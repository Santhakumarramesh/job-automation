# Target operating model (north star)

**Purpose:** Describe how Career Co-Pilot Pro should work **after recommended upgrades**, aligned with what exists today: MCP job search, fit gate, ATS optimization, candidate profile, answerer, resume naming, tracker, and apply runner.

**Related:** [VISION_ARCHITECTURE_MAP.md](VISION_ARCHITECTURE_MAP.md) (diagram + pillar → module table), [WORKFLOW_MODULE_MAP.md](WORKFLOW_MODULE_MAP.md) (phase → file map), [ARCHITECTURE.md](ARCHITECTURE.md) (current implementation layers).

---

## Goal

A **truthful high-fit job automation platform** that:

- Reads your **master resume** and builds a **truth inventory**
- Searches jobs via **LinkedIn MCP** and **other providers**
- Filters to **real fits** (fit gate + unsupported requirements)
- Optimizes resume toward a **truth-safe internal ATS target** (not fake 100s)
- Generates tailored documents and **humanized** answers
- **Auto-applies only** to **confirmed** LinkedIn Easy Apply jobs
- Routes everything else to **manual-assist** or **skip**
- **Tracks** actions, results, and **follow-up** opportunities

The system is not only a job applier: it is **qualification + execution + tracking + follow-up**.

---

## Phase 1 — Identity, truth, and profile foundation

1. **Master resume ingestion** — Extract skills, tools, frameworks, projects, education, work history, publications, certifications, links, location clues, experience claims → **truth inventory**.
2. **Candidate profile ingestion** — Structured profile: name, contact, links, location, relocation, work authorization, sponsorship answers, notice period, salary rules, short answers.
3. **Profile validation** — Before runs, validate completeness for: search-only vs manual-assist vs **live auto-apply** (strict gates for auto-apply).
4. **Truth inventory** — Allowed skills/claims, blocked claims, unsupported JD requirements → basis for all later decisions.

---

## Phase 2 — Job discovery

5. **Multi-source search** — LinkedIn MCP, Apify, future providers via registry.
6. **Search strategy** — From master resume: titles (e.g. AI/ML, Data Science), skills (Python, AWS, …), filters: location, remote/hybrid, date posted, experience, Easy Apply preference, recency.
7. **Easy Apply confirmation** — Two fields, never conflated:
   - `easy_apply_filter_used` — search filter only
   - `easy_apply_confirmed` — per-job verification (detail/page/button)
   - Only **confirmed** jobs enter the auto-apply lane.

---

## Phase 3 — Job normalization and ranking

8. **Normalize** — Unified schema: source, job id, title, company, location, description, URLs, posted date, salary if available, easy-apply flags, work mode, quality/recency metadata.
9. **Preliminary ranking** — Role relevance, skill/keyword overlap, location/work-auth fit, Easy Apply eligibility, recency (**pre-fit**, not final decision).

---

## Phase 4 — Truthful fit gate

10. **Fit analysis** — JD vs master resume: strong match without invention? Blockers?
11. **Checks** — Citizenship/clearance/visa, experience mismatch, unsupported core skills, title/location mismatch, salary realism if needed, truthful ATS potential.
12. **Decisions** — `apply` | `manual_review` | `reject` + numeric fit score.
13. **Unsupported requirements** — Explicit list: what can be highlighted vs must not be claimed.

---

## Phase 5 — ATS scoring and optimization

14. **Initial ATS** — Semantic + keyword + structure vs JD; missing keywords and weak sections.
15. **Internal target** — Aim for high internal score using **only truthful** content.
16. **Iterative optimizer** — Tailor → re-score → loop until target, max attempts, or **truth-safe ceiling**.
17. **Truth-safe cap** — e.g. “Max truthful ATS: 87” → do not force 100; **manual-assist** or **skip**.

---

## Phase 6 — Resume tailoring

18. **Tailored resume** — Reorder, prioritize relevant experience/projects, JD-aligned wording, true facts, ATS-friendly format.
19. **Resume naming** — `{Name}_{Position}_at_{Company}_Resume.pdf`.
20. **Cover letter** — Tailored, humanized, company-aware, truthful.
21. **Application package** — Resume path, cover path, ATS/fit scores, unsupported list, autofill values, expected answers, metadata → **execution input**.

---

## Phase 7 — Humanized question answering

22. **Question classification** — Sponsorship, auth, relocation, salary, years, why role/company, start date, notice, links, etc.
23. **Short-answer engine** — Truthful, readable, recruiter-friendly.
24. **Safe-answer** — If confidence low or data missing: `manual_review_required`, **no** auto-submit.
25. **Batch prep** — Field map, free-text answers, flags, unmapped placeholders for auto and manual-assist.

---

## Phase 8 — Central decision engine

26. **One policy service** — Single place: `auto_easy_apply` | `manual_assist` | `skip`.
27. **Auto Easy Apply** — Only if: LinkedIn + **Easy Apply confirmed** + fit apply + ATS ≥ threshold + no unsupported requirements + **profile validated** + no risky unanswered questions + optional dry-run passed.
28. **Centralized policy audit** — Log **why** each job landed in each lane (debuggable, trustworthy).

---

## Phase 9 — Auto-apply execution

29. **MCP control plane** — Tools: validate profile, score fit, confirm Easy Apply, prepare package, autofill values, dry-run apply, live apply, review unmapped fields, audit report.
30. **Dry-run first** — Open page, fill, upload, screenshot, **no submit**.
31. **Live apply** — Login → job page → confirm Easy Apply → modal → upload correct resume → fill → screenshot → submit → log.
32. **Strict enforcement** — Live submit **only** if Easy Apply **confirmed** and apply mode is `auto_easy_apply`; external ATS **never** auto-submitted in production v1.

---

## Phase 10 — Manual-assist lane

33. **Outputs** — Resume, cover letter, answers, autofill hints, job/fit/ATS summaries, next steps.
34. **External ATS helper** — Greenhouse/Lever/Workday: detect type, suggest prefills/answers, surface unmapped fields, **stop before** live submission unless explicitly manual-assist workflow.

---

## Phase 11 — Tracking and audit

35. **Structured tracking** — Source, ids, URLs, company, role, fit/ATS, apply mode, Easy Apply confirmed, paths, screenshots, Q/A audit, submission status, recruiter response, retry state, **user_id** (multi-user).
36. **Database + object storage** — Postgres (metadata), object store (artifacts) at scale.
37. **Run archive** — Every dry/live run: timestamp, screenshots, filled values, unmapped fields, errors, **policy reason**.

---

## Phase 12 — Follow-up layer

38. **Follow-up generator** — LinkedIn note, short email, check-in, company-aware templates.
39. **Timing** — Reminders (e.g. 3d, 7d post-apply), interview thank-you.
40. **Priority queue** — Higher fit/ATS/recency/company match → prioritized follow-up.

---

## Phase 13 — Learning loop

41. **Failure analysis** — Fit failures, ATS ceiling hits, unmapped fields, login challenges, manual-review volume.
42. **Profile improvement suggestions** — Missing fields, weak short answers, auth wording, links.
43. **Policy tuning** — Correlate fit/ATS thresholds and apply modes with outcomes over time.

---

## End-to-end chain (target)

1. Upload master resume  
2. Complete candidate profile  
3. Validate profile (strict for auto-apply)  
4. Build truth inventory  
5. Search (LinkedIn MCP / Apify / …)  
6. Normalize and rank  
7. Confirm Easy Apply where possible  
8. Run truthful fit gate  
9. Reject bad fits  
10. Internal ATS score vs JD  
11. Iterative truth-safe optimization  
12. Tailored resume  
13. Tailored cover letter  
14. Humanized answers + package  
15. **Central policy** → auto / manual-assist / skip  
16. If auto: optional dry-run → live MCP runner  
17. If manual-assist: package + answers for human submit  
18. Log all outcomes + run archive  
19. Follow-up templates + (future) reminders  
20. Analyze failures and suggest profile/policy improvements  

---

## One-line definition

**A truthful high-fit career copilot** using MCP job discovery, fit gating, ATS-oriented **truth-safe** optimization, tailored documents, humanized answering, **strict Easy Apply-only** auto-submission, full tracking, and follow-up support.
