"""A9 semantics: broad_score is the strength of currently OBSERVABLE POSITIVE
evidence. Unknown or missing evidence contributes exactly zero — never positive
points for being unknown, and never negative points either.
"""

import pytest

from app.evidence import compute_signals
from app.evidence.signal import Strength
from app.evidence.signals import SIGNAL_NAMES, broad_score
from app.models.raw import RawProfile
from app.normalize import load_config, normalize

CFG = load_config()
PARAMS = CFG.weights["signal_params"]


def prof(**kw):
    base = {"mdm_person_id": "p", "headline": None, "experience": [], "education": [],
            "total_experience_duration_months": None}
    base.update(kw)
    return normalize(RawProfile.model_validate(base), CFG)


@pytest.mark.parametrize("name", SIGNAL_NAMES)
def test_every_unknown_neutral_is_zero(name):
    """The config-level statement of the rule."""
    assert PARAMS[name]["unknown_neutral"] == 0.0


def test_unknown_institution_tier_contributes_nothing():
    assert PARAMS["education_signal"]["institution_tier_scores"]["unknown"] == 0.0


def test_unrecognised_degree_contributes_nothing():
    assert PARAMS["education_signal"]["degree_scores"]["OTHER"] == 0.0


def test_a_profile_with_no_evidence_scores_zero():
    """The headline case: no experience, no education, no totals -> 0.0, not 11.5."""
    p = prof()
    signals = compute_signals(p, CFG)
    assert broad_score(signals, CFG) == 0.0
    assert all(s.value == 0.0 for s in signals)
    assert all(s.strength is Strength.NONE for s in signals)
    assert all(s.observed is False for s in signals)


def test_unknown_school_with_unknown_degree_contributes_nothing():
    s = compute_signals(prof(education=[{"institution_name": "Cobalt Ridge University",
                                         "degree": "Certificate, Basketweaving"}]), CFG)[4]
    assert s.value == 0.0 and s.observed is False and s.strength is Strength.NONE


def test_unknown_school_with_a_known_degree_still_earns_the_degree():
    """The school contributes nothing; the credential still counts."""
    s = compute_signals(prof(education=[{"institution_name": "Cobalt Ridge University",
                                         "degree": "Doctor of Medicine (MD)"}]), CFG)[4]
    assert s.value == PARAMS["education_signal"]["degree_scores"]["MD"]
    assert s.observed is True


def test_missing_education_and_unknown_school_score_identically():
    missing = compute_signals(prof(education=[]), CFG)[4]
    unknown = compute_signals(prof(education=[{"institution_name": "Cobalt Ridge University",
                                               "degree": "Certificate, X"}]), CFG)[4]
    assert missing.value == unknown.value == 0.0


def test_tiered_institutions_still_contribute():
    t1 = compute_signals(prof(education=[{"institution_name": "Harvard University",
                                          "degree": "BA, History"}]), CFG)[4]
    t2 = compute_signals(prof(education=[{"institution_name": "Cornell University",
                                          "degree": "BA, History"}]), CFG)[4]
    tiers = PARAMS["education_signal"]["institution_tier_scores"]
    assert t1.value == tiers["tier_1"] and t2.value == tiers["tier_2"]


def test_missing_is_not_negative_no_signal_can_go_below_zero():
    for name in SIGNAL_NAMES:
        for p in (prof(), prof(experience=[{"position_title": None}]),
                  prof(education=[{}]), prof(experience=[{}], education=[{}])):
            s = next(x for x in compute_signals(p, CFG) if x.name == name)
            assert s.value >= 0.0


def test_broad_score_is_still_the_frozen_weighted_sum():
    """No renormalisation over observed signals — PLAN §4.1 is unchanged."""
    p = prof(experience=[{"position_title": "Founder & CEO", "management_level": "C-Level",
                          "company_industry": "Hospital & Health Care",
                          "date_from_year": 2018, "date_from_month": 1,
                          "duration_months": 60, "company_employees_count": 200,
                          "company_size_range": "51-200 employees"}],
             education=[{"institution_name": "Harvard University", "degree": "MD"}],
             total_experience_duration_months=60)
    signals = compute_signals(p, CFG)
    w = CFG.weights["signal_weights"]
    assert broad_score(signals, CFG) == pytest.approx(
        round(sum(w[s.name] * s.value for s in signals), 2))


def test_thresholds_were_not_touched():
    t = CFG.thresholds
    assert (t["priority_broad"], t["priority_confidence"],
            t["low_confidence_floor_broad"], t["routine_broad"]) == (65, 0.6, 30, 40)


def test_signal_weights_were_not_touched():
    assert CFG.weights["signal_weights"] == {
        "founder_evidence": 25, "healthcare_depth": 20, "leadership": 15,
        "career_trajectory": 15, "education_signal": 10,
        "operating_environment": 10, "other": 5}
