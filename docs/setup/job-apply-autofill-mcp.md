# Career Copilot MCP

Quick autofill for job applications (JobRight-style). Works with **LinkedIn Easy Apply** and external ATS when LinkedIn redirects: **Greenhouse**, **Lever**, **Workday**, and other official career sites.

Resumes are **renamed per job**: `{Name}_{Position}_at_{Company}_Resume.pdf`

## Features

- **LinkedIn Easy Apply** – Primary flow: click Easy Apply, fill fields from profile + application_answerer
- **Greenhouse / Lever / Workday** – When LinkedIn redirects to external ATS, detects form type and autofills
- **Proper resume naming** – Each application uses a job-specific resume path when tailored resume exists
- **MCP tools** – Call from Cursor or any MCP client:

  **Discovery:** `prepare_resume_for_job`, `get_autofill_values` (REST: ``POST /api/ats/autofill-values``), `detect_form_type` (REST: ``GET /api/ats/form-type``), `confirm_easy_apply`

  **Decision:** `decide_apply_mode`, `get_address_for_job`, `validate_candidate_profile` (REST: ``POST /api/ats/validate-profile``), `score_job_fit`, `batch_prioritize_jobs` (REST: ``POST /api/ats/batch-prioritize-jobs``)

  **Execution:** `apply_to_jobs`, `dry_run_apply_to_jobs`, `prepare_application_package`

  **Truth + discovery:** `build_truth_inventory_from_master_resume`, `search_jobs` (LinkedIn MCP; set `LINKEDIN_MCP_URL`)

  **ATS / forms (static + optional live):** `analyze_form`, `describe_ats_platform`, `analyze_form_live` (live probe needs `ATS_ALLOW_LIVE_FORM_PROBE=1` and Playwright Chromium — read-only DOM listing)

  **Review:** `review_unmapped_fields`, `application_audit_report`, `generate_recruiter_followup`

## Setup

### 0. Production-style install (system Python, repo root)

From the project root (path may contain spaces — use quotes):

```bash
bash setup.sh
bash start.sh
```

- **`setup.sh`** — `pip install -e ".[mcp]"`, seeds `.env` from `.env.example` if missing.
- **`start.sh`** — **stdio** MCP (Claude Desktop). Use **`bash start.sh --sse`** for HTTP/SSE (e.g. `curl -sL -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8765/sse`). Override host/port with `MCP_SSE_HOST` / `MCP_SSE_PORT`.

Claude Desktop: merge **[claude_desktop_config.example.json](claude_desktop_config.example.json)** into your app config (macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`), replacing `/ABSOLUTE/PATH/TO/...` with your real repo path.

**Config notes**

- **`start.sh`** (default, no args) runs **`python3 -m mcp_servers.job_apply_autofill.server`** — same module as `mcp_servers/job_apply_autofill/server.py`. Cowork mounts may use `src/career_copilot/`; this Mac layout keeps MCP at `mcp_servers/job_apply_autofill/`.
- **LLM keys:** In-repo tools (e.g. recruiter follow-up, ATS) expect **`OPENAI_API_KEY`** (see `.env.example`). **`ANTHROPIC_API_KEY`** is for Claude itself, not automatically used by this Python stack unless you wire it.
- **Tracker:** Optional **`TRACKER_USE_DB=1`** and **`TRACKER_DB_PATH`** (absolute path to SQLite file) match `.env.example`. There is no standard **`OUTPUT_DIR`** env in this repo; omit it or map outputs via documented paths (`generated_resumes/`, etc.).
- **Secrets:** Prefer a project **`.env`** (not committed) and keep Claude’s `env` block minimal (e.g. `PYTHONPATH` only), *or* use Claude’s `env` only if you accept secrets sitting in `claude_desktop_config.json`. Never paste real passwords into shared chats.

### 1. Install dependencies (manual)

```bash
pip install fastmcp playwright mcp
playwright install chromium
```

### 2. Configure profile

Copy and edit your candidate profile:

```bash
cp config/candidate_profile.example.json config/candidate_profile.json
# Edit: full_name, email, phone, linkedin_url, etc.
```

### 3. Add resume

Place your PDF in `Master_Resumes/` or set `RESUME_PATH` in `.env`.

### 4. LinkedIn credentials

Set in `.env`:

```
LINKEDIN_EMAIL=your@email.com
LINKEDIN_PASSWORD=your_password
```

## Run the MCP server

### Stdio (for Cursor MCP config)

```bash
cd /path/to/career-co-pilot-pro
python -m mcp_servers.job_apply_autofill.server
```

### Add to Cursor MCP config

Edit `~/.cursor/mcp.json` (or Cursor Settings → MCP):

```json
{
  "mcpServers": {
    "career-copilot-mcp": {
      "command": "fastmcp",
      "args": ["run", "mcp_servers/job_apply_autofill/server.py"],
      "cwd": "/path/to/Career Copilot MCP"
    }
  }
}
```

Or using Python directly:

```json
{
  "mcpServers": {
    "career-copilot-mcp": {
      "command": "python",
      "args": ["-m", "mcp_servers.job_apply_autofill.server"],
      "cwd": "/path/to/Career Copilot MCP"
    }
  }
}
```

Replace `/path/to/Career Copilot MCP` with your project root.

## Tool reference

| Tool | Purpose |
|------|---------|
| `decide_apply_mode` | Central policy: auto_easy_apply \| manual_assist \| skip; REST: ``POST /api/ats/decide-apply-mode`` |
| `validate_candidate_profile` | Check profile completeness, auto_apply_ready; REST: ``POST /api/ats/validate-profile`` |
| `score_job_fit` | Fit score, ATS score, missing keywords, unsupported requirements; REST: ``POST /api/ats/score-job-fit`` |
| `confirm_easy_apply` | Open job page, verify Easy Apply button exists |
| `get_address_for_job` | Mailing address from profile for job location; REST: ``POST /api/ats/address-for-job`` |
| `prepare_resume_for_job` | Job-specific resume path |
| `get_autofill_values` | Profile-based form values; REST: ``POST /api/ats/autofill-values`` |
| `prepare_application_package` | Resume + autofill + fit/ATS for manual-assist |
| `apply_to_jobs` | Live apply (Easy Apply only by default) |
| `dry_run_apply_to_jobs` | Fill without submit; safe testing |
| `detect_form_type` | LinkedIn vs Greenhouse vs Lever vs Workday; REST: ``GET /api/ats/form-type?url=`` |
| `review_unmapped_fields` | Summarize missed form fields |
| `application_audit_report` | Batch run summary |
| `batch_prioritize_jobs` | Rank jobs by fit, ATS, Easy Apply; REST: ``POST /api/ats/batch-prioritize-jobs`` |
| `generate_recruiter_followup` | LinkedIn message + email draft |
| `analyze_form` | Static ATS/board form hints + platform metadata (no browser) |
| `describe_ats_platform` | Provider labels, v1 auto-submit policy, static analyze preview |
| `analyze_form_live` | Optional headless Chromium field list + static merge; requires `ATS_ALLOW_LIVE_FORM_PROBE=1` |
| `build_truth_inventory_from_master_resume` | Parse master resume → skills/tools/projects/URLs (truth base for fit + ATS) |
| `search_jobs` | LinkedIn MCP job search → normalized job rows (`LINKEDIN_MCP_URL`); REST: ``POST /api/ats/search-jobs`` |

## Usage from Cursor

1. **Prepare resume for a job**  
   Call `prepare_resume_for_job` with job_title and company.

2. **Get autofill values**  
   Call `get_autofill_values` to fetch profile-based values for forms.

3. **Apply to jobs**  
   Export jobs from the AI Job Finder tab (JSON), then call `apply_to_jobs` with the JSON string. The server will:
   - Log into LinkedIn
   - For each job: detect LinkedIn vs external ATS
   - Fill forms using profile + application_answerer
   - Use job-specific resume when available
   - Submit and log to application tracker

4. **Detect form type**  
   Call `detect_form_type` with a URL to see if it’s LinkedIn, Greenhouse, Lever, or Workday.

## Two-Lane Strategy (Enforced in Code)

- **Auto-apply (default):** Only LinkedIn Easy Apply. `apply_to_jobs` rejects non–Easy Apply unless `manual_assist=True`.
- **Submission safeguards:** `require_safeguards=True` (default) skips jobs without fit_decision=Apply, ats_score≥85 when metadata present.
- **Manual-assist:** Set `manual_assist=True` for Greenhouse, Lever, Workday. Use `prepare_resume_for_job` and `get_autofill_values` to prepare; apply manually.

See [docs/TWO_LANE_APPLY_STRATEGY.md](docs/TWO_LANE_APPLY_STRATEGY.md) for details.

## Flow

```
Jobs (JSON) → apply_to_jobs
    ↓
For each job URL:
  - detect_form_type(url)
  - LinkedIn → run_linkedin_application (Easy Apply modal)
  - Greenhouse/Lever/Workday → fill_external_ats_form
    ↓
Resume: ensure_resume_exists_for_job → {Name}_{Position}_at_{Company}_Resume.pdf (source: explicit path, or `MASTER_RESUME_PDF` / sorted `Master_Resumes/*.pdf` — see `services/resume_naming.py`)
    ↓
Log to `services/application_tracker.py`
```

## Supported URLs

| Type        | Example URLs                                                |
|------------|-------------------------------------------------------------|
| LinkedIn   | linkedin.com/jobs/view/...                                  |
| Greenhouse | greenhouse.io, boards.greenhouse.io, jobs.greenhouse.io     |
| Lever      | lever.co, jobs.lever.co                                     |
| Workday    | workday.com, myworkdayjobs.com                              |
| Generic    | Other ATS – uses common field patterns                      |

## Options

- `dry_run=True` – Fill forms without submitting
- `rate_limit_seconds=90` – Minimum delay between applications
- `RESUME_PATH` – Override default resume location
- `CANDIDATE_NAME` – Used for resume filename when profile missing
- `ATS_ALLOW_LIVE_FORM_PROBE=1` – Enables MCP `analyze_form_live` (and API `POST /api/ats/analyze-form/live`); read-only DOM probe

## Login challenges

If LinkedIn shows a verification page (CAPTCHA, phone/email check, or security challenge):

1. **Complete verification in a browser** – Open https://linkedin.com, log in, and finish any prompts.
2. **Retry** – Run `apply_to_jobs` again. LinkedIn may trust the session for a while.
3. **Use dry run first** – `dry_run=True` fills without submitting; reduces risk of triggering challenges.

The server detects checkpoint/challenge URLs and returns an error immediately instead of failing later. There is no automated recovery; manual login and retry is the supported flow.

## Disclaimer

Automation may violate LinkedIn’s Terms of Service. Use responsibly for personal job search.
