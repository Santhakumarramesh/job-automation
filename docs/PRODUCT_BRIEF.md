# Career Co-Pilot Pro — Market-Ready Product Brief

> **One-line position:**
> "Career Co-Pilot Pro is a supervised candidate-ops platform that helps serious job seekers run a truthful, high-signal, faster application workflow — from job discovery to tailored documents to safe assisted submission."

---

## The Problem

Serious job seekers — especially in technical fields — face three compounding problems:

1. **Volume without signal.** Modern job boards surface hundreds of roles, but matching, tailoring, and tracking each one manually burns hours per application.
2. **Resume truthfulness vs. ATS optimization tension.** Candidates either keyword-stuff (and risk integrity) or apply as-is (and lose to ATS filters). There is no safe middle path in existing tools.
3. **Automation tools overclaim and under-deliver.** "Apply to 1,000 jobs" bots hallucinate answers, submit unreviewed applications, and erode candidate credibility. They are not trustworthy for high-value roles.

Career Co-Pilot Pro solves all three: it runs a disciplined, truth-safe application workflow — faster than manual, safer than bots.

---

## Target User

**Primary:** Technical professionals actively job-seeking — AI/ML engineers, data scientists, software engineers, and adjacent roles.

**Secondary:** International candidates on OPT/H1B who cannot afford inaccurate or unsupported application answers. High-stakes applicants who want quality over volume.

**What they share:** They are discerning. They will not use a tool that risks their reputation. They want speed AND integrity. They are willing to stay in the loop for high-risk steps.

---

## Core Workflows (What the Platform Does Today)

### 1. Truth Inventory
Upload a master resume. The platform builds a structured, machine-readable **truth inventory** — every verifiable skill, role, metric, and credential. Nothing can be submitted that is not grounded here.

### 2. Job Discovery & Fit Scoring
Connect job sources (LinkedIn, Apify, manual upload). The platform normalizes jobs, scores fit against the truth inventory, and classifies each job as `apply`, `manual_review`, or `skip` — no manual triage needed.

### 3. Internal ATS Alignment Scoring
For every job in the apply lane, the platform runs a truthful ATS optimization loop: rephrase, reorder, and emphasize existing facts to maximize keyword alignment — without inventing new skills, roles, or metrics. It returns an internal ATS score and a **truth-safe ceiling** (the maximum score achievable without lying).

### 4. Tailored Application Package
Generates a tailored resume, human-readable resume variant, cover letter, fit report, and ATS report — all grounded in the truth inventory.

### 5. Supervised Submission
- **For LinkedIn Easy Apply:** policy-gated pre-fill with optional supervised or shadow auto-submit.
- **For Workday / Greenhouse / Lever / external ATS:** assisted autofill only — the system prepares and pre-fills; the human reviews and submits.
- **For all flows:** screenshots, audit logs, and structured telemetry capture every action.

---

## The Three Phases (Autonomy Ladder)

| Phase | What It Does | Status |
|-------|-------------|--------|
| **Phase 1 — Supervised Platform** | Truth inventory → job fit → ATS scoring → tailored package → human submits | ✅ Production-ready |
| **Phase 2 — Shadow Autonomy** | System acts as if it would apply; logs "would-have-applied" runs without submitting; tunes thresholds | ✅ Implemented (`shadow_mode`) |
| **Phase 3 — Narrow Live Submit** | LinkedIn Easy Apply only, pilot-gated, with Redis failure-rate rollback and kill switch | ✅ Implemented (env-gated) |

**The honest claim:** Market-ready as a Phase 1 supervised product today. Phase 2 and 3 are implemented and available for operators who have completed pilot evidence requirements.

---

## What Makes This Different

### Truth-first architecture
Every answer, every resume line, every form fill is traced back to the master resume truth inventory. No hallucinated skills. No unsupported claims. The system blocks — not warns — when truth is missing.

### State machine as the product core
Every job has a machine-readable state: `skip`, `manual_review`, `manual_assist`, `safe_auto_apply`, `blocked`. Every answer has a state: `safe`, `review`, `missing`, `blocked`. These states drive the UI, the tracker, the audit log, and the submission gate — not ad hoc flags.

### Honest autonomy model
The platform is explicit about where it will and will not submit autonomously. This is not a weakness. It is the differentiator. Trust is the product.

### Production architecture
FastAPI + Celery + Redis + Postgres + S3 + Alembic. JWT/API-key auth. Grafana-ready metrics. Docker Compose deployment. This is not a demo. It can be deployed and operated.

---

## Differentiators vs. Competitors

| Dimension | Resume.io / Zety | Simplify / Autoapply bots | Career Co-Pilot Pro |
|-----------|-----------------|--------------------------|---------------------|
| Truth safety | None | None | **Core constraint** |
| ATS scoring | Basic | None / black box | **Truthful ceiling scoring** |
| Answer state machine | None | None | **`safe` / `review` / `missing` / `blocked`** |
| Autonomy model | N/A | Overclaims | **Phased, pilot-gated, documented** |
| External ATS | Manual | Broken | **Assisted autofill (manual_assist)** |
| Audit / transparency | None | None | **Screenshots, JSONL, tracker, Grafana** |
| Target user | Anyone | Anyone | **Serious technical candidates** |

---

## MVP Scope (What to Ship First)

1. **Streamlit UI** — master resume upload, truth inventory view, job queue, fit scores, ATS scores, package download.
2. **Supervised apply for LinkedIn Easy Apply** — pre-fill + screenshot + tracker row. Human clicks Submit.
3. **Manual-assist for Workday/Greenhouse** — fill preparation + report. Human pastes and submits.
4. **Tracker + insights dashboard** — applied / skipped / shadow rows with pipeline analytics.
5. **Follow-up digest** — scheduled reminders for follow-up emails.

---

## Pricing Direction (Suggested)

| Tier | Who | What | Price Signal |
|------|-----|------|-------------|
| **Free** | Individual candidates | 5 jobs/month, basic tailoring, no apply automation | $0 |
| **Pro** | Active job seekers | 50 jobs/month, full package, LinkedIn assisted apply | ~$29/month |
| **Expert** | High-stakes candidates (OPT, senior roles) | Unlimited, shadow + manual-assist all ATS, priority support | ~$79/month |
| **Team** | Bootcamps, recruiting firms, career coaches | Workspace + multi-user + API access + white-label | Custom |

---

## What to Build Next (Priority Order)

1. **Outcome tracking** — recruiter response rates, interview conversions, offer rates per job class. This is the strongest commercial proof point.
2. **Richer answer classification UI** — show candidates exactly which fields are `safe` vs `review` vs `missing` before they submit.
3. **OPT/H1B mode** — strict sponsorship answer policy, USCIS-safe phrasing rules, extra caution on work-auth fields.
4. **Chrome extension (light)** — let users trigger package generation from any job board, not just the platform.
5. **Cohort analytics for Phase 2** — shadow vs. actual apply alignment rates, threshold tuning dashboard.
6. **Multi-workspace RBAC** — for bootcamps and recruiting firms managing multiple candidates.

---

## The Positioning Statement

> **Do not present this as a bot. Present it as a candidate operating system.**

Career Co-Pilot Pro is the platform serious job seekers use to run a disciplined, high-signal, truth-safe application workflow — faster than manual, more trustworthy than any bot.

---

*Last updated: March 2026. See [AUTONOMY_MODEL.md](AUTONOMY_MODEL.md), [PRODUCT_SCOPE.md](PRODUCT_SCOPE.md), and [MARKET_PRODUCTION_ROADMAP.md](MARKET_PRODUCTION_ROADMAP.md) for technical details.*
