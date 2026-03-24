# Follow-up queue (Phase 12)

Schedule recruiter follow-ups on **tracker** rows using three optional columns:

| Column | Meaning |
|--------|---------|
| `follow_up_at` | ISO 8601 UTC (or with offset) — when to act |
| `follow_up_status` | `pending` (default when scheduling), `snoozed`, `done`, `dismissed` |
| `follow_up_note` | Short reminder text |

**Closed** statuses (`done`, `dismissed`) are excluded from queues.

## Priority score (`follow_up_priority_score`)

Each queue row includes **0–100** `follow_up_priority_score` (higher = tackle first), from:

- **ATS** (35%) — from `ats_score`
- **Fit** (25%) — `fit_decision` (`apply` > `manual_review` > other)
- **Recency** (25%) — how recent `applied_at` is (decays over ~30 days)
- **Overdue** (15%) — how far `follow_up_at` is in the past (caps at ~one week late)

Default API sort is **by this score** (descending). Use `sort_by_priority=false` to preserve tracker order.

## API (authenticated)

- `GET /api/follow-ups?due_only=true&include_snoozed=true&limit=50&sort_by_priority=true` — your rows only (`demo-user` sees all, same as applications list).
- `GET /api/follow-ups/digest` — same scope, returns `{ count, items, text }` with a **plain-text** body for email/Slack (`text`).
- `PATCH /api/applications/{application_id}/follow-up` — body JSON with any of `follow_up_at`, `follow_up_status`, `follow_up_note` (tracker row **`id`**, not `job_id`).

## Admin

- `GET /api/admin/follow-ups`
- `GET /api/admin/follow-ups/digest` — digest across all users (admin only).
- `PATCH /api/admin/applications/{application_id}/follow-up` — no `user_id` check.

## CLI (local)

- `PYTHONPATH=. python scripts/follow_up_digest.py` — print due follow-ups to stdout (`--user-id` optional).
- `PYTHONPATH=. python scripts/email_follow_up_digest.py` — same digest via **SMTP** when `FOLLOW_UP_SMTP_HOST` and `FOLLOW_UP_EMAIL_TO` are set; `--dry-run` prints digest and whether SMTP env is complete.
- `PYTHONPATH=. python scripts/webhook_follow_up_digest.py` — POST the same digest to **`FOLLOW_UP_WEBHOOK_URL`** (Slack incoming webhook by default: JSON `{"text": "..."}`); `--dry-run` prints whether the URL is set.
- `PYTHONPATH=. python scripts/telegram_follow_up_digest.py` — send the digest with **Telegram** `sendMessage` when bot token + chat id are set; `--dry-run` prints whether env is complete.

## Email (optional)

Use an app-specific password (Gmail, Outlook, etc.). TLS defaults to on (`STARTTLS` on port 587). Set `FOLLOW_UP_SMTP_USE_TLS=0` only if your relay does not use STARTTLS.

## Webhook / Slack / Discord (optional)

- **`FOLLOW_UP_WEBHOOK_URL`** — required to send; used by `services/follow_up_webhook.py` and `scripts/webhook_follow_up_digest.py`.
- **`FOLLOW_UP_WEBHOOK_STYLE`** — `slack` (default, `{"text": "..."}`), `discord` (`{"content": "..."}`), or `raw` (`text/plain` body).
- Optional: **`FOLLOW_UP_WEBHOOK_BEARER`** (`Authorization: Bearer …`), **`FOLLOW_UP_WEBHOOK_HEADERS_JSON`** (merge extra headers, JSON object), **`FOLLOW_UP_WEBHOOK_TIMEOUT`** (seconds, default 30).

Long digests are truncated (~3500 chars) so Slack-style webhooks are less likely to reject the payload.

## Telegram (optional)

- **`FOLLOW_UP_TELEGRAM_BOT_TOKEN`** — from [@BotFather](https://t.me/BotFather) when you create a bot.
- **`FOLLOW_UP_TELEGRAM_CHAT_ID`** — numeric id for the user or group that should receive messages (e.g. message your bot, then open `https://api.telegram.org/bot<token>/getUpdates` and read `message.chat.id`).
- Optional: **`FOLLOW_UP_TELEGRAM_TIMEOUT`** (seconds, default 30).

Digest is sent as plain text (no `parse_mode`) so arbitrary job titles and notes do not break Telegram’s Markdown/HTML parsers. Long messages are truncated (~4000 chars).

## Automation (cron / CI)

Schedule `scripts/email_follow_up_digest.py`, `scripts/webhook_follow_up_digest.py`, and/or `scripts/telegram_follow_up_digest.py` with cron, a CI runner, or GitHub Actions. Use the same environment variables as locally; for Postgres-backed trackers in CI, set `TRACKER_USE_DB`, `DATABASE_URL` (or `TRACKER_DATABASE_URL`), and optionally `TRACKER_DEFAULT_USER_ID`.

## Storage

- **CSV / SQLite / Postgres** — columns added automatically (SQLite `ALTER`, Postgres `_pg_ensure_column`).
- **Alembic** — revision `tracker_0002` adds the same columns on Postgres (`alembic upgrade head`).

## Artifact bundle

`GET /api/applications/by-job/{job_id}` includes a `follow_up` object under `artifacts` when any field is set.

## MCP / Streamlit

Use the API or edit the tracker DataFrame in Streamlit when wired; MCP tool not added in this slice.
