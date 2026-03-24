# CLI scripts

| Script | Purpose |
|--------|---------|
| `apply_linkedin_jobs.py` | Playwright LinkedIn apply from exported JSON (`--allow-answerer-submit` optional) |
| `follow_up_digest.py` | Print due follow-ups as plain text (cron / email paste) |
| `email_follow_up_digest.py` | Email due follow-ups via SMTP (`FOLLOW_UP_SMTP_*` / `FOLLOW_UP_EMAIL_*`; `--dry-run`) |
| `webhook_follow_up_digest.py` | POST due follow-ups to `FOLLOW_UP_WEBHOOK_URL` (Slack/Discord/raw; `--dry-run`) |
| `telegram_follow_up_digest.py` | Telegram `sendMessage` (`FOLLOW_UP_TELEGRAM_BOT_TOKEN`, `FOLLOW_UP_TELEGRAM_CHAT_ID`; `--dry-run`) |
| `regenerate_resume_pdf.py` | Build resume PDF from markdown |

Run from repository root, e.g.:

```bash
python scripts/apply_linkedin_jobs.py jobs.json --no-headless
python scripts/apply_linkedin_jobs.py jobs.json --allow-answerer-submit
PYTHONPATH=. python scripts/follow_up_digest.py --user-id streamlit-local
PYTHONPATH=. python scripts/email_follow_up_digest.py --dry-run
PYTHONPATH=. python scripts/webhook_follow_up_digest.py --dry-run
PYTHONPATH=. python scripts/telegram_follow_up_digest.py --dry-run
python scripts/regenerate_resume_pdf.py input.md out.pdf "Your Name"
```
