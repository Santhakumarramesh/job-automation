# CLI scripts

| Script | Purpose |
|--------|---------|
| `apply_linkedin_jobs.py` | Playwright LinkedIn apply from exported JSON (`--allow-answerer-submit` optional) |
| `follow_up_digest.py` | Print due follow-ups as plain text (cron / email paste) |
| `email_follow_up_digest.py` | Email due follow-ups via SMTP (`FOLLOW_UP_*` env; `--dry-run`) |
| `regenerate_resume_pdf.py` | Build resume PDF from markdown |

Run from repository root, e.g.:

```bash
python scripts/apply_linkedin_jobs.py jobs.json --no-headless
python scripts/apply_linkedin_jobs.py jobs.json --allow-answerer-submit
PYTHONPATH=. python scripts/follow_up_digest.py --user-id streamlit-local
PYTHONPATH=. python scripts/email_follow_up_digest.py --dry-run
python scripts/regenerate_resume_pdf.py input.md out.pdf "Your Name"
```
