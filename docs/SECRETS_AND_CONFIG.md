# Secrets & configuration (Phase 3.5)

## Environment separation

| `APP_ENV` / `ENV` | Meaning |
|-------------------|---------|
| `development` (default) | Warnings only; API can run without `API_KEY` (demo-user). |
| `production` / `prod` | **Fatal checks** unless `STRICT_STARTUP=0` (see below). |

## Strict startup

| Variable | Effect |
|----------|--------|
| `STRICT_STARTUP=1` | Force fatal validation in **any** `APP_ENV`. |
| `STRICT_STARTUP=0` | Disable **exit on error** even in production (errors still printed). Use only for recovery/debug. |

On fatal validation failure the process calls **`sys.exit(1)`** after printing `❌ Startup: ...`.

### Production / strict rules (API `context=app`)

- **Error** if both `API_KEY` and `JWT_SECRET` are unset (fully open gateway).
- **Error** if `DEMO_USER_IS_ADMIN` is enabled.

### Worker (`context=worker`)

- **Error** if `REDIS_BROKER` is empty.
- **Error** (strict only) if `OPENAI_API_KEY` is missing/too short.

### Warnings (non-fatal)

- Localhost Redis URLs when `APP_ENV=production`.
- Short `JWT_SECRET` in production (< 32 chars).
- Postgres / S3 / PyJWT mismatch (see `services/startup_checks.py`).

## AWS Secrets Manager

1. Create a secret (e.g. `career-co-pilot/prod`) whose value is **JSON**:

   ```json
   {
     "OPENAI_API_KEY": "sk-...",
     "API_KEY": "...",
     "JWT_SECRET": "...",
     "REDIS_BROKER": "redis://..."
   }
   ```

2. Set:

   ```bash
   export AWS_SECRETS_MANAGER_SECRET_ID=career-co-pilot/prod
   # optional:
   export AWS_SECRETS_MANAGER_REGION=us-east-1
   ```

3. Install **`boto3`** (`pip install boto3` or `pip install .[s3]`).

4. IAM: grant `secretsmanager:GetSecretValue` on that secret.

**Precedence:** Keys already set in the process environment (e.g. from `.env` or the container orchestrator) are **not** overwritten by Secrets Manager.

## Where checks run

- **FastAPI:** `app/main.py` lifespan → `run_startup_checks("app")`.
- **Streamlit:** `run_streamlit.py` after `load_dotenv()` → `run_startup_checks("streamlit")`.
- **Celery workers:** not auto-run (avoid import side effects). Validate in CI or an entrypoint:

  ```bash
  PYTHONPATH=. python scripts/check_startup.py worker --fail-on-errors
  ```

  Or inline: `python -c "from services.startup_checks import run_startup_checks; run_startup_checks('worker')"`.

- **CLI (any context):** `PYTHONPATH=. python scripts/check_startup.py app|worker|streamlit` — prints the same errors/warnings as startup; add `--json`, `--fail-on-errors`, or `--fail-on-warnings` for automation.

## Reference

- Implementation: `services/startup_checks.py`, `services/secrets_loader.py`
- Example env keys: `.env.example`
- Optional CORS for browser clients: `API_CORS_ORIGINS` — `services/api_cors.py`
