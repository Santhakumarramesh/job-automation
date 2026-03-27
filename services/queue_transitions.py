"""
Phase 6 — Queue transitions and recommended actions.
Centralizes how queue states advance as fit + package data arrive.
"""

from __future__ import annotations

from typing import Optional


class JobQueueState:
    SKIP = "skip"
    REVIEW_FIT = "review_fit"
    REVIEW_RESUME = "review_resume"
    READY_FOR_APPROVAL = "ready_for_approval"
    APPROVED_FOR_APPLY = "approved_for_apply"
    APPLYING = "applying"
    APPLIED = "applied"
    BLOCKED = "blocked"


class PackageState:
    NOT_GENERATED = "not_generated"
    GENERATED = "generated"
    OPTIMIZED_TRUTH_SAFE = "optimized_truth_safe"
    APPROVED = "approved"
    UPLOADED = "uploaded"


def determine_initial_state(
    *,
    fit_decision: str,
    overall_fit_score: int,
    hard_blockers: list[str] | None = None,
) -> str:
    if hard_blockers:
        return JobQueueState.SKIP
    decision = str(fit_decision or "").strip().lower()
    if decision == "apply" and overall_fit_score >= 65:
        return JobQueueState.REVIEW_FIT
    if decision in ("review_fit", "apply"):
        return JobQueueState.REVIEW_FIT
    return JobQueueState.SKIP


def determine_state_after_package(
    *,
    current_state: str,
    fit_decision: str,
    overall_fit_score: int,
    package_status: str,
    hard_blockers: list[str] | None = None,
    unsupported_requirements: list[str] | None = None,
) -> str:
    if current_state in (
        JobQueueState.SKIP,
        JobQueueState.BLOCKED,
        JobQueueState.APPROVED_FOR_APPLY,
        JobQueueState.APPLYING,
        JobQueueState.APPLIED,
    ):
        return current_state

    if hard_blockers:
        return JobQueueState.SKIP

    decision = str(fit_decision or "").strip().lower()
    status = str(package_status or "").strip().lower()

    if status not in (PackageState.GENERATED, PackageState.OPTIMIZED_TRUTH_SAFE, PackageState.APPROVED):
        return current_state

    if decision != "apply":
        return JobQueueState.REVIEW_FIT

    if (unsupported_requirements or []) and overall_fit_score < 75:
        return JobQueueState.REVIEW_RESUME

    return JobQueueState.READY_FOR_APPROVAL


def recommended_action(
    *,
    job_state: str,
    package_status: str,
) -> str:
    state = str(job_state or "").strip().lower()
    pkg = str(package_status or "").strip().lower()

    if state == JobQueueState.SKIP:
        return "skip"
    if state == JobQueueState.BLOCKED:
        return "blocked"
    if state == JobQueueState.APPROVED_FOR_APPLY:
        return "ready_for_apply"
    if state == JobQueueState.APPLYING:
        return "applying"
    if state == JobQueueState.APPLIED:
        return "applied"
    if state == JobQueueState.READY_FOR_APPROVAL:
        return "approve_for_apply"
    if state == JobQueueState.REVIEW_RESUME:
        return "review_resume"
    if state == JobQueueState.REVIEW_FIT:
        if pkg in (PackageState.NOT_GENERATED, "", None):
            return "generate_package"
        return "review_resume"
    return "review_fit"
