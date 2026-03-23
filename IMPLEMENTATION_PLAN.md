# Implementation Plan: Master-Resume-Driven MCP LinkedIn Auto-Apply System

This document turns the repo review into a concrete implementation plan: exact files, folder structure, and what each module should do.

---

## Current State vs. Target State

| Layer | Current | Target |
|-------|---------|--------|
| **Job source** | Apify + LinkedIn MCP (partial) | Unified provider layer with LinkedIn MCP as primary |
| **Job schema** | `JobListing` exists | Add `job_id`, `easy_apply`, `posted_at`, `experience_level` |
| **Master resume** | `master_resume_guard.py` (helper) | Central gatekeeper + profile inventory |
| **Candidate profile** | Sidebar inputs only | `candidate_profile.json` / DB store |
| **Application answers** | None | `application_answerer.py` |
| **Auto-apply** | Export JSON for external script | `application_runner.py` (MCP/browser) |
| **Tracker** | CSV with 6 columns | Rich tracker with source, URLs, status, audit trail |
| **README** | "Production-ready", "100% ATS" | Honest positioning |

---

## Phase 1: Unified Provider Layer & Job Schema ✅ DONE

### 1.1 Extend `providers/common_schema.py` ✅

Add to `JobListing`:
```
job_id: str = ""           # Provider-specific ID (LinkedIn job ID, etc.)
easy_apply: bool = False
posted_at: str = ""
experience_level: str = "" # entry, mid, senior, etc.
apply_url: str = ""       # Dedicated apply URL if different from job_url
```

### 1.2 Rename / Add Provider Modules

| Current | New | Purpose |
|---------|-----|---------|
| `providers/apify_jobs.py` | `providers/apify_provider.py` | Keep; standardize interface |
| `providers/linkedin_mcp_jobs.py` | `providers/linkedin_mcp_provider.py` | Keep; add LinkedIn MCP filters |

**LinkedIn MCP filters to support** (from [linkedin-mcp-server](https://github.com/eliasbiondo/linkedin-mcp-server)):
- `date_posted`: 24h, 1w, 1m
- `job_type`: full_time, part_time, contract, internship
- `experience_level`: entry, mid, senior
- `work_remote`: remote, hybrid, on_site
- `easy_apply`: bool
- `sort_order`: most_recent, most_relevant

### 1.3 Provider Interface

Create `providers/base_provider.py`:
```python
from abc import ABC, abstractmethod
from providers.common_schema import JobListing

class JobProvider(ABC):
    @abstractmethod
    def search(self, keywords: list[str], location: str, filters: dict, max_results: int) -> list[JobListing]:
        pass
    
    @abstractmethod
    def get_job_details(self, job_id: str) -> JobListing | None:
        pass
```

Both `apify_provider.py` and `linkedin_mcp_provider.py` implement this.

### 1.4 Files to Create / Modify ✅

| Action | File | Status |
|--------|------|--------|
| Modify | `providers/common_schema.py` – add job_id, easy_apply, experience_level, apply_url | Done |
| Create | `providers/base_provider.py` – JobProvider + SearchFilters | Done |
| Update | `providers/apify_jobs.py` – ApifyProvider class, job_id in results | Done |
| Update | `providers/linkedin_mcp_jobs.py` – LinkedInMCPProvider, filters support | Done |
| Modify | `providers/registry.py` – filters param, get_provider() | Done |
| Modify | `app.py` – LinkedIn filters expander (easy_apply, date_posted, sort_order) | Done |

---

## Phase 2: Master Resume as Central Gatekeeper ✅ DONE

### 2.1 Upgrade `agents/master_resume_guard.py` ✅

Parse and persist a full profile inventory:

```python
@dataclass
class CandidateProfile:
    skills: set[str]
    tools: set[str]
    projects: set[str]
    education: set[str]
    companies: set[str]
    locations: list[str]           # Preferred / willing to work
    visa_status: str               # F1 OPT, H1B, Green Card, Citizen, etc.
    work_authorization: str         # "No sponsorship needed", etc.
    github_url: str = ""
    linkedin_url: str = ""
    portfolio_url: str = ""
    preferred_roles: list[str] = []
    years_experience: dict[str, int] = {}  # {"Python": 3, "ML": 2}
```

Functions:
- `parse_master_resume(text) -> CandidateProfile`
- `is_job_fit(profile, job: JobListing) -> FitResult` (apply/review/reject + reasons)
- `get_truthful_missing_keywords(profile, jd_keywords) -> list[str]`

### 2.2 Gate Flow

```
Job fetched → is_job_fit(profile, job)
  → reject: skip, log reason
  → review: queue for manual check
  → apply: proceed to tailoring
```

### 2.3 Files to Create / Modify ✅

| Action | File | Status |
|--------|------|--------|
| Modify | `agents/master_resume_guard.py` – CandidateProfile, FitResult, is_job_fit(), locations, visa, URLs | Done |
| Modify | `app.py` – fit_gate_node, gate before score/iterative_ats | Done |

---

## Phase 3: Application Profile Store ✅ DONE

### 3.1 Create `config/candidate_profile.json`

Schema (user-editable, gitignored or in `.env` path):

```json
{
  "full_name": "",
  "email": "",
  "phone": "",
  "current_location": "",
  "visa_status": "F1 OPT",
  "work_authorization_note": "Immediate availability, no sponsorship required",
  "relocation_preference": "Open to remote",
  "notice_period": "Immediate",
  "linkedin_url": "",
  "github_url": "",
  "portfolio_url": "",
  "graduation_date": "",
  "salary_expectation_rule": "Negotiable",
  "short_answers": {
    "why_this_role": "Template...",
    "why_this_company": "Template...",
    "years_python": "3+",
    "years_ml": "2+"
  }
}
```

### 3.2 Create `services/profile_service.py`

- `load_profile(path) -> dict`
- `validate_profile(profile) -> list[str]` (warnings)
- Used by `application_answerer` and `application_runner`

### 3.3 Files to Create ✅

| Action | File | Status |
|--------|------|--------|
| Create | `config/candidate_profile.example.json` (template) | Done |
| Gitignore | `config/candidate_profile.json` (user copies from example) | Done |
| Create | `services/profile_service.py` – load_profile, validate_profile, get_short_answer, ensure_profile_exists | Done |
| Create | `services/__init__.py` | Done |
| Modify | `app.py` – sidebar Application Profile expander | Done |

---

## Phase 4: Answer Composer for Employer Questions ✅ DONE

### 4.1 Create `agents/application_answerer.py` ✅

Responsibilities:
- Read JD + application form questions
- Classify question type (sponsorship, relocation, salary, years, why-role, etc.)
- Answer from `candidate_profile` + master resume
- Stay truthful; no fabrication
- Return short, humanized text (≤150 chars for most fields)

Question types to support:
- Sponsorship / work authorization
- Relocation
- Expected salary
- Years of experience (Python, ML, NLP, etc.)
- Why this role / company
- Availability to start
- Notice period

### 4.2 Interface

```python
def answer_question(
    question_text: str,
    question_type: str | None,  # auto-detect if None
    profile: dict,
    master_resume_text: str,
    job_description: str,
) -> str
```

### 4.3 Files to Create ✅

| Action | File | Status |
|--------|------|--------|
| Create | `agents/application_answerer.py` – answer_question, classify_question, answer_batch | Done |
| Modify | `app.py` – sidebar test question preview | Done |

---

## Phase 5: Application Runner (Auto-Apply Engine) ✅ DONE

### 5.1 Create `agents/application_runner.py` ✅

Responsibilities:
- Open application page (via MCP `get_job_details` + apply URL, or Playwright)
- Detect form fields (text, select, file upload, checkbox)
- Map fields to:
  - `application_answerer` for text
  - `candidate_profile` for links (LinkedIn, GitHub, portfolio)
  - Tailored resume PDF
  - Tailored cover letter (if required)
- Fill fields; skip ambiguous or risky ones
- Submit; capture status
- Save: screenshots, timestamp, submission URL, Q&A audit trail

### 5.2 Integration with LinkedIn MCP

The [linkedin-mcp-server](https://github.com/eliasbiondo/linkedin-mcp-server) provides:
- `search_jobs` – job IDs
- `get_job_details` – full job data
- Browser auth via Patchright

The runner can:
- Use MCP for job data
- Use Playwright/Patchright for form filling (or MCP tools if the server exposes apply actions)

### 5.3 Safety

- Rate limit (e.g., 1 application per 2 minutes)
- Dry-run mode: fill but don't submit
- Flag fields that couldn't be mapped
- Require confirmation for "submit" step

### 5.4 Files to Create ✅

| Action | File | Status |
|--------|------|--------|
| Create | `agents/application_runner.py` – RunConfig, RunResult, fill_linkedin_easy_apply_modal, run_linkedin_application, save_run_results | Done |
| Upgrade | `apply_linkedin_jobs.py` – uses runner, profile, --dry-run, --rate-limit | Done |
| Modify | `.gitignore` – application_runs/ | Done |

---

## Phase 6: Upgrade Tracker & Terminology ✅ DONE

### 6.1 Upgrade `application_tracker.py` ✅

New schema (SQLite or CSV with more columns):

| Column | Purpose |
|--------|---------|
| id | UUID |
| source | apify, linkedin_mcp, url |
| job_id | Provider job ID |
| job_url | Job listing URL |
| apply_url | Application form URL |
| company | |
| position | |
| status | applied, screening, interview, offer, rejected |
| submission_status | submitted, failed, partial |
| resume_path | |
| cover_letter_path | |
| job_description | |
| applied_at | Timestamp |
| recruiter_response | Pending, positive, negative |
| screenshots_path | JSON list of paths |
| qa_audit | JSON of question→answer |
| retry_state | For failed submissions |

### 6.2 Rename ATS Terminology in Code

| Current | New |
|---------|-----|
| `target_score=100` | `target_truthful_score` |
| "100% ATS" | "ATS-oriented matching" |

In `enhanced_ats_checker.py`:
- Separate "ATS formatting score" from "role fit score"
- Add docstring: "Internal estimate; not a guarantee of passing real employer ATS."

### 6.3 Files to Modify ✅

| Action | File | Status |
|--------|------|--------|
| Modify | `application_tracker.py` – rich schema, log_application_from_result, legacy compat | Done |
| Modify | `enhanced_ats_checker.py` – target_truthful_score, internal estimate docstring | Done |
| Modify | `app.py` – tracker column compat (company/Company) | Done |
| Modify | `apply_linkedin_jobs.py` – log to tracker on apply | Done |

---

## Phase 7: Refactor `app.py` into Services ✅ DONE

### 7.1 Target Structure

```
ui/
  streamlit_app.py      # Tabs, forms, display only
services/
  job_search_service.py # get_jobs(provider, filters), uses registry
  ats_service.py        # score_resume, iterative_optimizer, fit_gate
  document_service.py   # tailor, humanize, build PDFs
  application_service.py# log to tracker, load applications
  profile_service.py    # load candidate profile
app.py                  # Thin entry: imports streamlit_app.run()
```

### 7.2 Migration ✅

1. Extract functions from `app.py` into services. Done
2. `app.py` imports from `services/` and `ui/`. Done
3. Streamlit app calls services instead of agents directly. Done

---

## Phase 8: README & Auth ✅ DONE

### 8.1 Update `README.md` ✅

Replace:
- "production-ready" → "prototype / early automation platform" Done
- "100% ATS compatibility" → "ATS-oriented resume matching and tailoring" Done
- Add: "LinkedIn MCP integration is in progress; see LINKEDIN_MCP_SETUP.md." Done

### 8.2 `app/auth.py` ✅

- Auth remains stubbed. README updated: "API auth is stubbed; implement real auth (OAuth2/JWT) before production use."

---

## Recommended Implementation Order

1. **Phase 8** (README, auth note) – quick, low risk  
2. **Phase 1** (provider schema, LinkedIn MCP filters) – unblocks real MCP usage  
3. **Phase 2** (master resume gatekeeper) – you already have a base  
4. **Phase 3** (candidate profile store) – needed for Phase 4–5  
5. **Phase 4** (application_answerer) – needed for Phase 5  
6. **Phase 5** (application_runner) – core auto-apply  
7. **Phase 6** (tracker, ATS wording) – supporting  
8. **Phase 7** (refactor app.py) – can be incremental  

---

## Final Workflow (Target)

```
Master resume + candidate_profile.json
    ↓
LinkedIn MCP search_jobs (with filters)
    ↓
JD fetch + normalize (JobListing)
    ↓
is_job_fit(profile, job) → reject/review/apply
    ↓ (if apply)
ATS-oriented tailoring (truthful only)
    ↓
application_answerer for form questions
    ↓
application_runner: fill, upload, submit
    ↓
Tracker: log + screenshots + audit
```

---

## Post-Implementation Enhancements ✅

| Enhancement | Status |
|-------------|--------|
| **Job Apply Autofill MCP** | Done – LinkedIn Easy Apply + Greenhouse/Lever/Workday, resume naming |
| **Two-lane strategy** | Done – Easy Apply default ON, auto-apply vs manual-assist |
| **Fit threshold 85** | Done – `FIT_THRESHOLD_AUTO_APPLY` in master_resume_guard |
| **docs/TWO_LANE_APPLY_STRATEGY.md** | Done |

---

## References

- [LinkedIn MCP Server](https://github.com/eliasbiondo/linkedin-mcp-server) – job search, details, auth
