# Phase 4: Scale, identity, and operator polish

**Goal:** Move from “multi-user capable API + workers” to deployments that are easier to run at team scale, audit, and observe end-to-end.

**Prerequisite:** [Phase 3](PHASE_3_PLAN.md) baseline complete ✅ (auth, Postgres tracker, Celery graph, S3/metrics hooks).

---

## Phase 4.1 — Enterprise identity

| Milestone | Deliverable |
|-----------|-------------|
| 4.1.1 | Generic OIDC / JWKS — `JWT_JWKS_URL` or `JWT_ISSUER` discovery, optional `JWT_AUDIENCE` (`app/auth.py`) ✅ |
| 4.1.2 | Optional **organization / workspace** id — column `workspace_id`, `JobRequest.workspace_id`, JWT `workspace_id`/`org_id`, header `X-Workspace-Id`, `?workspace_id=` on list/insights/follow-ups ✅ |
| 4.1.3 | Service-to-service auth — `M2M_API_KEY` + `X-M2M-API-Key` (configurable header), `M2M_USER_ID`, `M2M_SERVICE_ROLES`, `M2M_API_KEY_IS_ADMIN` ✅ |

Streamlit today is single-session oriented; Phase 4 clarifies a **hosted multi-user UI** story or documents “API-first + your own frontend.”

---

## Phase 4.2 — Durable orchestration

| Milestone | Deliverable |
|-----------|-------------|
| 4.2.1 | **DB-backed idempotency** — `IDEMPOTENCY_USE_DB=1`, table `job_idempotency`, claim-before-enqueue (`services/idempotency_db.py`); Alembic `tracker_0005` ✅ |
| 4.2.2 | Optional **DB or object-store snapshots** for LangGraph/task state — `TASK_STATE_BACKEND=db|s3` in `services/task_state_store.py` ✅ |
| 4.2.3 | **`GET /api/admin/celery/inspect`** — Celery inspect snapshot + ops notes in [WORKER_ORCHESTRATION.md](WORKER_ORCHESTRATION.md#stuck-tasks--worker-visibility-phase-423) ✅ |

---

## Phase 4.3 — Metrics and alerting (closed loop)

| Milestone | Deliverable |
|-----------|-------------|
| 4.3.1 | **Celery → Prometheus** — API `/metrics` mirrors Redis `ccp:metrics:celery` as Gauges when `PROMETHEUS_METRICS=1` and (`CELERY_METRICS_REDIS=1` or `PROMETHEUS_CELERY_REDIS=1`); Pushgateway / multiprocess still optional for other cases ✅ |
| 4.3.2 | Starter alert rules — [prometheus/alert_rules.example.yml](prometheus/alert_rules.example.yml) + PromQL in [OBSERVABILITY.md](OBSERVABILITY.md#alerting) ✅ |
| 4.3.3 | **`scripts/metrics_webhook_alert.py`** + `services/metrics_alert_webhook.py` — POST when Redis counters cross `METRICS_ALERT_*_MIN` ✅ |

Today: Redis hash + `GET /api/admin/metrics/summary` and API `GET /metrics` (HTTP only). See [OBSERVABILITY.md](OBSERVABILITY.md).

---

## Phase 4.4 — Data lifecycle and compliance

| Milestone | Deliverable |
|-----------|-------------|
| 4.4.1 | **Retention defaults** — [DATA_RETENTION.md](DATA_RETENTION.md) (audit, task_state, idempotency, Redis metrics, S3 pointer) ✅ |
| 4.4.2 | **Admin export/delete** — `GET /api/admin/applications/export`, `DELETE /api/admin/applications/by-user` (+ idempotency rows when DB mode) ✅ |
| 4.4.3 | S3 lifecycle examples (CLI JSON + Terraform sketch) in [OBJECT_STORAGE.md](OBJECT_STORAGE.md#example-expire-old-artifact-objects-aws-s3) ✅ |

---

## Phase 4.5 — Apply-path hardening (optional)

| Milestone | Deliverable |
|-----------|-------------|
| 4.5.1 | Login / checkpoint **recovery playbooks** — [APPLY_RECOVERY_PLAYBOOKS.md](APPLY_RECOVERY_PLAYBOOKS.md); optional Redis counters `APPLY_RUNNER_METRICS_REDIS` + `apply_runner` on admin metrics summary ✅ |
| 4.5.2 | **Pipeline `run_id`** = Celery task id — injected in enqueue payload, `artifacts_manifest`, audit (`job_enqueued`, `celery_task_*`), `POST /api/jobs` + `GET /api/jobs/{id}` responses ✅ |

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
- [PHASE_5_PLAN.md](PHASE_5_PLAN.md) — deployment & ops  
- [DEPLOY.md](DEPLOY.md) — runbook  
- [WORKER_ORCHESTRATION.md](WORKER_ORCHESTRATION.md) — Celery, idempotency, task state  
- [OBSERVABILITY.md](OBSERVABILITY.md) — logs, Redis metrics, Prometheus HTTP  
- [DATA_RETENTION.md](DATA_RETENTION.md) — artifact paths, TTLs, operator cleanup  
- `scripts/metrics_webhook_alert.py` — optional Redis counter alerts (4.3.3)  
