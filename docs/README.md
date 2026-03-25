# Documentation index

| Doc | What it is |
|-----|------------|
| [TARGET_OPERATING_MODEL.md](TARGET_OPERATING_MODEL.md) | North-star product workflow (phases 1–13 + end-to-end chain) |
| [VISION_ARCHITECTURE_MAP.md](VISION_ARCHITECTURE_MAP.md) | Combined vision, mermaid diagram, pillar → module ownership |
| [WORKFLOW_MODULE_MAP.md](WORKFLOW_MODULE_MAP.md) | Each capability → repo path + implementation status |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Technical layers, data flow, decision logic, module index |
| [PHASE_3_PLAN.md](PHASE_3_PLAN.md) | Multi-user / production roadmap (baseline) |
| [PHASE_4_PLAN.md](PHASE_4_PLAN.md) | Scale & identity: JWKS/OIDC, durable orchestration, metrics, compliance |
| [PHASE_5_PLAN.md](PHASE_5_PLAN.md) | Deployment runbooks, multi-replica notes, operator checklist |
| [PHASE_6_PLAN.md](PHASE_6_PLAN.md) | Docker image + Compose reference stack |
| [DEPLOY.md](DEPLOY.md) | Processes, env checklist, Docker, horizontal scaling |
| [MIGRATIONS.md](MIGRATIONS.md) | Alembic Postgres tracker migrations |
| [OBJECT_STORAGE.md](OBJECT_STORAGE.md) | Optional S3 artifact upload, presigned URLs, lifecycle examples |
| [WORKER_ORCHESTRATION.md](WORKER_ORCHESTRATION.md) | Celery + LangGraph, retries, idempotency, task snapshots |
| [SECRETS_AND_CONFIG.md](SECRETS_AND_CONFIG.md) | Production env, strict startup, AWS Secrets Manager |
| [OBSERVABILITY.md](OBSERVABILITY.md) | Audit log, Redis metrics, Prometheus |
| [prometheus/alert_rules.example.yml](prometheus/alert_rules.example.yml) | Starter Prometheus alert rules (`ccp_celery_*`, HTTP 5xx) |
| [DATA_RETENTION.md](DATA_RETENTION.md) | On-disk artifacts, TTLs, operator cleanup (Phase 4.4) |
| [FOLLOW_UPS.md](FOLLOW_UPS.md) | Tracker follow-up queue & API (Phase 12) |
| [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) | Prototype status and rules |
| [FIX_ROADMAP.md](FIX_ROADMAP.md) | Checklist reconciliation |
| [TWO_LANE_APPLY_STRATEGY.md](TWO_LANE_APPLY_STRATEGY.md) | Auto-apply vs manual-assist lanes |
| [setup/](setup/README.md) | LinkedIn MCP & Career Copilot MCP setup |
