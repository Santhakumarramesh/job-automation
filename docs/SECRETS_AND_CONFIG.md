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

- **Error** if `API_KEY`, all JWT modes (`JWT_SECRET`, `JWT_JWKS_URL`, `JWT_ISSUER`), and `M2M_API_KEY` are unset (fully open gateway).
- **Error** if `DEMO_USER_IS_ADMIN` is enabled.

### Worker (`context=worker`)

- **Error** if `REDIS_BROKER` is empty.
- **Error** (strict only) if `OPENAI_API_KEY` is missing/too short.

### Warnings (non-fatal)

- Localhost Redis URLs when `APP_ENV=production`.
- Short `JWT_SECRET` in production (< 32 chars).
- `JWT_JWKS_URL` or `JWT_ISSUER` without `JWT_AUDIENCE` in production (audience checks recommended).
- Postgres / S3 / PyJWT mismatch (see `services/startup_checks.py`).

## LLM performance tuning (Phase 5)

These env vars apply mainly to **Celery worker** pipelines (resume tailoring + cover letter + optional project generation/humanization).

| Variable | Meaning |
|----------|---------|
| `CCP_OPENAI_MODEL` | LLM model name used across pipeline steps that currently default to `gpt-4o`. Example: `gpt-4o-mini`. |
| `CCP_FAST_PIPELINE=1` | Speed mode: skips expensive **project generation** and **self-humanization** passes (resume + cover letter). Also skips the “tone matching” company-info retrieval step for faster cover-letter generation. |

If `CCP_FAST_PIPELINE` is enabled, the pipeline still produces `tailored_resume_text` and `cover_letter_text`, but may omit project/custom additions and runs fewer LLM calls.

## Browser automation performance tuning (Phase 5)

These env vars apply mainly to the Playwright runner (`agents/application_runner.py`) sleeps/waits.

| Variable | Meaning |
|----------|---------|
| `CCP_FAST_BROWSER_PIPELINE=1` | Speed mode for browser waits (reduces `page.wait_for_timeout(...)` delays). |
| `CCP_BROWSER_WAIT_MULTIPLIER` | Multiplier applied to runner waits in fast mode (default `0.25`). |

If you see increased “DOM unmapped” rates or flakiness, raise `CCP_BROWSER_WAIT_MULTIPLIER` (e.g. `0.5`) instead of disabling the mode.

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

## JWT role templates (Phase 4, optional)

Some IdPs prefer a **single template** claim (e.g. `role_template: "operator_approver"`) instead of enumerating every RBAC string.

| Variable | Meaning |
|----------|---------|
| `JWT_ROLE_TEMPLATE_CLAIM` | JWT claim name to read (default `role_template`). |
| `JWT_ROLE_TEMPLATE_MAP` | JSON object: template name → list of role strings (or one comma-separated string). Names and roles are normalized to lowercase; unknown templates are ignored. |
| `M2M_ROLE_TEMPLATE` | Optional template name for **M2M** principals (`M2M_API_KEY` path); uses the same map. |

Expansion is applied in `app/auth.py` **after** collecting normal `role` / `roles` / `realm_access` claims. The resolved template string is stored on `User.role_template` for observability.
- Optional CORS for browser clients: `API_CORS_ORIGINS` — `services/api_cors.py` (production rejects `*` unless `API_CORS_SKIP_WILDCARD_PROD_CHECK=1`; see startup checks)
