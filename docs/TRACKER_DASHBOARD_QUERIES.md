# Tracker analytics & example queries

Use these patterns for ops dashboards (Metabase, Grafana Postgres, `psql`, or BI exports).

## Admin HTTP API (no SQL)

Authenticated **admin** (JWT role / `API_KEY_IS_ADMIN`) can call:

```http
GET /api/admin/tracker-analytics/summary?max_rows=5000
GET /api/admin/tracker-analytics/summary?user_id=demo-user&workspace_id=my-ws
```

Response includes rollups such as **`by_job_state`**, **`by_status`**, **`by_applied_iso_week`**, cross-tabs on recruiter response, counts of rows with parseable `applied_at`, and **`shadow_metrics_v0`** (Phase 2: `shadow_positive_rate`, `shadow_to_applied_ratio`, `runner_issue_proxy_*`, `fp_fn_definitions_v0`). This matches `services/tracker_analytics.py` / `compute_shadow_insights` and is the lowest-friction rollup for a quick dashboard.

## Postgres: `job_state` column

After Alembic `tracker_0008`, the `applications.job_state` column is populated on new writes (denormalized from v0.1 `application_decision`). Prefer it for simple filters and indexes:

```sql
SELECT job_state, COUNT(*) AS n
FROM applications
GROUP BY 1
ORDER BY n DESC;
```

## Postgres: `application_decision` as JSONB

After Alembic **`tracker_0009`**, `applications.application_decision` is **JSONB** (nullable). Empty / legacy blank strings become `NULL` on upgrade.

### Filter by JSON fields

```sql
SELECT id, company, position,
       application_decision->>'job_state' AS job_state,
       (application_decision->>'safe_to_submit')::boolean AS safe_to_submit
FROM applications
WHERE application_decision->>'job_state' = 'safe_auto_apply'
LIMIT 100;
```

### Count by `job_state` inside JSON (if `job_state` column backfill missing)

```sql
SELECT application_decision->>'job_state' AS js, COUNT(*)
FROM applications
WHERE application_decision IS NOT NULL
GROUP BY 1
ORDER BY COUNT(*) DESC;
```

### Index (optional, heavy writes)

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_applications_decision_job_state
  ON applications ((application_decision->>'job_state'));
```

Create only if you routinely filter on JSON paths and accept write overhead.

## SQLite / CSV tracker

`application_decision` remains **TEXT** JSON. Use `json_extract` where available:

```sql
SELECT json_extract(application_decision, '$.job_state') AS job_state, COUNT(*)
FROM applications
WHERE application_decision IS NOT NULL AND application_decision != ''
GROUP BY 1;
```

## Metrics & audit JSONL

- Prometheus metrics: see `docs/OBSERVABILITY.md` and `services/prometheus_setup.py`.
- Apply / operator audit lines: `application_audit.jsonl` (`AUDIT_LOG_PATH`); aggregates via `services/application_insights.py` / insights APIs where exposed.
