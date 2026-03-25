# Release notes cadence (autonomy & public readiness)

**Purpose:** Keep **market-facing** claims ([PRODUCT_SCOPE.md](PRODUCT_SCOPE.md)), **autonomy controls** ([AUTONOMY_MODEL.md](AUTONOMY_MODEL.md)), and **shipped behavior** aligned whenever you cut a release or change live-submit posture.

---

## When to update

| Trigger | Minimum action |
|---------|----------------|
| **Git tag / named release** | Add a dated section to [CHANGELOG.md](../CHANGELOG.md); note autonomy-relevant env vars or defaults. |
| **Change to Phase 3 gates** (`services/autonomy_submit_gate.py`, rollback thresholds, pilot allowlists) | CHANGELOG entry under **Changed** or **Security**; re-run the [Public readiness](AUTONOMY_MODEL.md#public-readiness-narrow-autonomy) checklist for production. |
| **Shadow / pilot evidence** (new cohort, new thresholds) | Short note in CHANGELOG **Documentation** or project wiki; link tracker date range and counts referenced in AUTONOMY_MODEL § evidence. |
| **Quarterly (ops)** | Skim AUTONOMY_MODEL + PRODUCT_SCOPE vs current env; no doc change if unchanged. |

---

## What to record in [CHANGELOG.md](../CHANGELOG.md)

Use the **[Unreleased]** bucket until you tag; then rename to a version and date.

- **Security / ops:** kill switch (`AUTONOMY_LINKEDIN_LIVE_SUBMIT_DISABLED`), pilot-only mode, rollback tuning, auth changes affecting apply routes.
- **Changed:** behavior of `safe_auto_apply`, runner, or MCP/REST apply contracts when user-visible.
- **Documentation:** new or moved operator docs (link paths, not full prose).

Avoid duplicating [MCP_APPLICATION_DECISION_CONTRACT.md](MCP_APPLICATION_DECISION_CONTRACT.md); link it when the JSON contract version changes.

---

## Public readiness checklist (before widening live submit)

Use [AUTONOMY_MODEL.md — Public readiness (narrow autonomy)](AUTONOMY_MODEL.md#public-readiness-narrow-autonomy) as the authoritative checklist. Release notes should **reference** whether that checklist was satisfied for the release (yes / N/A for doc-only).

---

## Related

- [OBSERVABILITY.md](OBSERVABILITY.md) — metrics and Grafana sample for API/Celery.
- [PRODUCTION_READINESS_AUDIT_AND_ROADMAP.md](PRODUCTION_READINESS_AUDIT_AND_ROADMAP.md) — phased roadmap status.
