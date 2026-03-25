# Product Scope & Guarantees

> See also:
> - [System Vision](SYSTEM_VISION.md) (start here for the full blueprint)
> - [Autonomy & Policy Model](AUTONOMY_MODEL.md)
> - [Market Production Roadmap](MARKET_PRODUCTION_ROADMAP.md)
> - [Market Production Audit Checklist](MARKET_PRODUCTION_AUDIT_CHECKLIST.md) (repo checklist + scores)
> - [External ATS — Workday & Greenhouse](EXTERNAL_ATS_MANUAL_ASSIST.md)

## Current status

- Default operating mode: **supervised + policy‑gated automation**.
- Auto‑submit is limited, experimental, and not the default path.

---

## What this product is

This project is a **production‑minded candidate‑ops platform with supervised, policy‑gated job application automation**.

At a high level, it helps a candidate:

- Turn a master resume and candidate profile into a **truth inventory**.
- Discover and normalize jobs from multiple sources.
- Score **job fit** and **internal ATS alignment**.
- Generate **tailored application packages** (resume, cover letter, reports).
- Automate **safe parts** of the apply flow under supervision.

It is built to be deployed as a real service (API + workers + tracker + monitoring), not just a demo script.

---

## What this product is not

To stay honest and safe, this project is **not**:

- A “fire‑and‑forget” job spam bot.
- A guarantee of employer ATS scores, interviews, or offers.
- A universal auto‑submitter for all external ATS platforms (Greenhouse, Lever, Workday, etc.).
- A system that guarantees “strictly error‑free” browser automation.

It is explicitly designed to require **supervision** for higher‑risk actions and to keep automation within clear policy boundaries.

---

## Supported operating modes

The system is designed around **levels of autonomy**, with supervised behavior as the default:

1. **Level 1 – Supervised, analysis only**
   - Build truth inventory and candidate profile.
   - Search and rank jobs.
   - Score fit and ATS alignment.
   - Generate tailored documents and reports.
   - No browser automation.

2. **Level 2 – Supervised + safe prefill (current default)**
   - All Level 1 capabilities.
   - Browser opens job pages and verifies identity (title/company/location).
   - Browser pre‑fills fields that are known to be **truth‑safe and submit‑safe**.
   - Human reviews and submits or discards.

3. **Level 3 – Narrow `safe_auto_apply` (advanced, limited)**
   - Only for **LinkedIn Easy Apply**, and only when strict conditions are met.
   - Auto‑submit is allowed for a narrow class of high‑confidence jobs.
   - External ATS flows remain in **manual_assist**.

The system is intentionally designed so that Level 1 and Level 2 are **fully usable products** on their own.

---

## In‑scope capabilities

The following are explicitly in scope:

- Building and maintaining a **truth inventory** from a master resume and structured candidate profile.
- Policy‑gated **job evaluation**:
  - Job fit scoring.
  - Internal ATS scoring with a transparent, internal metric.
  - Job state classification (e.g., `skip`, `manual_assist`, `safe_auto_apply`).
- Package generation:
  - Tailored, ATS‑aware resume.
  - Human‑readable resume variant.
  - Tailored cover letter.
  - Fit report and ATS report.
- Supervised automation:
  - Opening job pages.
  - Verifying job identity (title, company, location).
  - Pre‑filling **safe** fields.
  - Logging, screenshots, and audits.
- **Assisted autofill** for external ATS (Workday, Greenhouse, Lever, …) in **`manual_assist`** only — not full auto-submit; see [EXTERNAL_ATS_MANUAL_ASSIST.md](EXTERNAL_ATS_MANUAL_ASSIST.md).

---

## Out‑of‑scope capabilities (for now)

The following are **out of scope** and not promised:

- Fully autonomous auto‑apply across all external ATS platforms.
- Legal advice on visa/immigration, employment law, or contract terms.
- Compensation negotiation or personalized legal risk assessment.
- Guaranteed outcomes with real employer ATS systems.

Any future expansion beyond this scope will require explicit updates to this document and to the autonomy model.
