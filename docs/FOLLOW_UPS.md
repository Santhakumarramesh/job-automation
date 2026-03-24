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

## Storage

- **CSV / SQLite / Postgres** — columns added automatically (SQLite `ALTER`, Postgres `_pg_ensure_column`).
- **Alembic** — revision `tracker_0002` adds the same columns on Postgres (`alembic upgrade head`).

## Artifact bundle

`GET /api/applications/by-job/{job_id}` includes a `follow_up` object under `artifacts` when any field is set.

## MCP / Streamlit

Use the API or edit the tracker DataFrame in Streamlit when wired; MCP tool not added in this slice.
