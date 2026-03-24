"""Structured application_locations and mailing_address on candidate profile."""

from agents.application_answerer import (
    REASON_MISSING_MAILING_ADDRESS,
    answer_question_structured,
)
from services.profile_service import (
    format_application_locations_summary,
    format_mailing_address_dict,
    format_mailing_address_oneline,
    validate_profile,
)


def test_format_application_locations_summary():
    p = {
        "application_locations": [
            {"label": "Bay", "city": "SF", "state_region": "CA", "country": "US", "remote_ok": True},
            {"city": "NYC", "state_region": "NY", "country": "US", "remote_ok": False},
        ]
    }
    s = format_application_locations_summary(p)
    assert "Bay" in s and "remote OK" in s
    assert "NYC" in s or "NY" in s


def test_format_mailing_address_dict():
    ma = {"street_line1": "2 Side", "city": "Denver", "state_region": "CO", "country": "US"}
    assert "Denver" in format_mailing_address_dict(ma)


def test_format_mailing_address_oneline():
    p = {
        "mailing_address": {
            "street_line1": "1 Main",
            "city": "Boston",
            "state_region": "MA",
            "postal_code": "02101",
            "country": "US",
        }
    }
    assert "1 Main" in format_mailing_address_oneline(p)
    assert "Boston" in format_mailing_address_oneline(p)


def test_validate_profile_location_shapes():
    w = validate_profile({"full_name": "A", "email": "a@b.co", "application_locations": "bad"})
    assert any("application_locations" in x for x in w)
    w2 = validate_profile({"full_name": "A", "email": "a@b.co", "mailing_address": []})
    assert any("mailing_address" in x for x in w2)
    w3 = validate_profile(
        {
            "full_name": "A",
            "email": "a@b.co",
            "alternate_mailing_addresses": [{"label": "x", "regions_served": "nope"}],
        }
    )
    assert any("regions_served" in x for x in w3)


def test_answerer_relocation_falls_back_to_application_locations():
    p = {
        "relocation_preference": "",
        "current_location": "",
        "application_locations": [{"label": "Remote US", "country": "US", "remote_ok": True}],
    }
    r = answer_question_structured("What is your work location preference?", profile=p)
    assert "Remote" in r["answer"] or "US" in r["answer"]
    assert r["manual_review_required"] is False


def test_answerer_mailing_address_structured():
    p = {
        "mailing_address": {
            "street_line1": "10 Oak Rd",
            "city": "Austin",
            "state_region": "TX",
            "postal_code": "73301",
            "country": "US",
        }
    }
    r = answer_question_structured("Please enter your mailing address", profile=p)
    assert "10 Oak" in r["answer"]
    assert r["manual_review_required"] is False


def test_answerer_mailing_address_empty_flags():
    r = answer_question_structured("What is your home address?", profile={})
    assert r["manual_review_required"] is True
    assert REASON_MISSING_MAILING_ADDRESS in r["reason_codes"]
