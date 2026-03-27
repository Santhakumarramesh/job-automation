# Phase 11 — Production-Ready Queue Architecture

## Core Product Rule

> **Discovery finds jobs. MCP evaluates jobs. User approves jobs. Runner applies jobs.**

No application is submitted without explicit user approval. This is enforced at the DB level via `job_state = approved_for_apply`.

---

## 8-Phase Pipeline Summary

| Phase | Module | What it does |
|---|---|---|
| 1 | `services/fit_engine.py` | Structured fit scoring (role family + seniority + evidence) |
| 2 | `services/resume_package_service.py` | Truthful ATS optimizer (truth-safe ceiling, no fabrication) |
| 3 | `services/job_prefilter.py` | High-confidence discovery filter |
| 4 | `services/apply_queue_service.py` | Queue state machine + SQLite DB |
| 5 | `mcp_servers/.../server.py` | `approve_jobs_for_apply` MCP tool |
| 6 | `agents/queue_runner_executor.py` | One-by-one apply runner |
| 7 | `services/apply_queue_service.py` | Full lifecycle state tracking |
| 8 | `ui/candidate_app.py` | 5-page Streamlit workflow |

---

## Queue State Machine

```
[Discovered]
     │
     ▼
  skip ──────────────────────────────────────────► [Dead]
     │
  review_fit ──── (fit score 55–69) ──► user reviews
     │
  review_resume ── (resume check)
     │
  ready_for_approval
     │
  ◄──────────── USER APPROVES ──────────────►
     │
  approved_for_apply
     │
  applying  ←──── Queue Runner picks up here
     │
  applied ──► [Done]
     │
  blocked ──► [Manual action needed]
```

---

## Fit Engine (Phase 1)

**File**: `services/fit_engine.py`

### Role Families Matched
- `ai_ml_engineer` — ML Engineer, Applied Scientist, AI Engineer
- `genai_engineer` — GenAI, LLM, Prompt Engineer
- `ai_agent_engineer` — Agentic AI, Multi-agent, Automation Engineer
- `mlops_engineer` — MLOps, Platform, Infrastructure for ML
- `data_scientist` — Data Science, Analytics Engineering

### Scoring Formula
```
overall_fit = (role_match × 0.35) + (seniority_match × 0.25) + (exp_match × 0.25) + (ats_contribution × 0.15)
```

### Decision Thresholds
| Score | Decision |
|---|---|
| ≥ 70 AND gap_count ≤ 1 | `apply` |
| ≥ 55 | `review_fit` |
| < 55 | `skip` |

### Experience Evidence Levels
- `supported` — skill is in resume + verified evidence map
- `partially_supported` — skill mentioned but limited depth
- `unsupported` — skill not found in resume
- `manual_review` — complex requirement needing human judgment

---

## ATS Optimizer (Phase 2)

**File**: `services/resume_package_service.py`
**Wraps**: `agents/iterative_ats_optimizer.py`

### Truth-Safe Ceiling
The optimizer loops until:
1. Target ATS score reached (default 85), OR
2. No more *truthful* improvements are possible

`get_truthful_missing_keywords()` filters out keywords not supported by the master resume — the system **never fabricates** skills or experiences.

### Package Versions
Each job gets a versioned package at:
```
generated_resumes/_packages/{version_id}/
├── resume.pdf          # optimized tailored PDF
├── resume.txt          # plain text version
└── package.json        # metadata (scores, keywords, iterations)
```

**Package statuses**: `not_generated → generated → optimized_truth_safe → approved → uploaded`

---

## Queue Service (Phase 4)

**File**: `services/apply_queue_service.py`
**DB**: `job_applications.db` (SQLite, `apply_queue` table)

### Key Functions
```python
upsert_queue_item(job_url, job_title, company, job_description, fit_data, ats_score, ...)
attach_package(item_id, package)
approve_job(item_id)        # → approved_for_apply
hold_job(item_id)           # → review_fit
skip_job(item_id)           # → skip
mark_applied(item_id)       # → applied
mark_blocked(item_id)       # → blocked
get_approved_queue()        # → list of approved_for_apply items
get_queue_summary()         # → counts by state
```

---

## Queue Runner (Phase 6)

**File**: `agents/queue_runner_executor.py`

### Per-Job Flow
1. **Pull** item from `approved_for_apply`
2. **Generate package** via `generate_package_for_job()` (truth-safe ATS optimizer)
3. **Get form answers** via `answer_question_structured()` from truth inventory
4. **Execute apply** via `application_service.apply_single_job()` or Chrome browser
5. **Update state** → `applied` or `blocked`

### Key Config (`RunnerConfig`)
```python
RunnerConfig(
    dry_run=False,            # True = prepare only, don't submit
    max_jobs=20,              # safety cap per run
    target_ats_score=85.0,    # ATS target for resume generation
    max_ats_iterations=5,     # max optimizer loops
    inter_job_delay_sec=5.0,  # rate limiting between jobs
    skip_resume_generation=False,  # reuse existing package
)
```

---

## MCP Tools Added (Phase 11)

| Tool | Purpose |
|---|---|
| `answer_form_fields` | Get truth-inventory answers for detected form fields |
| `generate_tailored_resume_for_job` | Run iterative ATS optimizer for a job, return package |
| `get_job_queue_for_review` | Score batch of jobs, group by high_confidence/review_fit/skip, upsert to queue |
| `approve_jobs_for_apply` | Mark queue items as approved_for_apply |
| `run_approved_queue` | Process all approved items (generate resume → fill forms → apply) |
| `get_queue_status` | Current queue counts + pending approvals + recent applied |

---

## UI Workflow (Phase 8)

**File**: `ui/candidate_app.py`

### 5-Page Flow
1. **Discover** — Search for jobs, paste job URLs, see prefiltered results
2. **Review Queue** — Approve / Hold / Skip individual jobs with fit breakdown
3. **Resume Review** — Generate tailored resume per job, review ATS scores
4. **Apply Queue** — "Apply to All" or "Dry Run" on approved jobs
5. **Tracker** — Full lifecycle table with state filtering

---

## Form Answer Pipeline

The runner calls `answer_question_structured()` for every standard question **before** touching any form. This replaces the previous broken approach of reading LinkedIn's pre-filled DOM values.

### Correct Answers (from `candidate_profile.json`)
| Question | Answer |
|---|---|
| Years Python | 3+ |
| Years ML | 2+ |
| Years SQL | 3+ |
| Years NLP | 2+ |
| Years AWS | 1+ |
| Visa sponsorship | Yes (F-1 STEM OPT) |
| Authorized to work in US | Yes |

---

## Running the Queue

### Via MCP Tool (Claude / Cowork)
```
1. get_job_queue_for_review(jobs_json=[...])   → scores + upserts to DB
2. approve_jobs_for_apply(item_ids_json=[...]) → marks approved
3. run_approved_queue(dry_run=True)            → preview what will happen
4. run_approved_queue(dry_run=False)           → execute
```

### Via Streamlit UI
```
streamlit run ui/candidate_app.py
→ Page 2: Review Queue → Approve jobs
→ Page 4: Apply Queue → "Apply to All"
```

### Via Direct Python
```python
from agents.queue_runner_executor import run_approved_queue, RunnerConfig

result = run_approved_queue(RunnerConfig(dry_run=True))
print(result)
```
