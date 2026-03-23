# Job Apply Autofill MCP Server

Quick autofill for job applications (JobRight-style). Works with **LinkedIn Easy Apply** and external ATS when LinkedIn redirects: **Greenhouse**, **Lever**, **Workday**, and other official career sites.

Resumes are **renamed per job**: `{Name}_{Position}_at_{Company}_Resume.pdf`

## Features

- **LinkedIn Easy Apply** – Primary flow: click Easy Apply, fill fields from profile + application_answerer
- **Greenhouse / Lever / Workday** – When LinkedIn redirects to external ATS, detects form type and autofills
- **Proper resume naming** – Each application uses a job-specific resume path when tailored resume exists
- **MCP tools** – Call from Cursor or any MCP client:
  - `prepare_resume_for_job` – Generate job-specific resume path
  - `get_autofill_values` – Get suggested values from candidate profile
  - `apply_to_jobs` – Apply to a list of jobs (LinkedIn + external ATS)
  - `detect_form_type` – Detect LinkedIn vs Greenhouse vs Lever vs Workday from URL

## Setup

### 1. Install dependencies

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
cd /path/to/resume-ai-agent
python -m mcp_servers.job_apply_autofill.server
```

### Add to Cursor MCP config

Edit `~/.cursor/mcp.json` (or Cursor Settings → MCP):

```json
{
  "mcpServers": {
    "job-apply-autofill": {
      "command": "fastmcp",
      "args": ["run", "mcp_servers/job_apply_autofill/server.py"],
      "cwd": "/path/to/resume-ai-agent"
    }
  }
}
```

Or using Python directly:

```json
{
  "mcpServers": {
    "job-apply-autofill": {
      "command": "python",
      "args": ["-m", "mcp_servers.job_apply_autofill.server"],
      "cwd": "/path/to/resume-ai-agent"
    }
  }
}
```

Replace `/path/to/resume-ai-agent` with your project root.

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

## Two-Lane Strategy

- **Auto-apply:** Only for LinkedIn Easy Apply jobs. Use `apply_to_jobs` with a JSON of Easy Apply jobs.
- **Manual-assist:** For Greenhouse, Lever, Workday, or non–Easy Apply. Use `prepare_resume_for_job` and `get_autofill_values` to prepare; apply manually.

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
Resume: ensure_resume_exists_for_job → {Name}_{Position}_at_{Company}_Resume.pdf
    ↓
Log to application_tracker
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

## Disclaimer

Automation may violate LinkedIn’s Terms of Service. Use responsibly for personal job search.
