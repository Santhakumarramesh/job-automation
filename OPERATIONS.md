# Career Co-Pilot Pro — Operations Guide

Day-2 operations reference for running Career Co-Pilot Pro in production.

---

## Health Checks

```bash
# API health
curl http://localhost:8000/api/health

# Celery worker status
celery -A app.tasks inspect active

# Redis connectivity
redis-cli ping
```

---

## Kill Switches

To immediately block all live LinkedIn submits:

```bash
export AUTONOMY_LINKEDIN_LIVE_SUBMIT_DISABLED=1
# Restart the API / MCP server for the env var to take effect
```

To roll back to pilot-only mode:

```bash
export AUTONOMY_LINKEDIN_PILOT_SUBMIT_ONLY=1
export AUTONOMY_LINKEDIN_PILOT_USER_IDS=user-id-1,user-id-2
```

---

## Viewing Metrics

```bash
# Redis live submit counters
redis-cli -n 1 keys "linkedin_*"

# Prometheus scrape
curl http://localhost:8000/metrics | grep linkedin
```

---

## Database Backup

```bash
# SQLite
cp job_applications.db job_applications.db.bak

# PostgreSQL
pg_dump $DATABASE_URL > backup_$(date +%Y%m%d).sql
```

---

## Log Monitoring

All logs are structured JSON. Key fields: `correlation_id`, `level`, `message`, `timestamp`.

```bash
# Follow API logs
docker-compose logs -f api | jq .

# Filter errors only
docker-compose logs api | jq 'select(.level == "ERROR")'
```

---

## Common Issues

| Symptom | Cause | Fix |
|---|---|---|
| `login_challenge` from `apply_to_jobs` | LinkedIn session expired | Open LinkedIn in browser, complete verification |
| `ATS / API tab` missing in UI | `APP_MODE` is not `operator` | Set `APP_MODE=operator` |
| `profile missing required fields` | `candidate_profile.json` incomplete | Edit `config/candidate_profile.json` |
| Celery tasks queued but not running | Redis not running | Start Redis: `redis-server` |
| `safe_to_submit: false` on all jobs | `TRUTH_APPLY_HARD_GATE=1` + incomplete profile | Fix profile or set `TRUTH_APPLY_HARD_GATE=0` |
| Rollback gate blocking all submits | High failure rate in Redis metrics | Check `linkedin_live_submit_*` counters; reset or adjust threshold |

---

## Resetting Apply Metrics (Redis)

If rollback gates are blocking due to stale Redis counters:

```bash
redis-cli -n 1 DEL linkedin_live_submit_attempt_total
redis-cli -n 1 DEL linkedin_live_submit_success_total
```

---

*Career Co-Pilot Pro · OPERATIONS.md · Phase 10 · 2026-03-26*
