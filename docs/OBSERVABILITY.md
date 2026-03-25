# Observability (Phase 3.6)

For **retention** of audit files, task-state JSON, idempotency stores, and related paths, see [DATA_RETENTION.md](DATA_RETENTION.md).

## Audit log (JSONL)

`services/observability.audit_log` appends to **`AUDIT_LOG_PATH`** (default `application_audit.jsonl`).

Celery lifecycle actions:

| Action | When |
|--------|------|
| `celery_task_started` | Task begins |
| `celery_task_finished` | Terminal outcome: `success`, `rejected`, or `error` |

Each `celery_task_finished` line includes `duration_sec`, `user_id`, `job_name`, and optional `failure_class` (`transient` / `permanent`).

## Structured logs

- **`LOG_JSON=1`** — JSON lines on the root logger (`services/observability.configure_structured_logging`).
- **`LOG_LEVEL`** — default `INFO`.
- Celery emits `career_co_pilot.celery` INFO lines with duration and outcome.

## Redis metrics (cross-worker)

Enable on **workers** with:

```bash
export CELERY_METRICS_REDIS=1
# optional: dedicated URL (else REDIS_BROKER is used)
# export REDIS_METRICS_URL=redis://localhost:6379/0
```

Counters live in Redis hash **`ccp:metrics:celery`**, including:

- `tasks_total`, `tasks_success_total`, `tasks_rejected_total`, `tasks_error_total`
- `tasks_error_transient`, `tasks_error_permanent` (when applicable)
- `task_duration_seconds_sum`, `task_duration_count` → average duration

**Admin API** (requires admin role):

`GET /api/admin/metrics/summary`

Returns JSON with `fields` from Redis or `enabled: false` if not configured.

**Apply runner (Phase 4.5.1):** when `APPLY_RUNNER_METRICS_REDIS=1`, Playwright paths increment counters in hash **`ccp:metrics:apply_runner`** (e.g. `linkedin_login_checkpoint_pause_total`, `linkedin_login_challenge_abort_total`). Non-empty hash is merged into the same summary as **`apply_runner`**. Playbooks: [APPLY_RECOVERY_PLAYBOOKS.md](APPLY_RECOVERY_PLAYBOOKS.md).

> **Prefork:** each worker process updates the same Redis keys — aggregation is correct. Intermediate **retries** do not increment terminal counters until the final outcome.

## Prometheus (API process)

```bash
pip install .[metrics]
export PROMETHEUS_METRICS=1
```

- **`GET /metrics`** — Prometheus text (Python + `ccp_http_requests_total` with grouped paths).
- **Celery counters (Phase 4.3):** when workers use `CELERY_METRICS_REDIS=1`, set the same on the API **or** `PROMETHEUS_CELERY_REDIS=1` so `/metrics` exposes **`ccp_celery_*`** Gauges mirrored from Redis hash `ccp:metrics:celery` on each scrape. Use `increase()` / `rate()` in PromQL (Gauges reflect cumulative Redis values). Set `PROMETHEUS_CELERY_REDIS=0` to omit the bridge while keeping `CELERY_METRICS_REDIS=1` for the admin JSON API.
- Restrict access at the load balancer / mesh in production.

## Operator checklist (Phase 5.3)

1. **Scrape** each API instance’s `GET /metrics` (or one SD target set) with `PROMETHEUS_METRICS=1`.
2. **Enable the Celery bridge** on the API when workers publish to Redis: `PROMETHEUS_CELERY_REDIS=1` or `CELERY_METRICS_REDIS=1` on the API (see above).
3. **Load** [prometheus/alert_rules.example.yml](prometheus/alert_rules.example.yml) into your ruler; tune windows to your scrape interval.
4. **Optional:** cron [scripts/metrics_webhook_alert.py](../scripts/metrics_webhook_alert.py) for Redis-threshold webhooks.

**Grafana (v0 samples):** import [`contrib/grafana/dashboard-career-co-pilot-v0.json`](../contrib/grafana/dashboard-career-co-pilot-v0.json) for Prometheus API/Celery metrics, and [`contrib/grafana/dashboard-tracker-job-state-v0.json`](../contrib/grafana/dashboard-tracker-job-state-v0.json) for Postgres tracker `job_state` outcomes (counts, applied-rate, weekly trend).

## Alerting

Not built-in. Point your stack at:

- JSONL audit file (e.g. ship to OpenSearch / CloudWatch Logs)
- Redis metrics (poll `GET /api/admin/metrics/summary` or read the hash from monitoring)
- Prometheus scrape of `/metrics`

Raise alerts on spikes in `tasks_error_*` or `tasks_rejected_total` / sustained latency via `avg_duration_seconds`.

**Starter rules (Phase 4.3.2):** copy [prometheus/alert_rules.example.yml](prometheus/alert_rules.example.yml) into your Prometheus `rule_files`, `PrometheusRule` CRD, or ruler. Helm / recording rules remain operator-owned.

**Phase 7.4 apply-runner alerts (optional):** the same starter rules file can also include alerts for:
- elevated LinkedIn Easy Apply fill latency (avg wall time from Prometheus: `ccp_apply_runner_linkedin_fill_*_seconds_*`)
- Playwright timeout spikes (from Redis → Prometheus: `ccp_apply_runner_linkedin_fill_playwright_timeout_total`)
- DOM drift / mapping gaps proxy via unmapped-field average (avg from `ccp_apply_runner_linkedin_fill_unmapped_fields_*`)
- truth/submission gate blocks share (from Prometheus counters: `ccp_apply_runner_linkedin_live_submit_blocked_autonomy_total` and `..._attempt_total`)

When these fire, start with the corresponding sections in [APPLY_RECOVERY_PLAYBOOKS.md](APPLY_RECOVERY_PLAYBOOKS.md).

**Optional webhook (Phase 4.3.3):** cron `scripts/metrics_webhook_alert.py` with `CELERY_METRICS_REDIS=1`, thresholds like `METRICS_ALERT_ERROR_TOTAL_MIN`, and `METRICS_ALERT_WEBHOOK_URL` — see `services/metrics_alert_webhook.py`.

**Example PromQL** (after Celery Redis bridge is enabled on `/metrics`; tune windows for your scrape interval):

```text
# Error share over 30m (Gauge mirrors — use increase)
  increase(ccp_celery_tasks_error_total[30m])
/ increase(ccp_celery_tasks_total[30m]) > 0.25

# Permanent failures picking up
increase(ccp_celery_tasks_error_permanent_total[1h]) > 3

# Avg duration from sum/count mirrors
  (ccp_celery_task_duration_seconds_sum - ccp_celery_task_duration_seconds_sum offset 1h)
/ (ccp_celery_task_duration_count - ccp_celery_task_duration_count offset 1h) > 120

 # LinkedIn Easy Apply: avg fill latency from apply-runner sum/count
  rate(ccp_apply_runner_linkedin_fill_total_seconds_sum[5m])
 / clamp_min(rate(ccp_apply_runner_linkedin_fill_total_seconds_count[5m]), 1e-9) > 240

 # LinkedIn Easy Apply: truth/submission gate blocked share
  rate(ccp_apply_runner_linkedin_live_submit_blocked_autonomy_total[5m])
 / clamp_min(rate(ccp_apply_runner_linkedin_live_submit_attempt_total[5m]), 1e-9) > 0.25
```
