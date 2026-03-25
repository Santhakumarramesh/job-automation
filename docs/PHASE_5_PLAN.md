# Phase 5: Production deployment and operations

**Goal:** Run the API, Celery workers, and optional Streamlit in a hosted environment with a clear env matrix, health checks, and runbooks.

**Prerequisite:** [Phase 4](PHASE_4_PLAN.md) capabilities in place (identity, durable orchestration, metrics, retention).

---

## Phase 5.1 — Auth and startup alignment

| Milestone | Deliverable |
|-----------|-------------|
| 5.1.1 | OIDC / JWKS user JWTs — `JWT_JWKS_URL` or `JWT_ISSUER` discovery, optional `JWT_AUDIENCE` (`app/auth.py`) ✅ |
| 5.1.2 | Production startup treats JWT as configured when any of `JWT_SECRET`, `JWT_JWKS_URL`, or `JWT_ISSUER` is set; `M2M_API_KEY` counts toward “not demo-open” ✅ |

---

## Phase 5.2 — Deployment runbook

| Milestone | Deliverable |
|-----------|-------------|
| 5.2.1 | [DEPLOY.md](DEPLOY.md) — processes, probes, env checklist, migrations ✅ |
| 5.2.2 | Multi-replica notes: in-memory rate limits, Celery single graph, Redis broker/backend — [DEPLOY.md](DEPLOY.md#multi-replica-api-and-workers) ✅ |

---

## Phase 5.3 — Operator closure (ongoing)

| Milestone | Deliverable |
|-----------|-------------|
| 5.3.1 | Prometheus scrape + example alert rules documented — [OBSERVABILITY.md](OBSERVABILITY.md#operator-checklist-phase-53), [prometheus/alert_rules.example.yml](prometheus/alert_rules.example.yml); Grafana JSON dashboards remain operator-owned ✅ |
| 5.3.2 | Apply-path playbooks — [APPLY_RECOVERY_PLAYBOOKS.md](APPLY_RECOVERY_PLAYBOOKS.md) ✅ |

---

## Related docs

- [PHASE_6_PLAN.md](PHASE_6_PLAN.md) — Docker image + Compose (next packaging step)  
- [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) — honesty bar and enforced checks  
- [SECRETS_AND_CONFIG.md](SECRETS_AND_CONFIG.md) — `APP_ENV`, strict startup, Secrets Manager  
- [WORKER_ORCHESTRATION.md](WORKER_ORCHESTRATION.md) — workers, idempotency, task state  
- [MIGRATIONS.md](MIGRATIONS.md) — Alembic / tracker schema  
