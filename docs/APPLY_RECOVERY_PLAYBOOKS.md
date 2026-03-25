# Apply-path recovery playbooks (Phase 4.5.1)

Operational steps when LinkedIn Easy Apply automation stalls: **login challenges**, **checkpoints**, **form mapping gaps**, and **rate limits**. For lane strategy (auto vs manual), see [TWO_LANE_APPLY_STRATEGY.md](TWO_LANE_APPLY_STRATEGY.md).

---

## 1. LinkedIn checkpoint / challenge after password

**Symptoms:** URL contains `checkpoint` or `challenge`; headless API returns `login_challenge` or “verification required”.

**Interactive script (`scripts/apply_linkedin_jobs.py` with `--no-headless`):**

1. Run with visible browser; when the script pauses at “Complete in browser, then press Enter…”, finish 2FA / CAPTCHA / email link in the same window.
2. Press Enter only after the feed or job page loads normally.
3. If loops repeat, clear cookies for `linkedin.com`, log in once manually in a normal profile, then retry.

**Headless API / MCP (`apply_to_jobs`, `confirm_easy_apply`):**

1. Open a regular browser on the same machine, sign in to LinkedIn, complete any security prompt.
2. Reduce automation frequency: increase `--rate-limit` / `rate_limit_seconds` (e.g. 120–180s between jobs).
3. Retry after 15–60 minutes if LinkedIn rate-limited the session.

**Metrics (optional):** set `APPLY_RUNNER_METRICS_REDIS=1` and inspect `GET /api/admin/metrics/summary` → `apply_runner.fields.linkedin_login_challenge_abort_total` (headless abort) or `linkedin_login_checkpoint_pause_total` (interactive pause). See [OBSERVABILITY.md](OBSERVABILITY.md).

---

## 2. “Failed – Login Challenge” or stuck on apply page

**Symptoms:** Tracker `submission_status` or run JSON shows login-related failure; screenshots under `application_runs/screenshots/`.

1. Confirm `LINKEDIN_EMAIL` / `LINKEDIN_PASSWORD` (or profile email) are correct and the account is not locked.
2. Run a **dry run** first: `scripts/apply_linkedin_jobs.py --dry-run` to validate forms without submit.
3. If Easy Apply button never appears, run `confirm_easy_apply` (API or MCP) on the job URL after manual login to refresh `easy_apply_confirmed`.

---

## 3. Form unmapped / manual assist

**Symptoms:** `manual_assist_ready`, `Failed – Form Unmapped`, or large `unmapped_fields` in run results.

1. Treat as **Lane 2**: open the job apply URL manually; use generated resume/cover from the pipeline.
2. For repeat offenders, capture HTML snippet or field labels and extend answerer mappings (see MCP `review-unmapped-fields` / project docs).
3. Do **not** disable `block_submit_on_answerer_review` in production batches unless you accept bad submissions.

---

## 4. Retry policy (when to re-run)

| Situation | Retry |
|-----------|--------|
| Transient network / timeout in Celery | Safe — Celery retries transient failures. |
| LinkedIn checkpoint right after login | After human completes challenge in same session. |
| Immediate second full batch after failures | **Wait** — backoff reduces lockouts. |
| Same job after `applied` | Avoid duplicate apply; check tracker row first. |

---

## 5. Related paths

- Setup: [docs/setup/job-apply-autofill-mcp.md](setup/job-apply-autofill-mcp.md)  
- Worker / jobs API: [WORKER_ORCHESTRATION.md](WORKER_ORCHESTRATION.md)  
- Retention: [DATA_RETENTION.md](DATA_RETENTION.md)  
