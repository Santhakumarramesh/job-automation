"""
Static form / flow hints per ATS label (not live DOM). Helps manual-assist prep and MCP clients
until real ``analyze_form`` scraping exists per board.
"""

from __future__ import annotations

from typing import Any, Dict, List

from providers.job_source import (
    ATS_DICE,
    ATS_GREENHOUSE,
    ATS_LEVER,
    ATS_LINKEDIN_JOBS,
    ATS_OTHER,
    ATS_UNKNOWN,
    ATS_WORKDAY,
)

_DISCLAIMER = (
    "Inventory-based hints only — verify fields on the live application page before submitting."
)


def _sections(*blocks: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list(blocks)


def build_form_hints(provider_id: str, job_url: str) -> Dict[str, Any]:
    """Return a structured hint payload for ``analyze_form`` (v1, no browser)."""
    url = (job_url or "")[:500]
    pid = provider_id or ATS_UNKNOWN

    if pid == ATS_LINKEDIN_JOBS:
        return {
            "status": "schema_hints",
            "provider_id": pid,
            "job_url": url,
            "flow": "linkedin_easy_apply_modal",
            "typical_sections": _sections(
                {
                    "id": "contact",
                    "label": "Contact",
                    "common_fields": ["email", "phone_number", "location", "linkedin_profile_url"],
                },
                {
                    "id": "screening",
                    "label": "Screening questions",
                    "common_fields": [
                        "sponsorship",
                        "years_experience",
                        "work_authorization",
                        "salary_expectation",
                    ],
                },
                {"id": "documents", "label": "Documents", "common_fields": ["resume_upload", "cover_letter_upload"]},
            ),
            "required_common": ["email", "resume_upload"],
            "disclaimer": _DISCLAIMER,
        }

    if pid == ATS_GREENHOUSE:
        return {
            "status": "schema_hints",
            "provider_id": pid,
            "job_url": url,
            "flow": "greenhouse_embedded_or_standalone",
            "typical_sections": _sections(
                {
                    "id": "personal",
                    "label": "Personal information",
                    "common_fields": ["first_name", "last_name", "email", "phone", "location"],
                },
                {
                    "id": "profile",
                    "label": "Profile / links",
                    "common_fields": ["linkedin", "portfolio", "github"],
                },
                {
                    "id": "application",
                    "label": "Application details",
                    "common_fields": ["resume", "cover_letter", "custom_questions"],
                },
                {"id": "eeo", "label": "EEO / voluntary disclosure", "common_fields": ["gender", "race", "veteran_status"]},
            ),
            "required_common": ["email", "resume"],
            "disclaimer": _DISCLAIMER,
        }

    if pid == ATS_LEVER:
        return {
            "status": "schema_hints",
            "provider_id": pid,
            "job_url": url,
            "flow": "lever_application_form",
            "typical_sections": _sections(
                {
                    "id": "basics",
                    "label": "Basic information",
                    "common_fields": ["name", "email", "phone", "location"],
                },
                {
                    "id": "urls",
                    "label": "Links",
                    "common_fields": ["linkedin", "portfolio", "github"],
                },
                {
                    "id": "role",
                    "label": "Role-specific",
                    "common_fields": ["resume", "cover_letter", "custom_fields"],
                },
            ),
            "required_common": ["email", "resume"],
            "disclaimer": _DISCLAIMER,
        }

    if pid == ATS_WORKDAY:
        return {
            "status": "schema_hints",
            "provider_id": pid,
            "job_url": url,
            "flow": "workday_multi_step",
            "typical_sections": _sections(
                {"id": "account", "label": "Account / sign-in", "common_fields": ["create_account", "sign_in"]},
                {
                    "id": "my_info",
                    "label": "My information",
                    "common_fields": ["legal_name", "address", "phone", "email"],
                },
                {
                    "id": "experience",
                    "label": "Experience & education",
                    "common_fields": ["work_history", "education", "skills"],
                },
                {
                    "id": "questions",
                    "label": "Application questions",
                    "common_fields": ["screening_questions", "attachments"],
                },
            ),
            "required_common": ["email", "resume_or_profile"],
            "disclaimer": _DISCLAIMER,
        }

    if pid == ATS_DICE:
        return {
            "status": "schema_hints",
            "provider_id": pid,
            "job_url": url,
            "flow": "dice_or_board_redirect",
            "typical_sections": _sections(
                {
                    "id": "profile",
                    "label": "Profile snapshot",
                    "common_fields": ["name", "email", "phone", "resume"],
                },
                {
                    "id": "apply",
                    "label": "Quick apply / redirect",
                    "common_fields": ["cover_note", "external_apply_link"],
                },
            ),
            "required_common": ["email", "resume"],
            "disclaimer": _DISCLAIMER,
        }

    if pid == "linkedin_other":
        return {
            "status": "schema_hints",
            "provider_id": pid,
            "job_url": url,
            "flow": "linkedin_non_jobs_page",
            "typical_sections": _sections(
                {
                    "id": "note",
                    "label": "Not a job view",
                    "common_fields": [],
                }
            ),
            "required_common": [],
            "disclaimer": "Open a linkedin.com/jobs/… URL for Easy Apply hints.",
        }

    if pid in (ATS_OTHER, ATS_UNKNOWN):
        return {
            "status": "schema_hints",
            "provider_id": pid,
            "job_url": url,
            "flow": "unknown_or_company_career_site",
            "typical_sections": _sections(
                {
                    "id": "generic",
                    "label": "Typical career portal",
                    "common_fields": [
                        "personal_info",
                        "resume",
                        "cover_letter",
                        "screening_questions",
                    ],
                }
            ),
            "required_common": ["email", "resume"],
            "disclaimer": _DISCLAIMER,
        }

    return build_form_hints(ATS_UNKNOWN, job_url)
