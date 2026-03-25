# LinkedIn MCP Integration

Your app supports **LinkedIn MCP** as a job source alongside Apify. Use it for direct LinkedIn job search with filters.

## Prerequisites

1. **Python 3.10+**
2. **uv** (recommended) or pip
3. **LinkedIn account** (for authentication)

## Setup

### 1. Clone and install linkedin-mcp-server

```bash
git clone https://github.com/eliasbiondo/linkedin-mcp-server.git
cd linkedin-mcp-server
uv sync
uv run patchright install
```

### 2. Authenticate

```bash
uv run linkedin-mcp-server --login
```

A browser window opens. Log in to LinkedIn. The session is saved at `~/.linkedin-mcp-server/browser-data`.

### 3. Run the MCP server (HTTP mode)

```bash
uv run linkedin-mcp-server --transport streamable-http --host 0.0.0.0 --port 8001
```

Keep this running in a terminal. Default URL: `http://127.0.0.1:8001/mcp`.

### 4. Optional: Python MCP client

For the job finder to call LinkedIn MCP from the Streamlit app:

```bash
pip install mcp
```

### 5. Use in the app

1. Open the **AI Job Finder** tab
2. Select **LinkedIn MCP** or **Both** as the job source
3. Click **Find Jobs**

## Environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LINKEDIN_MCP_URL` | MCP server URL | `http://127.0.0.1:8001/mcp` |

## Architecture

```
linkedin-mcp-server (HTTP)  ←→  providers/linkedin_mcp_jobs.py  ←→  services/enhanced_job_finder.py
                                                                         ↓
                                                              normalized JobListing
                                                                         ↓
                                                              ATS → Resume → Cover Letter → Tracker
```

## Cursor MCP configuration (optional)

To use LinkedIn MCP directly from Cursor AI, add to your MCP config:

```json
{
  "mcpServers": {
    "linkedin": {
      "command": "uv",
      "args": [
        "--directory", "/path/to/linkedin-mcp-server",
        "run", "linkedin-mcp-server"
      ]
    }
  }
}
```

For HTTP mode (remote or inspector):

```json
{
  "mcpServers": {
    "linkedin": {
      "url": "http://127.0.0.1:8001/mcp"
    }
  }
}
```

## Apply on LinkedIn

After finding jobs via LinkedIn MCP:

1. Select jobs in the Job Finder tab
2. Click **Export jobs for LinkedIn apply (JSON)**
3. Run: `python scripts/apply_linkedin_jobs.py linkedin_jobs_to_apply.json --no-headless`
4. Set `LINKEDIN_EMAIL` and `LINKEDIN_PASSWORD` in `.env` or environment
5. Add your resume PDF to `Master_Resumes/` or set `RESUME_PATH`

Requires: `pip install playwright && playwright install chromium`

## Disclaimer

LinkedIn scraping may violate their Terms of Service. Use responsibly for personal job search. The authors are not responsible for misuse.
