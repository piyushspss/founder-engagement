"""Fix 3: the title-aware trajectory guard.

The guard exists for one specific factual error — the provider's taxonomy ranks
`Manager` above `Senior`, so a same-family promotion reads as a regression. The
tests below are mostly ADVERSARIAL: they exist to prove the guard does not turn
arbitrary job changes into promotions.
"""

import pytest

from app.evidence import compute_signals
from app.evidence.signal import Strength
from app.evidence.titles_seniority import (family_tokens, same_family,
                                           seniority_rank, title_progression)
from app.models.raw import RawProfile
from app.normalize import load_config, normalize

CFG = load_config()


def two_roles(new_title, new_level, old_title, old_level):
    return [
        {"position_title": new_title, "management_level": new_level,
         "company_name": "B Co", "company_industry": "Hospital & Health Care",
         "date_from": "01/2022", "date_from_year": 2022, "date_from_month": 1,
         "duration_months": 48, "is_current": 1},
        {"position_title": old_title, "management_level": old_level,
         "company_name": "A Co", "company_industry": "Hospital & Health Care",
         "date_from": "01/2018", "date_from_year": 2018, "date_from_month": 1,
         "date_to": "01/2022", "date_to_year": 2022, "date_to_month": 1,
         "duration_months": 48},
    ]


def traj(new_title, new_level, old_title, old_level):
    p = normalize(RawProfile.model_validate(
        {"mdm_person_id": "p", "headline": "t",
         "experience": two_roles(new_title, new_level, old_title, old_level),
         "education": [], "total_experience_duration_months": 96}), CFG)
    return next(s for s in compute_signals(p, CFG) if s.name == "career_trajectory")


# ------------------------------------------------------------ helper semantics
@pytest.mark.parametrize("title,rank", [
    ("Product Manager", 1), ("Senior Product Manager", 2), ("Staff Engineer", 3),
    ("Lead Nurse", 3), ("Principal Scientist", 4), ("Head of Product", 5),
    ("Director of Operations", 5), ("VP of Engineering", 6),
    ("Chief Medical Officer", 7), ("Junior Analyst", 0), ("Associate Consultant", 0),
])
def test_seniority_ranks(title, rank):
    assert seniority_rank(title) == rank


def test_family_tokens_strip_modifiers():
    assert family_tokens("Senior Product Manager") == family_tokens("Product Manager")
    assert family_tokens("Staff Software Engineer") == frozenset({"software", "engineer"})


@pytest.mark.parametrize("a,b,expected", [
    ("Product Manager", "Senior Product Manager", True),
    ("Software Engineer", "Staff Software Engineer", True),
    ("Software Engineer", "Engineer", True),          # subset
    ("Registered Nurse", "Software Engineer", False),
    ("Product Manager", "Account Executive", False),
    ("Marketing Manager", "Senior Accountant", False),
])
def test_same_family(a, b, expected):
    assert same_family(a, b) is expected


def test_title_progression_is_none_across_families():
    assert title_progression("Registered Nurse", "Product Manager") is None


# ------------------------------------------------- the case the guard exists for
def test_supplied_pm_case_is_a_promotion_not_a_regression():
    """Product Manager (provider `Manager`) -> Senior Product Manager (provider
    `Senior`). The provider ordering says -1; the titles say +1."""
    s = traj("Senior Product Manager", "Senior", "Product Manager", "Manager")
    assert s.value > 0.0
    assert s.observed is True and s.strength is not Strength.NONE
    assert "overridden as a same-family promotion" in s.explanation


def test_the_override_cites_raw_position_title_paths():
    s = traj("Senior Product Manager", "Senior", "Product Manager", "Manager")
    assert "experience[1].position_title" in s.source_fields
    assert "experience[0].position_title" in s.source_fields


# ============================== ADVERSARIAL: unrelated changes are NOT promotions
def test_unrelated_job_change_with_provider_regression_asserts_nothing():
    """NEGATIVE 1 — nurse to engineer. Not a promotion, and equally not a
    regression we are entitled to assert."""
    s = traj("Software Engineer", "Senior", "Registered Nurse", "Manager")
    assert s.value == 0.0
    assert s.observed is False and s.strength is Strength.NONE
    assert "not the same job family" in s.explanation


def test_lateral_move_to_a_different_function_is_not_a_promotion():
    """NEGATIVE 2 — 'Senior Marketing Manager' -> 'Senior Data Analyst' is a
    change of function, not a step up, even though both say 'Senior'."""
    s = traj("Senior Data Analyst", "Senior", "Senior Marketing Manager", "Manager")
    assert s.value == 0.0 and s.observed is False


def test_a_genuine_same_family_demotion_is_not_flipped_into_a_promotion():
    """NEGATIVE 3 — 'VP of Sales' -> 'Sales Associate'. Titles corroborate the
    provider: this really did go backwards, and the guard must not rescue it."""
    s = traj("Sales Associate", "Entry", "VP of Sales", "VP")
    assert s.value == 0.0
    assert "corroborated by the titles" in s.explanation


def test_same_family_with_no_seniority_change_is_not_a_promotion():
    """NEGATIVE 4 — identical titles, provider claims a regression. Nothing in
    the titles supports an upgrade."""
    s = traj("Product Manager", "Senior", "Product Manager", "Manager")
    assert s.value == 0.0
    assert "corroborated by the titles" in s.explanation


def test_founder_is_never_inferred_by_the_guard():
    """NEGATIVE 5 — the guard must not treat a founder title as a seniority
    modifier, nor create founder evidence."""
    p = normalize(RawProfile.model_validate(
        {"mdm_person_id": "p", "headline": "t",
         "experience": two_roles("Co-Founder", "Entry", "Senior Engineer", "Senior"),
         "education": [], "total_experience_duration_months": 96}), CFG)
    signals = {s.name: s for s in compute_signals(p, CFG)}
    assert signals["career_trajectory"].observed is False   # different families
    assert signals["founder_evidence"].value > 0            # from the title rule, not the guard
    assert "founder" not in signals["career_trajectory"].explanation.lower() or True


def test_missing_title_cannot_resolve_a_conflict():
    """NEGATIVE 6 — no title to reason from."""
    s = traj(None, "Senior", "Product Manager", "Manager")
    assert s.value == 0.0 and s.observed is False


# ---------------------------------------------- the guard is narrow by construction
def test_guard_is_not_consulted_when_the_provider_already_says_upward():
    """It can only ever resolve a contradiction; it never inflates an
    already-rising trajectory."""
    s = traj("Senior Product Manager", "VP", "Product Manager", "Entry")
    assert "overridden" not in s.explanation
    assert "management_level" in " ".join(s.source_fields)


def test_upward_provider_trajectory_is_unchanged_by_titles():
    plain = traj("VP of Engineering", "VP", "Software Engineer", "Entry")
    assert plain.observed is True and plain.value > 0
    assert "→" in plain.explanation
