"""Optional POLICY_ENFORCE_JOB_LOCATION gate."""

import os

import pytest

from services.job_location_match import (
    REASON_MANUAL_JOB_LOCATION_UNKNOWN,
    REASON_SKIP_JOB_LOCATION,
    check_job_location_policy,
    haystack_matches_region,
    job_is_remoteish,
    job_location_haystack,
)
from services.policy_service import decide_apply_mode_with_reason, REASON_AUTO_OK


@pytest.fixture
def clear_loc_policy(monkeypatch):
    monkeypatch.delenv("POLICY_ENFORCE_JOB_LOCATION", raising=False)


def test_job_location_haystack_and_remote():
    j = {"location": "US", "title": "Engineer", "work_type": "remote"}
    assert "remote" in job_location_haystack(j)
    assert job_is_remoteish(j) is True


def test_haystack_matches_region():
    hay = "senior engineer new york ny hybrid"
    assert haystack_matches_region(hay, "New York") is True
    assert haystack_matches_region(hay, "Paris") is False


def test_enforce_off_always_ok(monkeypatch, clear_loc_policy):
    monkeypatch.delenv("POLICY_ENFORCE_JOB_LOCATION", raising=False)
    profile = {"application_locations": [{"city": "NYC"}]}
    a, r = check_job_location_policy({"location": "London, UK"}, profile)
    assert a == "ok" and r == ""


def test_enforce_on_no_profile_locs_ok(monkeypatch):
    monkeypatch.setenv("POLICY_ENFORCE_JOB_LOCATION", "1")
    a, r = check_job_location_policy({"location": "Paris"}, {"full_name": "x"})
    assert a == "ok"


def test_enforce_match_city(monkeypatch):
    monkeypatch.setenv("POLICY_ENFORCE_JOB_LOCATION", "1")
    profile = {"application_locations": [{"city": "Austin", "state_region": "TX", "country": "US"}]}
    a, r = check_job_location_policy({"location": "Austin, TX — on-site"}, profile)
    assert a == "ok"


def test_enforce_mismatch_skip(monkeypatch):
    monkeypatch.setenv("POLICY_ENFORCE_JOB_LOCATION", "1")
    profile = {"application_locations": [{"city": "Boston", "state_region": "MA"}]}
    a, r = check_job_location_policy({"location": "Seattle, WA"}, profile)
    assert a == "skip" and r == REASON_SKIP_JOB_LOCATION


def test_enforce_remote_requires_remote_ok(monkeypatch):
    monkeypatch.setenv("POLICY_ENFORCE_JOB_LOCATION", "1")
    profile = {"application_locations": [{"city": "NYC", "remote_ok": False}]}
    a, r = check_job_location_policy(
        {"location": "United States", "title": "Engineer", "work_type": "remote", "description": "remote ok"},
        profile,
    )
    assert a == "skip" and r == REASON_SKIP_JOB_LOCATION

    profile2 = {"application_locations": [{"city": "NYC", "remote_ok": True}]}
    a2, r2 = check_job_location_policy(
        {"location": "US", "title": "Engineer", "work_type": "remote"},
        profile2,
    )
    assert a2 == "ok"


def test_enforce_empty_haystack_manual(monkeypatch):
    monkeypatch.setenv("POLICY_ENFORCE_JOB_LOCATION", "1")
    profile = {"application_locations": [{"city": "Denver"}]}
    a, r = check_job_location_policy({"url": "x"}, profile)
    assert a == "manual_assist" and r == REASON_MANUAL_JOB_LOCATION_UNKNOWN


def test_decide_apply_mode_with_reason_location_skip(monkeypatch):
    monkeypatch.setenv("POLICY_ENFORCE_JOB_LOCATION", "1")
    job = {
        "url": "https://linkedin.com/jobs/view/1",
        "easy_apply_confirmed": True,
        "location": "Berlin, Germany",
    }
    profile = {"application_locations": [{"city": "Chicago", "state_region": "IL"}]}
    m, reason = decide_apply_mode_with_reason(
        job,
        fit_decision="apply",
        ats_score=95,
        unsupported_requirements=[],
        profile_ready=True,
        profile=profile,
    )
    assert m == "skip"
    assert reason == REASON_SKIP_JOB_LOCATION


def test_decide_apply_mode_with_reason_location_ok(monkeypatch):
    monkeypatch.setenv("POLICY_ENFORCE_JOB_LOCATION", "1")
    job = {
        "url": "https://linkedin.com/jobs/view/1",
        "easy_apply_confirmed": True,
        "location": "Chicago, IL",
    }
    profile = {"application_locations": [{"city": "Chicago"}]}
    m, reason = decide_apply_mode_with_reason(
        job,
        fit_decision="apply",
        ats_score=95,
        unsupported_requirements=[],
        profile_ready=True,
        profile=profile,
    )
    assert m == "auto_easy_apply" and reason == REASON_AUTO_OK
