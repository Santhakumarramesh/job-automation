# Database migrations (Alembic)

## Scope

| Backend | Schema management |
|---------|-------------------|
| **PostgreSQL** (`TRACKER_USE_DB=1` + `postgresql://…`) | **Alembic** (this doc) + optional auto-`ALTER` in `services/tracker_db.py` for new columns |
| **SQLite** | `services/tracker_db.initialize_tracker_db()` — no Alembic |

## Install

```bash
pip install .[postgres,migrations]
```

## Configure

Set the same URL the app uses:

```bash
export TRACKER_DATABASE_URL="postgresql://user:pass@host:5432/dbname"
# or
export DATABASE_URL="postgresql://..."
```

From the **repository root** (where `alembic.ini` lives):

```bash
alembic upgrade head
```

### Existing database (table already created by the app)

If `applications` was created by `initialize_tracker_db()` before you adopted Alembic, the baseline revision **detects the table and skips `CREATE`**, but still records `tracker_0001` in `alembic_version` on first `upgrade`.

### Brand-new database

Run `alembic upgrade head` before or after first app start — both are safe.

## New revisions

```bash
alembic revision -m "describe change"
```

Edit the generated file under `alembic/versions/`, then `alembic upgrade head`.

Baseline: `tracker_0001` (applications). **Phase 12:** `tracker_0002` adds `follow_up_at`, `follow_up_status`, `follow_up_note` (idempotent if columns already exist).

## Downgrade

`tracker_0001` **downgrade drops `applications`** — only use on throwaway DBs.

## CI / tests

With `TEST_POSTGRES_URL` set, `tests/test_tracker_postgres.py` can run `alembic upgrade head` to verify migrations apply.
