"""ATS provider adapters (v1 stubs) — see ``registry.describe_ats_platform``."""

from providers.ats.registry import (
    describe_ats_platform,
    get_ats_adapter_for_job,
    get_ats_adapter_for_label,
)

__all__ = [
    "describe_ats_platform",
    "get_ats_adapter_for_job",
    "get_ats_adapter_for_label",
]
