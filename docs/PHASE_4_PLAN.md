# Phase 4: Scale, identity, and operator polish

**Goal:** Move from “multi-user capable API + workers” to deployments that are easier to run at team scale, audit, and observe end-to-end.

**Prerequisite:** [Phase 3](PHASE_3_PLAN.md) baseline complete ✅ (auth, Postgres tracker, Celery graph, S3/metrics hooks).

---

## Phase 4.1 — Enterprise identity

| Milestone | Deliverable |
|-----------|-------------|
| 4.1.1 | OAuth2 / OpenID Connect (Auth0, Clerk, Supabase, or generic OIDC) — deferred from Phase 3.1.1 |
| 4.1.2 | Optional **organization / workspace** id on tracker rows and job payloads (schema + API filters) |
| 4.1.3 | Service-to-service auth (m2m tokens or scoped API keys) for workers and automation |

Streamlit today is single-session oriented; Phase 4 clarifies a **hosted multi-user UI** story or documents “API-first + your own frontend.”

---

## Phase 4.2 — Durable orchestration

| Milestone | Deliverable |
|-----------|-------------|
| 4.2.1 | **DB-backed idempotency** — `IDEMPOTENCY_USE_DB=1`, table `job_idempotency`, claim-before-enqueue (`services/idempotency_db.py`); Alembic `tracker_0005` ✅ |
| 4.2.2 | Optional **DB or object-store snapshots** for LangGraph/task state (today: `services/task_state_store.py` on disk) |
| 4.2.3 | **`GET /api/admin/celery/inspect`** — Celery inspect snapshot + ops notes in [WORKER_ORCHESTRATION.md](WORKER_ORCHESTRATION.md#stuck-tasks--worker-visibility-phase-423) ✅ |

---

## Phase 4.3 — Metrics and alerting (closed loop)

| Milestone | Deliverable |
|-----------|-------------|
| 4.3.1 | **Celery → Prometheus** — API `/metrics` mirrors Redis `ccp:metrics:celery` as Gauges when `PROMETHEUS_METRICS=1` and (`CELERY_METRICS_REDIS=1` or `PROMETHEUS_CELERY_REDIS=1`); Pushgateway / multiprocess still optional for other cases ✅ |
| 4.3.2 | Starter alert rules / PromQL examples — see [OBSERVABILITY.md](OBSERVABILITY.md#alerting) (YAML in your repo / Helm still operator-owned) 📋 |
| 4.3.3 | Optional webhook notifier on threshold (Slack/HTTP) — thin wrapper over existing Redis metrics |

Today: Redis hash + `GET /api/admin/metrics/summary` and API `GET /metrics` (HTTP only). See [OBSERVABILITY.md](OBSERVABILITY.md).

---

## Phase 4.4 — Data lifecycle and compliance

| Milestone | Deliverable |
|-----------|-------------|
| 4.4.1 | **Retention defaults** — [DATA_RETENTION.md](DATA_RETENTION.md) (audit, task_state, idempotency, Redis metrics, S3 pointer) ✅ |
| 4.4.2 | PII export/delete hooks for tracker rows (per user) where regulations require it |
| 4.4.3 | S3 lifecycle templates in [OBJECT_STORAGE.md](OBJECT_STORAGE.md) (operator-owned today → codified examples) |

---

## Phase 4.5 — Apply-path hardening (optional)

| Milestone | Deliverable |
|-----------|-------------|
| 4.5.1 | Login / checkpoint **recovery playbooks** and optional retry signals in runner metrics |
| 4.5.2 | Stronger **tracker ↔ apply run** correlation (single `run_id` across MCP, Celery, and tracker audit) |

---

## Suggested execution order

1. **4.3** — Makes production ops measurable with minimal schema change.  
2. **4.2** — Unlocks horizontal API and durable replay.  
3. **4.1** — When you need SSO, not just JWT/API keys.  
4. **4.4** — As compliance or retention requirements appear.  
5. **4.5** — If live Easy Apply volume justifies investment.

---

## Out of scope (still)

Multi-tenant **billing**, white-label marketplaces, and **guaranteed** pass-through on third-party ATS vendors — same boundary as Phase 3.

---

## Related docs

- [PHASE_3_PLAN.md](PHASE_3_PLAN.md) — completed baseline  
- [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) — current honesty bar  
- [WORKER_ORCHESTRATION.md](WORKER_ORCHESTRATION.md) — Celery, idempotency, task state  
- [OBSERVABILITY.md](OBSERVABILITY.md) — logs, Redis metrics, Prometheus HTTP  
- [DATA_RETENTION.md](DATA_RETENTION.md) — artifact paths, TTLs, operator cleanup  
