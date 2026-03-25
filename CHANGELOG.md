# Changelog

Notable changes to **Career Co-Pilot Pro** are listed here. For autonomy and operator-facing expectations, also follow [docs/RELEASE_NOTES_CADENCE.md](docs/RELEASE_NOTES_CADENCE.md).

The format is inspired by [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed

- Set `asyncio_default_fixture_loop_scope = "function"` in `pyproject.toml` to remove pytest-asyncio default-scope deprecation noise and keep test behavior explicit.
- Added `CCP_FAST_PIPELINE=1` speed mode and `CCP_OPENAI_MODEL` model override for the Celery worker LLM pipeline (resume tailoring + cover letter; optionally skips humanization and project generation).
- Added `CCP_FAST_BROWSER_PIPELINE=1` + `CCP_BROWSER_WAIT_MULTIPLIER` to reduce Playwright runner wait delays (`agents/application_runner.py`) when you want faster fills.
- Expanded scoped `mypy.ini` coverage to infra utility services: `services/observability.py`, `services/secrets_loader.py`, `services/task_state_store.py`, `services/idempotency_keys.py`, `services/idempotency_db.py`.
- Added `tests/conftest.py` autouse fixture to isolate tracker DB/CSV per test (`tmp_path`), preventing row-count bleed between tests.
- Expanded scoped `mypy.ini` coverage to HTTP/metrics middleware: `services/prometheus_setup.py`, `services/apply_runner_metrics_redis.py`, `services/rate_limit.py`, `services/api_cors.py`.
- Expanded scoped `mypy.ini` coverage to policy/tracker/startup/profile services: `services/policy_service.py`, `services/tracker_db.py`, `services/application_tracker.py`, `services/startup_checks.py`, `services/profile_service.py`.
- Expanded scoped `mypy.ini` coverage to queue/context surfaces: `app/tasks.py`, `services/tracker_context.py`.

### Documentation

- CI sample now runs a deterministic tracker-isolation regression slice before full pytest.
- Added tracker Grafana starter: [contrib/grafana/dashboard-tracker-job-state-v0.json](contrib/grafana/dashboard-tracker-job-state-v0.json) for `job_state` counts / applied-rate / weekly trend.
- Added [docs/RELEASE_NOTES_CADENCE.md](docs/RELEASE_NOTES_CADENCE.md) describing when and how to update release notes alongside [AUTONOMY_MODEL.md](docs/AUTONOMY_MODEL.md) public readiness.

---

## Earlier history

Commits before this changelog: see repository history on your Git host.
