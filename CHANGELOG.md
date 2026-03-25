# Changelog

Notable changes to **Career Co-Pilot Pro** are listed here. For autonomy and operator-facing expectations, also follow [docs/RELEASE_NOTES_CADENCE.md](docs/RELEASE_NOTES_CADENCE.md).

The format is inspired by [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed

- Expanded scoped `mypy.ini` coverage to HTTP/metrics middleware: `services/prometheus_setup.py`, `services/apply_runner_metrics_redis.py`, `services/rate_limit.py`, `services/api_cors.py`.

### Documentation

- Added tracker Grafana starter: [contrib/grafana/dashboard-tracker-job-state-v0.json](contrib/grafana/dashboard-tracker-job-state-v0.json) for `job_state` counts / applied-rate / weekly trend.
- Added [docs/RELEASE_NOTES_CADENCE.md](docs/RELEASE_NOTES_CADENCE.md) describing when and how to update release notes alongside [AUTONOMY_MODEL.md](docs/AUTONOMY_MODEL.md) public readiness.

---

## Earlier history

Commits before this changelog: see repository history on your Git host.
