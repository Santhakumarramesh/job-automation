# Phase 7: Quality Gates & Performance Telemetry

**Goal:** Make the supervised product easier to operate long-term and faster in practice by (1) strengthening CI type-safety beyond the v0 scope and (2) adding measurable, dashboarded performance telemetry for the browser fill / apply pipeline.

**North star:** when “filling feels slow” happens again, we should be able to answer *which step* is slow (LLM vs Playwright vs DOM scanning vs retries) and quickly correlate it with operator-visible symptoms.

---

## Phase 7.1 — Expand mypy coverage (beyond v0 scope)

| Milestone | Deliverable |
|-----------|-------------|
| 7.1.1 | Extend `mypy.ini` scope to cover additional stable surfaces (handlers, admin APIs, metrics helpers, and runner orchestration). |
| 7.1.2 | Update `contrib/github-actions-ci.yml` to run `mypy --config-file mypy.ini` with a failing gate for *new* type errors (no silently ignored regressions). |
| 7.1.3 | Keep “strict typing” incremental: prefer concrete annotations at module boundaries rather than deep internal refactors. |

---

## Phase 7.2 — Grafana dashboards beyond v0 samples

| Milestone | Deliverable |
|-----------|-------------|
| 7.2.1 | Tracker: add `safe_to_submit=true` weekly trends split by `job_state` (counts, applied counts, and applied rate). |
| 7.2.2 | Apply runner: add dashboards for apply-runner reliability and (if available) performance timings (fill duration buckets, timeout rate, and DOM drift indicators). |
| 7.2.3 | Keep operator ownership: dashboards should be runnable with the repo’s datasource variables (`${DS_POSTGRES}`, `${DS_PROMETHEUS}`) and work even when Redis-only metrics are present (show “Redis-only” in panel notes). |

---

## Phase 7.3 — Performance instrumentation for browser fill

| Milestone | Deliverable |
|-----------|-------------|
| 7.3.1 | Add step timing for LinkedIn Easy Apply fill path in `agents/application_runner.py`: `goto`, `wait_for_timeout`, `click easy apply`, `DOM scan`, `field fill`, `screenshot`, and `submit click` (when used). |
| 7.3.2 | Store timings in a metrics-friendly backend (preferred: Redis hash pattern consistent with `services/metrics_redis.py` / `services/apply_runner_metrics_redis.py`), and aggregate into admin JSON endpoints if needed. |
| 7.3.3 | Provide 1-2 Grafana panels that directly answer the operator question: “Where did the ~5 minute time go?” |
| 7.3.4 | Ensure instrumentation is gated or low-overhead (e.g. enabled via env var) so performance tuning doesn’t itself become the bottleneck. |

---

## Phase 7.4 — Alert rules & incident-friendly context

| Milestone | Deliverable |
|-----------|-------------|
| 7.4.1 | Update `prometheus/alert_rules.example.yml` with alerts for: elevated apply fill latency, increased Playwright timeouts, higher-than-normal DOM drift / unmapped field rate, and “truth gate blocked” spikes. |
| 7.4.2 | Add the relevant sections to `docs/OBSERVABILITY.md` (what to look at, what actions are safe, and which playbooks to follow). |
| 7.4.3 | Tie alerts to runbooks in `docs/APPLY_RECOVERY_PLAYBOOKS.md` so operators have immediate next steps. |

---

## Suggested execution order

1. **7.3** (performance instrumentation) so we can empirically reduce fill time again.
2. **7.1** (mypy expansion) so future changes stay safe.
3. **7.2** (Grafana deepening) to make the new telemetry visible.
4. **7.4** (alerts + runbooks) to reduce time-to-diagnosis.

---

## Out of scope (for Phase 7)

- Guaranteeing hands-off browser apply in production (still supervised by design).
- Large architectural rewrites of the Playwright runner or policy model.
- Full FP/FN ground-truth automation against employer ATS systems.

