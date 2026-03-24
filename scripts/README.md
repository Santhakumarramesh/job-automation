# CLI scripts

| Script | Purpose |
|--------|---------|
| `apply_linkedin_jobs.py` | Playwright LinkedIn apply from exported JSON (`--allow-answerer-submit` optional) |
| `follow_up_digest.py` | Print due follow-ups as plain text (cron / email paste) |
| `email_follow_up_digest.py` | Email due follow-ups via SMTP (`FOLLOW_UP_SMTP_*` / `FOLLOW_UP_EMAIL_*`; `--dry-run`) |
| `webhook_follow_up_digest.py` | POST due follow-ups to `FOLLOW_UP_WEBHOOK_URL` (Slack/Discord/raw; `--dry-run`) |
| `telegram_follow_up_digest.py` | Telegram `sendMessage` (`FOLLOW_UP_TELEGRAM_BOT_TOKEN`, `FOLLOW_UP_TELEGRAM_CHAT_ID`; `--dry-run`) |
| `notify_follow_up_digest.py` | One-shot: webhook + Telegram + SMTP for due items (each if configured; `--dry-run`) |
| `print_insights.py` | Phase 13 tracker insights to stdout (`--json`, `--user-id`, `--no-audit`; no API) |
| `validate_profile.py` | Check `candidate_profile.json` for auto-apply readiness (`--strict`, `--json`; exit 0/1) |
| `check_startup.py` | Phase 3.5 env report: `app` \| `worker` \| `streamlit` (`--json`, `--fail-on-errors`) |
| `regenerate_resume_pdf.py` | Build resume PDF from markdown |

Run from repository root, e.g.:

```bash
python scripts/apply_linkedin_jobs.py jobs.json --no-headless
python scripts/apply_linkedin_jobs.py jobs.json --allow-answerer-submit
PYTHONPATH=. python scripts/follow_up_digest.py --user-id streamlit-local
PYTHONPATH=. python scripts/email_follow_up_digest.py --dry-run
PYTHONPATH=. python scripts/webhook_follow_up_digest.py --dry-run
PYTHONPATH=. python scripts/telegram_follow_up_digest.py --dry-run
PYTHONPATH=. python scripts/notify_follow_up_digest.py --dry-run
PYTHONPATH=. python scripts/print_insights.py --no-audit
PYTHONPATH=. python scripts/print_insights.py --json --no-audit | head -c 2000
PYTHONPATH=. python scripts/validate_profile.py --strict
PYTHONPATH=. python scripts/check_startup.py app
PYTHONPATH=. python scripts/check_startup.py worker --json
python scripts/regenerate_resume_pdf.py input.md out.pdf "Your Name"
```

**CI (GitHub Actions):** copy [`docs/setup/github-actions-ci.yml`](../docs/setup/github-actions-ci.yml) to `.github/workflows/ci.yml`. Pushing workflow files needs a GitHub PAT with the **workflow** scope.
