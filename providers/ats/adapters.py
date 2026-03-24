"""Concrete ATS adapters (v1 stubs + LinkedIn auto lane flag)."""

from __future__ import annotations

from typing import Any, Dict

from providers.ats.form_hints import build_form_hints
from providers.job_source import (
    ATS_DICE,
    ATS_GREENHOUSE,
    ATS_LEVER,
    ATS_LINKEDIN_JOBS,
    ATS_OTHER,
    ATS_UNKNOWN,
    ATS_WORKDAY,
)


class _BaseAdapter:
    provider_id: str = ATS_OTHER

    def supports_auto_apply_v1(self) -> bool:
        return False

    def analyze_form(self, job_url: str) -> Dict[str, Any]:
        return build_form_hints(self.provider_id, job_url)

    def manual_assist_capabilities(self) -> list[str]:
        return [
            "prepare_application_package",
            "get_autofill_values",
            "review_unmapped_fields",
            "dry_run_apply_to_jobs",
            "application_audit_report",
        ]


class LinkedInJobsAdapter(_BaseAdapter):
    provider_id = ATS_LINKEDIN_JOBS

    def supports_auto_apply_v1(self) -> bool:
        return True


class GreenhouseAdapter(_BaseAdapter):
    provider_id = ATS_GREENHOUSE


class LeverAdapter(_BaseAdapter):
    provider_id = ATS_LEVER


class WorkdayAdapter(_BaseAdapter):
    provider_id = ATS_WORKDAY


class DiceAdapter(_BaseAdapter):
    provider_id = ATS_DICE


class LinkedInOtherAdapter(_BaseAdapter):
    provider_id = "linkedin_other"


class GenericAdapter(_BaseAdapter):
    provider_id = ATS_OTHER


class UnknownAdapter(_BaseAdapter):
    provider_id = ATS_UNKNOWN


ADAPTER_BY_LABEL: Dict[str, type] = {
    ATS_LINKEDIN_JOBS: LinkedInJobsAdapter,
    ATS_GREENHOUSE: GreenhouseAdapter,
    ATS_LEVER: LeverAdapter,
    ATS_WORKDAY: WorkdayAdapter,
    ATS_DICE: DiceAdapter,
    "linkedin_other": LinkedInOtherAdapter,
    ATS_OTHER: GenericAdapter,
    ATS_UNKNOWN: UnknownAdapter,
}
