# Phase 8: SLOs and Incident Workflow

**Goal:** Turn alerting into an operator-ready operating model by defining:
1) concrete **SLO targets** (what “good” looks like), and  
2) a repeatable **incident workflow** (detect → diagnose → mitigate → verify → document).

This phase does not require new infrastructure; it focuses on making the already-shipped metrics and runbooks easy to use under pressure.

---

## 8.1 — Define SLOs for apply operations (what to measure)

The SLOs below reference the Prometheus gauges we mirror from Redis:
`ccp_apply_runner_<stage>_seconds_{sum,count}` and counters:
`ccp_apply_runner_<event>`.

### 8.1.1 — Apply fill latency SLO

- **Definition:** average LinkedIn Easy Apply fill latency
  - `avg_fill_seconds = rate(ccp_apply_runner_linkedin_fill_total_seconds_sum[5m]) / clamp_min(rate(ccp_apply_runner_linkedin_fill_total_seconds_count[5m]), 1e-9)`
- **Target:** keep `avg_fill_seconds <= 120`
- **Error budget:** trigger an incident when breached for **15m** (align with Phase 7.4 alerts).

### 8.1.2 — DOM scan drift / mapping SLO (unmapped fields proxy)

- **Definition:** average unmapped-field count per run
  - `avg_unmapped = rate(ccp_apply_runner_linkedin_fill_unmapped_fields_sum[5m]) / clamp_min(rate(ccp_apply_runner_linkedin_fill_unmapped_fields_count[5m]), 1e-9)`
- **Target:** keep `avg_unmapped <= 6`
- **Error budget:** trigger when breached for **10m**.

### 8.1.3 — Playwright timeout SLO

- **Definition:** timeout occurrences
  - `timeouts_15m = increase(ccp_apply_runner_linkedin_fill_playwright_timeout_total[15m])`
- **Target:** `timeouts_15m < 2`
- **Error budget:** alert and treat as degradation when `timeouts_15m >= 3`.

### 8.1.4 — Policy / truth-gate blockage SLO

- **Definition:** share of live submit attempts blocked by the truth/safety policy
  - `blocked_share = rate(ccp_apply_runner_linkedin_live_submit_blocked_autonomy_total[5m]) / clamp_min(rate(ccp_apply_runner_linkedin_live_submit_attempt_total[5m]), 1e-9)`
- **Target:** `blocked_share <= 0.10`
- **Error budget:** incident when breached for **20m**.

---

## 8.2 — Incident workflow (operator runbook)

### 8.2.1 — Detect

Primary signals (Phase 7.4):
- `ApplyRunnerAvgFillLatencyHigh`
- `ApplyRunnerAvgDomScanHigh`
- `ApplyRunnerPlaywrightTimeoutSpike`
- `TruthGateBlockedShareHigh`
- `ApplyRunnerAvgUnmappedFieldsHigh`

### 8.2.2 — Diagnose (quick triage)

Use the Grafana dashboard we already ship (`contrib/grafana/dashboard-career-co-pilot-v0.json`):
- Compare avg timing panels for:
  - DOM scan, value resolution, and field fill.
- Check “operator note” panel for what’s Redis-only vs Prometheus-mirrored.

Optional: run the incident triage helper to compute likely-breached alert(s) from the current Redis counters:

```bash
# Ensure this points to the same Redis instance your workers use for apply-runner metrics
export REDIS_METRICS_URL=redis://localhost:6379/0

# Reads apply-runner metrics from Redis and prints SLO triage + likely alert(s)
python scripts/triage_apply_runner_slo.py
```

If you also want the script to estimate the 15m timeout threshold using Prometheus, set:

```bash
export PROMETHEUS_BASE_URL=http://localhost:9090
```

### 8.2.3 — Mitigate (choose lane)

Route to the relevant section in `docs/APPLY_RECOVERY_PLAYBOOKS.md`:
- Fill latency / DOM scan: Metrics-driven triage (7.4 section) → slow-stage lane.
- Playwright timeouts: Metrics-driven triage → switch to visible browser and re-auth/retry guidance.
- Unmapped fields: Metrics-driven triage → Lane 2 manual-assist and mapping expansion.
- Truth gate blocks: Metrics-driven triage → review gating / data quality.

### 8.2.4 — Verify

After mitigation, confirm these return to target bands:
- `avg_fill_seconds` back under `120`
- `avg_unmapped` back under `6`
- timeout occurrences under threshold
- blocked_share under target

Verification window: **10–30 minutes** depending on your batch cadence.

### 8.2.5 — Document (close the loop)

Record:
- what fired,
- what mitigated it,
- the before/after metric values (roughly),
- whether a config/threshold needs adjustment,
- whether dashboards/runbooks need an update.

Update `CHANGELOG.md` and link to any specific mitigation that changed thresholds or defaults.

---

## 8.3 — “Done” criteria

- The SLO targets are documented and mapped to Phase 7.4 alerts.
- Every mitigation lane used in practice has a corresponding doc section in `docs/APPLY_RECOVERY_PLAYBOOKS.md`.
- Operator can follow the workflow without asking engineering for missing context.

