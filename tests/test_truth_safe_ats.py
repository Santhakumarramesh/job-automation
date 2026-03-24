"""Truth-safe internal ATS ceiling helper."""

from services.truth_safe_ats import compute_truth_safe_ats_ceiling


def test_ceiling_when_truth_safe_off():
    c = compute_truth_safe_ats_ceiling(72, truth_safe=False, target_score=95)
    assert c["truth_safe_ats_ceiling"] == 95
    assert "off" in c["truth_safe_ceiling_reason"].lower()


def test_ceiling_with_unsupported_caps_at_current():
    c = compute_truth_safe_ats_ceiling(
        80,
        truth_safe=True,
        unsupported_requirements=["TS/SCI clearance"],
    )
    assert c["truth_safe_ats_ceiling"] == 80
    assert "unsupported" in c["truth_safe_ceiling_reason"].lower()
    assert "unsupported_requirements" in c["ceiling_limited_by"]


def test_ceiling_converged():
    c = compute_truth_safe_ats_ceiling(
        92,
        truth_safe=True,
        converged=True,
        target_score=90,
    )
    assert c["truth_safe_ats_ceiling"] == 92


def test_ceiling_no_truthful_headroom():
    c = compute_truth_safe_ats_ceiling(
        78,
        truth_safe=True,
        no_truthful_improvement=True,
        truthful_missing_keywords=[],
    )
    assert c["truth_safe_ats_ceiling"] == 78
    assert "truth_inventory" in c["ceiling_limited_by"]


def test_ceiling_max_attempts_with_truthful_left():
    c = compute_truth_safe_ats_ceiling(
        70,
        truth_safe=True,
        stopped_after_max_attempts=True,
        truthful_missing_keywords=["Python", "AWS"],
        target_score=100,
    )
    assert c["truth_safe_ats_ceiling"] > 70
    assert c["truth_safe_ats_ceiling"] <= 100
    assert "optimizer" in c["truth_safe_ceiling_reason"].lower() or "attempts" in c["truth_safe_ceiling_reason"].lower()
