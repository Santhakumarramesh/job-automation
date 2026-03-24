"""Address selection by job location (default vs alternate_mailing_addresses)."""

from services.address_for_job import get_address_for_job


def test_remote_uses_default():
    profile = {
        "mailing_address": {"street_line1": "1 SF", "city": "San Francisco", "state_region": "CA", "country": "US"},
        "alternate_mailing_addresses": [
            {
                "label": "NYC",
                "regions_served": ["New York"],
                "mailing_address": {"street_line1": "9 NY", "city": "New York", "state_region": "NY", "country": "US"},
            }
        ],
    }
    job = {"location": "Anywhere", "work_type": "remote", "title": "Engineer"}
    r = get_address_for_job(job, profile)
    assert r["used_alternate"] is False
    assert r["mailing_address"]["city"] == "San Francisco"
    assert "remote" in r["selection_reason"].lower()


def test_alternate_matches_region():
    profile = {
        "mailing_address": {"street_line1": "1 SF", "city": "San Francisco", "state_region": "CA", "country": "US"},
        "alternate_mailing_addresses": [
            {
                "label": "NYC apartment",
                "regions_served": ["Manhattan", "NYC", "New York"],
                "mailing_address": {
                    "street_line1": "500 E",
                    "city": "New York",
                    "state_region": "NY",
                    "postal_code": "10001",
                    "country": "US",
                },
            }
        ],
    }
    job = {"location": "New York, NY (on-site)", "title": "Data Scientist", "work_type": "on_site"}
    r = get_address_for_job(job, profile)
    assert r["used_alternate"] is True
    assert r["address_label"] == "NYC apartment"
    assert r["mailing_address"]["city"] == "New York"
    assert "500 E" in r["mailing_address_oneline"]


def test_no_match_falls_back_to_default():
    profile = {
        "mailing_address": {"street_line1": "1 Austin", "city": "Austin", "state_region": "TX", "country": "US"},
        "alternate_mailing_addresses": [
            {
                "label": "Boston",
                "regions_served": ["Boston", "MA"],
                "mailing_address": {"street_line1": "2 B", "city": "Boston", "state_region": "MA", "country": "US"},
            }
        ],
    }
    job = {"location": "Seattle, WA", "title": "Eng"}
    r = get_address_for_job(job, profile)
    assert r["used_alternate"] is False
    assert r["mailing_address"]["city"] == "Austin"
