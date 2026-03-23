# Phase 2: Production Hardening

**Goal:** Move from strong prototype to deployable production system.

**Scope:** P0 remaining + P1 high-value items.

---

## Phase 2.1 — Database-backed persistence ✅

| Milestone | Deliverable |
|-----------|-------------|
| 2.1.1 | SQLite-backed tracker (zero-infra; migration path to Postgres) |
| 2.1.2 | Schema: applications |
| 2.1.3 | `application_tracker` reads/writes via DB when `TRACKER_USE_DB=1` |
| 2.1.4 | Backward compat: CSV → SQLite migration on first run |

## Phase 2.2 — Authentication ✅

| Milestone | Deliverable |
|-----------|-------------|
| 2.2.1 | API key auth (X-API-Key header) — set API_KEY env |
| 2.2.2 | Stub only when API_KEY not set (local dev) |
| 2.2.3 | Optional: JWT for session-based flows |

## Phase 2.3 — API hardening ✅

| Milestone | Deliverable |
|-----------|-------------|
| 2.3.1 | `/health` and `/ready` endpoints |
| 2.3.2 | `GET /api/jobs/{job_id}` status |
| 2.3.3 | JobRequest validation (max_length) |
| 2.3.4 | Request size limits, rate limiting (Phase 3) |

## Phase 2.4 — Observability (minimal)

| Milestone | Deliverable |
|-----------|-------------|
| 2.4.1 | Structured JSON logging |
| 2.4.2 | Request correlation ID |
| 2.4.3 | Audit log for apply actions |

---

## Execution order

1. **2.1** — Database (unblocks audit, multi-user readiness)
2. **2.2** — Auth (unblocks API protection)
3. **2.3** — API hardening (operational sanity)
4. **2.4** — Observability (debugging, compliance)

---

## Out of scope for Phase 2

- Full OAuth2 (Phase 3)
- Worker/LangGraph unification (Phase 3)
- Object storage for artifacts (Phase 3)
- Secret manager integration (Phase 3)
