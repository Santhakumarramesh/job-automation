# Safe Delete Checklist

Repo cleanup decisions for Career Co-Pilot Pro.

## ✅ Delete now (safe)

| Item | Action | Why |
|------|--------|-----|
| `.DS_Store` | Add to `.gitignore` (already present) | Mac metadata, never versioned |
| `.vercel/` | `git rm -r --cached .vercel/` + add to `.gitignore` | Deployment state, not source |

## ⚠️ Review before deleting

### `job applications automation /`

**Recommendation: DELETE** — High-confidence duplicate.

- Has its own `.git` (nested repo)
- Duplicate docs: APIFY_SETUP, DEPLOY, LINKEDIN_SETUP, etc.
- Root app has consolidated structure (`app/`, `agents/`, `services/`, `ui/`)
- Folder name suggests old copy, not intentional module

**Dependency:** `dashboard/app.py` and `dashboard/excel_sync.py` reference this folder for `job_applications.csv`. Update them to use root `job_applications.csv` (from `application_tracker`) first.

```bash
# After updating dashboard paths and confirming no imports:
rm -rf "job applications automation "
```

### `candidate_resumes/`

**Recommendation: Already in `.gitignore`** — No action if empty. If it has committed files:

```bash
git rm -r --cached candidate_resumes/
```

### `model_artifacts/`

**Recommendation: Add to `.gitignore`** — Keep locally, don’t version.

- Contains: `classifier.pkl`, `tfidf_vectorizer.pkl`, `meta_scaler.pkl`, `model_config.json`
- `agents/job_guard.py` uses LLM only; no references to these artifacts
- Regenerate with `model_training/train_fast.py` if needed

```bash
git rm -r --cached model_artifacts/
# Add model_artifacts/ to .gitignore
```

### `model_training/` ✓ Removed

- `job_guard` uses LLM; sklearn training code was obsolete
- Removed in cleanup (Oct 2025)

### `test_all_tabs.py` ✓ Done

**Moved to `tests/test_streamlit_tabs.py`** — Run from root: `python tests/test_streamlit_tabs.py`

## ✅ Keep

- `vercel.json` — Deployment config
- `README.md`, `pyproject.toml`, `requirements.txt`
- `app/`, `agents/`, `services/`, `ui/`, `providers/`, `mcp_servers/`
- `tests/`
- `config/`, `docs/`, `Master_Resumes/`

## Execution order

1. Add `.vercel/` to `.gitignore` ✓
2. `git rm -r --cached .vercel/` ✓
3. Delete `.DS_Store` files: `find . -name .DS_Store -delete`
4. Run checklist items after manual review
