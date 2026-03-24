"""
Application profile service. Loads and validates candidate_profile.json.
Used by application_answerer and application_runner (Phase 4–5).
"""

import json
import os
from pathlib import Path
from typing import List, Optional


# Default paths: actual (gitignored) or example (template)
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
DEFAULT_PROFILE_PATH = _PROJECT_ROOT / "config" / "candidate_profile.json"
EXAMPLE_PROFILE_PATH = _PROJECT_ROOT / "config" / "candidate_profile.example.json"

# Can override via env
PROFILE_PATH_ENV = "CANDIDATE_PROFILE_PATH"


def _resolve_path(path: Optional[str] = None) -> Path:
    """Resolve profile path: explicit path, env, default, or example fallback."""
    if path:
        p = Path(path)
        if p.is_file():
            return p
    env_path = os.getenv(PROFILE_PATH_ENV)
    if env_path:
        p = Path(env_path)
        if p.is_file():
            return p
    if DEFAULT_PROFILE_PATH.is_file():
        return DEFAULT_PROFILE_PATH
    return EXAMPLE_PROFILE_PATH


def load_profile(path: Optional[str] = None) -> dict:
    """
    Load candidate profile from JSON.
    Tries: explicit path, CANDIDATE_PROFILE_PATH env, config/candidate_profile.json, then example.
    Returns empty dict on parse error.
    """
    resolved = _resolve_path(path)
    try:
        with open(resolved, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError) as e:
        print(f"⚠️ Profile load failed ({resolved}): {e}")
        return {}


# Required fields for auto-apply
AUTO_APPLY_REQUIRED = [
    "full_name", "email", "phone", "linkedin_url",
    "work_authorization_note", "notice_period",
]


def format_application_locations_summary(profile: dict) -> str:
    """
    Human-readable summary of ``application_locations`` for forms (relocation / work location).
    Each item: optional label, city, state_region, country, remote_ok (bool).
    """
    profile = profile or {}
    locs = profile.get("application_locations")
    if not isinstance(locs, list) or not locs:
        return ""
    chunks: List[str] = []
    for raw in locs:
        if not isinstance(raw, dict):
            continue
        label = str(raw.get("label") or "").strip()
        city = str(raw.get("city") or "").strip()
        st = str(raw.get("state_region") or "").strip()
        country = str(raw.get("country") or "").strip()
        remote = raw.get("remote_ok")

        if label:
            core = label
        else:
            core = ", ".join(p for p in (city, st) if p)
        if not core and country:
            core = country
        if not core:
            continue
        if country and country.lower() not in core.lower():
            core = f"{core}, {country}" if core else country
        if remote is True:
            core = f"{core} (remote OK)"
        elif remote is False:
            core = f"{core} (on-site preferred)"
        chunks.append(core)
    return "; ".join(chunks)


def format_mailing_address_oneline(profile: dict) -> str:
    """
    Single-line mailing address from ``mailing_address`` (street, city, state, postal, country).
    """
    profile = profile or {}
    ma = profile.get("mailing_address")
    if not isinstance(ma, dict):
        return ""
    line1 = str(ma.get("street_line1") or "").strip()
    line2 = str(ma.get("street_line2") or "").strip()
    city = str(ma.get("city") or "").strip()
    st = str(ma.get("state_region") or "").strip()
    postal = str(ma.get("postal_code") or "").strip()
    country = str(ma.get("country") or "").strip()
    city_state = ", ".join(p for p in (city, st, postal) if p)
    parts = [p for p in (line1, line2, city_state, country) if p]
    return ", ".join(parts)


def validate_profile(profile: dict) -> list[str]:
    """
    Validate profile and return list of warnings (missing fields, invalid formats).
    Does not raise; returns empty list if fully valid.
    """
    warnings = []
    required = ["full_name", "email"]
    for k in required:
        if not profile.get(k) or not str(profile.get(k)).strip():
            warnings.append(f"Missing or empty: {k}")

    if profile.get("email") and "@" not in str(profile.get("email", "")):
        warnings.append("email does not look valid")

    if profile.get("linkedin_url") and "linkedin.com" not in str(profile.get("linkedin_url", "")).lower():
        warnings.append("linkedin_url may be incorrect")

    if profile.get("github_url") and "github.com" not in str(profile.get("github_url", "")).lower():
        warnings.append("github_url may be incorrect")

    short = profile.get("short_answers", {})
    if not isinstance(short, dict):
        warnings.append("short_answers should be an object")

    locs = profile.get("application_locations")
    if locs is not None and not isinstance(locs, list):
        warnings.append("application_locations should be a list of location objects")
    ma = profile.get("mailing_address")
    if ma is not None and not isinstance(ma, dict):
        warnings.append("mailing_address should be an object with street/city/state fields")

    return warnings


def is_auto_apply_ready(profile: dict) -> bool:
    """
    True if profile has all required fields for auto-apply.
    """
    profile = profile or {}
    for k in AUTO_APPLY_REQUIRED:
        if not profile.get(k) or not str(profile.get(k)).strip():
            return False
    return True


def get_short_answer(profile: dict, key: str, job_context: Optional[dict] = None) -> str:
    """
    Get a short answer by key from profile.short_answers.
    job_context: optional dict with company, role for templating (future).
    """
    short = profile.get("short_answers", {})
    if isinstance(short, dict):
        return str(short.get(key, "")).strip()
    return ""


def ensure_profile_exists() -> bool:
    """
    Ensure candidate_profile.json exists. If not, copy from example.
    Returns True if profile file exists after call.
    """
    if DEFAULT_PROFILE_PATH.is_file():
        return True
    if EXAMPLE_PROFILE_PATH.is_file():
        try:
            import shutil
            DEFAULT_PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(EXAMPLE_PROFILE_PATH, DEFAULT_PROFILE_PATH)
            print(f"Created {DEFAULT_PROFILE_PATH} from example. Edit with your details.")
            return True
        except OSError as e:
            print(f"Could not create profile: {e}")
            return False
    return False
