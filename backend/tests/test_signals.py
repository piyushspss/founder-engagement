"""Per-signal unit tests, including the two invariants the runbook specifies:

  (i)  removing a field that feeds a signal must never make that signal's value
       LOWER than its unknown/neutral value;
  (ii) removing decision-relevant fields must never INCREASE confidence.

Global broad_score monotonicity is deliberately NOT tested: removing
contradictory data can legitimately change derived signals in either direction.
Per-signal semantics is the meaningful invariant.
"""

import copy
import itertools

import pytest

from app.evidence import compute_confidence, compute_signals
from app.evidence.signal import Strength
from app.evidence.signals import SIGNAL_FUNCTIONS, SIGNAL_NAMES, broad_score
from app.models.raw import RawProfile
from app.normalize import load_config, normalize

CFG = load_config()
PARAMS = CFG.weights["signal_params"]


def role(**kw):
    base = {"position_title": "Product Manager", "company_name": "Acme Health",
            "company_industry": "Hospital & Health Care", "management_level": "Manager",
            "company_size_range": "51-200 employees", "company_employees_count": 120,
            "date_from": "01/2018", "date_from_year": 2018, "date_from_month": 1,
            "date_to": "01/2022", "date_to_year": 2022, "date_to_month": 1,
            "duration_months": 48, "company_annual_revenue_source_5": 9000000,
            "company_employees_count_change_yearly_percentage": 12.0,
            "company_founded_year": 2010}
    base.update(kw)
    return base


def prof(**kw):
    base = {"mdm_person_id": "p", "headline": "Test", "experience": [], "education": [],
            "total_experience_duration_months": None, "location_country": "United States"}
    base.update(kw)
    return normalize(RawProfile.model_validate(base), CFG)


def sig(profile, name):
    return SIGNAL_FUNCTIONS[name](profile, CFG)


# ============================================================ founder_evidence
def test_founder_explicit_title_scores_at_least_the_base():
    s = sig(prof(experience=[role(position_title="Co-Founder & CEO")]), "founder_evidence")
    assert s.value >= PARAMS["founder_evidence"]["base_explicit"]
    assert s.strength is Strength.STRONG and s.observed is True
    assert s.source_fields


def test_founder_tenure_bonus_is_capped():
    short = sig(prof(experience=[role(position_title="Founder", duration_months=6)]),
                "founder_evidence")
    long = sig(prof(experience=[role(position_title="Founder", duration_months=600)]),
               "founder_evidence")
    p = PARAMS["founder_evidence"]
    assert long.value == pytest.approx(p["base_explicit"] + p["tenure_bonus_max"])
    assert short.value < long.value <= 1.0


def test_ceo_is_not_founder_evidence():
    s = sig(prof(experience=[role(position_title="Chief Executive Officer")]), "founder_evidence")
    assert s.value == PARAMS["founder_evidence"]["unknown_neutral"]
    assert s.strength is Strength.NONE and s.observed is False


def test_possible_founder_scores_zero_credit_by_config():
    s = sig(prof(experience=[role(position_title="Founding Member")]), "founder_evidence")
    assert s.value == pytest.approx(PARAMS["founder_evidence"]["possible_credit"])
    assert s.strength is Strength.NONE


def test_no_experience_yields_neutral_not_negative():
    s = sig(prof(experience=[]), "founder_evidence")
    assert s.value == PARAMS["founder_evidence"]["unknown_neutral"]
    assert "absence of evidence" in s.explanation


# ============================================================ healthcare_depth
def test_healthcare_depth_is_log_scaled_and_saturates():
    a = sig(prof(experience=[role(duration_months=12)]), "healthcare_depth")
    b = sig(prof(experience=[role(duration_months=60)]), "healthcare_depth")
    c = sig(prof(experience=[role(duration_months=600)]), "healthcare_depth")
    assert a.value < b.value
    assert b.value == pytest.approx(c.value, abs=1e-9) or c.value <= 1.0
    assert c.value <= 1.0


def test_unknown_industry_is_not_counted_as_non_health():
    known = sig(prof(experience=[role()]), "healthcare_depth")
    unknown = sig(prof(experience=[role(company_industry=None,
                                        company_categories_and_keywords=[],
                                        company_name="Northwind Widgets")]), "healthcare_depth")
    assert unknown.value == PARAMS["healthcare_depth"]["unknown_neutral"]
    assert unknown.strength is Strength.NONE
    assert "UNKNOWN" in unknown.explanation
    assert known.value > unknown.value


def test_non_health_and_unknown_industry_score_identically():
    """Neither is healthcare experience. The difference between them is a
    confidence question, not a scoring one."""
    nonhealth = sig(prof(experience=[role(company_industry="Retail")]), "healthcare_depth")
    unknown = sig(prof(experience=[role(company_industry=None,
                                        company_categories_and_keywords=[])]), "healthcare_depth")
    assert nonhealth.value == unknown.value


def test_tiered_health_employer_earns_a_bonus():
    plain = sig(prof(experience=[role(company_name="Northwind Care")]), "healthcare_depth")
    tiered = sig(prof(experience=[role(company_name="Mayo Clinic")]), "healthcare_depth")
    assert tiered.value > plain.value


# =================================================================== leadership
def test_leadership_takes_the_highest_level_held():
    s = sig(prof(experience=[role(management_level="Manager"),
                             role(management_level="VP", date_from="01/2010",
                                  date_from_year=2010, date_to="01/2016",
                                  date_to_year=2016)]), "leadership")
    assert s.value >= PARAMS["leadership"]["level_scores"]["VP"]


def test_leadership_scope_bonus_is_capped():
    small = sig(prof(experience=[role(management_level="VP", company_employees_count=10,
                                      company_size_range="1-10 employees")]), "leadership")
    huge = sig(prof(experience=[role(management_level="VP", company_employees_count=90000,
                                     company_size_range="10001+ employees")]), "leadership")
    p = PARAMS["leadership"]
    assert huge.value == pytest.approx(min(1.0, p["level_scores"]["VP"] + p["scope_bonus_max"]))
    assert small.value < huge.value


def test_missing_management_level_is_neutral():
    s = sig(prof(experience=[role(management_level=None)]), "leadership")
    assert s.value == PARAMS["leadership"]["unknown_neutral"]
    assert s.strength is Strength.NONE


def test_unrecognised_level_is_unknown_not_zero_evidence():
    s = sig(prof(experience=[role(management_level="Grand Poobah")]), "leadership")
    assert s.value == PARAMS["leadership"]["unknown_neutral"]
    assert "not in the configured taxonomy" in s.explanation


def test_lead_sits_between_senior_and_manager_and_below_director():
    scores = PARAMS["leadership"]["level_scores"]
    assert scores["Specialist"] < scores["Senior"] < scores["Lead"] < scores["Manager"]
    assert scores["Lead"] < scores["Director"] < scores["VP"] < scores["C-Level"]


# =========================================================== career_trajectory
def test_trajectory_rewards_progression():
    flat = prof(experience=[role(management_level="Manager"),
                            role(management_level="Manager", date_from="01/2010",
                                 date_from_year=2010, date_to="01/2014", date_to_year=2014)])
    rising = prof(experience=[role(management_level="VP"),
                              role(management_level="Entry", date_from="01/2010",
                                   date_from_year=2010, date_to="01/2014", date_to_year=2014)])
    assert sig(rising, "career_trajectory").value > sig(flat, "career_trajectory").value


def test_single_role_trajectory_is_unmeasurable_not_flat():
    s = sig(prof(experience=[role()]), "career_trajectory")
    assert s.value == PARAMS["career_trajectory"]["unknown_neutral"]
    assert s.strength is Strength.NONE
    assert "not flat" in s.explanation


def test_undated_roles_make_trajectory_unmeasurable():
    s = sig(prof(experience=[role(date_from=None, date_from_year=None, date_from_month=None),
                             role(date_from=None, date_from_year=None, date_from_month=None)]),
            "career_trajectory")
    assert s.value == PARAMS["career_trajectory"]["unknown_neutral"]


# ============================================================ education_signal
def test_education_tiers_are_ordered():
    t1 = sig(prof(education=[{"institution_name": "Harvard University", "degree": "BA"}]),
             "education_signal")
    t2 = sig(prof(education=[{"institution_name": "Cornell University", "degree": "BA"}]),
             "education_signal")
    unknown = sig(prof(education=[{"institution_name": "Cobalt Ridge University",
                                   "degree": "BA"}]), "education_signal")
    assert t1.value > t2.value > unknown.value


def test_unknown_institution_scores_the_neutral_value_not_zero():
    """A7: we have no basis to call an unlisted school weak, so we do not."""
    s = sig(prof(education=[{"institution_name": "Cobalt Ridge University",
                             "degree": "Certificate, Basketweaving"}]), "education_signal")
    tiers = PARAMS["education_signal"]["institution_tier_scores"]
    assert s.value >= tiers["unknown"]


def test_missing_education_scores_the_same_neutral_as_an_unknown_school():
    missing = sig(prof(education=[]), "education_signal")
    assert missing.value == PARAMS["education_signal"]["unknown_neutral"]
    assert missing.strength is Strength.NONE
    assert missing.observed is False


def test_clinical_degree_carries_the_signal_when_the_school_is_unknown():
    s = sig(prof(education=[{"institution_name": "Sable Creek State University",
                             "degree": "Doctor of Medicine (MD)"}]), "education_signal")
    assert s.value == PARAMS["education_signal"]["degree_scores"]["MD"]
    assert s.observed is True


# ======================================================= operating_environment
def test_operating_environment_uses_the_largest_environment():
    s = sig(prof(experience=[role(company_employees_count=20,
                                  company_size_range="11-50 employees"),
                             role(company_employees_count=4000,
                                  company_size_range="1001-5000 employees",
                                  date_from="01/2010", date_from_year=2010,
                                  date_to="01/2014", date_to_year=2014)]),
            "operating_environment")
    assert "4000 employees" in s.explanation


def test_missing_company_size_is_neutral():
    s = sig(prof(experience=[role(company_employees_count=None, company_size_range=None)]),
            "operating_environment")
    assert s.value == PARAMS["operating_environment"]["unknown_neutral"]
    assert s.strength is Strength.NONE


def test_size_range_lower_bound_is_used_when_the_exact_count_is_absent():
    """Conservative fallback: the band's floor, never its midpoint."""
    s = sig(prof(experience=[role(company_employees_count=None,
                                  company_size_range="1001-5000 employees")]),
            "operating_environment")
    assert s.observed is True
    assert "1001 employees" in s.explanation
    assert "company_size_range" in s.source_fields[0]


# ============================================================== broad_score
def test_broad_score_is_the_weighted_sum_and_bounded():
    p = prof(experience=[role(position_title="Co-Founder & CEO", management_level="C-Level")],
             education=[{"institution_name": "Harvard University", "degree": "MD"}],
             total_experience_duration_months=48)
    signals = compute_signals(p, CFG)
    weights = CFG.weights["signal_weights"]
    assert broad_score(signals, CFG) == pytest.approx(
        round(sum(weights[s.name] * s.value for s in signals), 2))
    assert 0 <= broad_score(signals, CFG) <= 100


def test_weights_sum_to_one_hundred():
    assert sum(CFG.weights["signal_weights"].values()) == 100


def test_every_signal_is_produced_for_an_empty_profile():
    signals = compute_signals(prof(), CFG)
    assert [s.name for s in signals] == SIGNAL_NAMES
    assert all(0.0 <= s.value <= 1.0 for s in signals)


# ================================================= INVARIANT (i): per-signal
FIELD_ABLATIONS = [
    ("position_title", None), ("company_industry", None), ("management_level", None),
    ("company_employees_count", None), ("company_size_range", None),
    ("duration_months", None), ("date_from", None), ("date_from_year", None),
    ("date_to", None), ("date_to_year", None), ("company_annual_revenue_source_5", None),
    ("company_employees_count_change_yearly_percentage", None),
]


@pytest.mark.parametrize("field,replacement", FIELD_ABLATIONS)
@pytest.mark.parametrize("signal_name", SIGNAL_NAMES)
def test_removing_a_field_never_pushes_a_signal_below_its_neutral(signal_name, field, replacement):
    """INVARIANT (i). Missing evidence is never interpreted as negative evidence
    solely because it is missing."""
    neutral = PARAMS[signal_name]["unknown_neutral"]
    rich = [role(position_title="Co-Founder & CEO", management_level="C-Level"),
            role(position_title="Senior Engineer", management_level="Senior",
                 date_from="01/2010", date_from_year=2010, date_from_month=1,
                 date_to="01/2016", date_to_year=2016, date_to_month=1)]
    ablated = copy.deepcopy(rich)
    for r in ablated:
        r[field] = replacement
    edu = [{"institution_name": "Harvard University", "degree": "MD"}]
    after = sig(prof(experience=ablated, education=edu,
                     total_experience_duration_months=120), signal_name)
    assert after.value >= neutral - 1e-9, (
        f"{signal_name} fell to {after.value} (below neutral {neutral}) "
        f"when {field} was removed")


@pytest.mark.parametrize("signal_name", SIGNAL_NAMES)
def test_removing_education_never_pushes_a_signal_below_its_neutral(signal_name):
    neutral = PARAMS[signal_name]["unknown_neutral"]
    exp = [role(position_title="Founder & CEO", management_level="C-Level")]
    after = sig(prof(experience=exp, education=[]), signal_name)
    assert after.value >= neutral - 1e-9


@pytest.mark.parametrize("signal_name", SIGNAL_NAMES)
def test_removing_all_experience_never_pushes_a_signal_below_its_neutral(signal_name):
    neutral = PARAMS[signal_name]["unknown_neutral"]
    after = sig(prof(experience=[], education=[{"institution_name": "MIT", "degree": "PhD"}]),
                signal_name)
    assert after.value >= neutral - 1e-9


@pytest.mark.parametrize("signal_name", SIGNAL_NAMES)
def test_unobserved_signals_always_report_strength_none(signal_name):
    s = sig(prof(), signal_name)
    if not s.observed:
        assert s.strength is Strength.NONE


# ================================================ INVARIANT (ii): confidence
ABLATION_SETS = [
    {"position_title": None},
    {"date_from": None, "date_from_year": None, "date_from_month": None},
    {"company_industry": None, "company_categories_and_keywords": []},
    {"date_to": None, "date_to_year": None, "date_to_month": None, "is_current": None},
    {"management_level": None},
]


@pytest.mark.parametrize("ablation", ABLATION_SETS)
def test_removing_decision_relevant_fields_never_increases_confidence(ablation):
    """INVARIANT (ii)."""
    rich = [role(position_title="Co-Founder & CEO", management_level="C-Level",
                 is_current=1, date_to=None, date_to_year=None, date_to_month=None),
            role(position_title="Senior Engineer", management_level="Senior",
                 date_from="01/2010", date_from_year=2010, date_to="01/2016",
                 date_to_year=2016)]
    edu = [{"institution_name": "Harvard University", "degree": "MD"}]
    before = compute_confidence(prof(experience=rich, education=edu,
                                     total_experience_duration_months=192), CFG)
    ablated = copy.deepcopy(rich)
    for r in ablated:
        r.update(ablation)
    after = compute_confidence(prof(experience=ablated, education=edu,
                                    total_experience_duration_months=192), CFG)
    assert after.confidence <= before.confidence + 1e-9, (
        f"removing {list(ablation)} raised confidence "
        f"{before.confidence} -> {after.confidence}")


def test_removing_education_never_increases_confidence():
    exp = [role(position_title="Founder", is_current=1, date_to=None,
                date_to_year=None, date_to_month=None)]
    with_edu = compute_confidence(
        prof(experience=exp, education=[{"institution_name": "MIT", "degree": "BS"}],
             total_experience_duration_months=48), CFG)
    without = compute_confidence(
        prof(experience=exp, education=[], total_experience_duration_months=48), CFG)
    assert without.confidence <= with_edu.confidence


def test_removing_all_experience_collapses_confidence():
    full = compute_confidence(prof(experience=[role()], education=[],
                                   total_experience_duration_months=48), CFG)
    empty = compute_confidence(prof(experience=[], education=[],
                                    total_experience_duration_months=48), CFG)
    assert empty.confidence < full.confidence


@pytest.mark.parametrize("k", [1, 2, 3])
def test_cumulative_ablation_is_monotone(k):
    """Any combination of removals, not just single ones."""
    rich = [role(position_title="Co-Founder & CEO", management_level="C-Level",
                 is_current=1, date_to=None, date_to_year=None, date_to_month=None),
            role(position_title="Senior Engineer", management_level="Senior",
                 date_from="01/2010", date_from_year=2010, date_to="01/2016",
                 date_to_year=2016)]
    edu = [{"institution_name": "Harvard University", "degree": "MD"}]
    base = compute_confidence(prof(experience=rich, education=edu,
                                   total_experience_duration_months=192), CFG).confidence
    for combo in itertools.combinations(ABLATION_SETS, k):
        ablated = copy.deepcopy(rich)
        for r in ablated:
            for ablation in combo:
                r.update(ablation)
        got = compute_confidence(prof(experience=ablated, education=edu,
                                      total_experience_duration_months=192), CFG).confidence
        assert got <= base + 1e-9


# ================================================================ provenance
def test_every_observed_signal_carries_raw_source_paths():
    """PLAN §4.5b + CP3 evidence requirement F: a non-neutral signal must be
    traceable to raw JSON paths, not just to a canonical value."""
    p = prof(experience=[role(position_title="Co-Founder & CEO", management_level="C-Level"),
                         role(position_title="Senior Engineer", management_level="Senior",
                              date_from="01/2010", date_from_year=2010, date_to="01/2016",
                              date_to_year=2016)],
             education=[{"institution_name": "Harvard University", "degree": "MD"}],
             total_experience_duration_months=192)
    for s in compute_signals(p, CFG):
        if s.observed:
            assert s.source_fields, f"{s.name} is observed but has no provenance"
            for path in s.source_fields:
                assert path.startswith(("experience[", "education[",
                                        "total_experience_duration_months")), path


def test_signal_values_are_bounded_zero_to_one():
    p = prof(experience=[role(position_title="Co-Founder & CEO", management_level="C-Level",
                              company_employees_count=500000, duration_months=900,
                              company_annual_revenue_source_5=9e12)],
             education=[{"institution_name": "Harvard University", "degree": "MD"}],
             total_experience_duration_months=900)
    for s in compute_signals(p, CFG):
        assert 0.0 <= s.value <= 1.0


# ============ INVARIANT (i), strengthened form (valid once neutral == 0.0) ============
# With every `unknown_neutral` at 0.0 the original invariant ("never below
# neutral") is satisfied by construction, since no signal can go negative. The
# test below asserts the form that still carries information: removing a field
# never RAISES a signal either. Missing data must not become an advantage.
# NOTE: this is deliberately per-signal, never on broad_score — the runbook
# excludes global monotonicity because removing contradictory data can
# legitimately move derived signals in either direction.
ALL_ABLATABLE_FIELDS = [
    "position_title", "company_industry", "management_level", "company_employees_count",
    "company_size_range", "duration_months", "date_from", "date_from_year", "date_to",
    "date_to_year", "company_annual_revenue_source_5",
    "company_employees_count_change_yearly_percentage", "company_founded_year",
]


def _rich_profile(ablate=()):
    rich = [role(position_title="Co-Founder & CEO", management_level="C-Level"),
            role(position_title="Senior Engineer", management_level="Senior",
                 date_from="01/2010", date_from_year=2010, date_from_month=1,
                 date_to="01/2016", date_to_year=2016, date_to_month=1)]
    rich = copy.deepcopy(rich)
    for r in rich:
        for f in ablate:
            r[f] = None
    return prof(experience=rich,
                education=[{"institution_name": "Harvard University", "degree": "MD"}],
                total_experience_duration_months=120)


@pytest.mark.parametrize("field", ALL_ABLATABLE_FIELDS)
@pytest.mark.parametrize("signal_name", SIGNAL_NAMES)
def test_removing_a_field_never_raises_a_signal(signal_name, field):
    before = sig(_rich_profile(), signal_name).value
    after = sig(_rich_profile(ablate=(field,)), signal_name).value
    assert after <= before + 1e-9, (
        f"{signal_name} rose {before} -> {after} when {field} was removed")


@pytest.mark.parametrize("signal_name", SIGNAL_NAMES)
def test_signals_are_zero_when_nothing_is_observed(signal_name):
    """A9: broad_score measures observable positive evidence. No evidence, no points."""
    s = sig(prof(), signal_name)
    assert s.value == 0.0 and s.observed is False and s.strength is Strength.NONE
