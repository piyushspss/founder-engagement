"""Canonical progression semantics — CP4-R2 and CP4-R3.

Two properties this file exists to defend:

* the broad `career_trajectory` signal and the `exceptional_progression`
  detector must never disagree about which way a career went. Before the
  refactor each read the provider's `management_level` for itself, and on the
  supplied PM record the broad signal said "+1 same-family promotion" while the
  detector said "-1 regression" — about the same two rows.
* "how many steps is it" and "is A more senior than B" are different questions
  with different ladders, and the coarse step ladder must never be used to
  answer the second one.
"""

import pytest

from app.evidence import compute_signals, detect_exceptional
from app.evidence.progression import (LEVEL_RANK, PROVIDER, TITLE_OVERRIDE,
                                      UNRESOLVED, at_least, management_order,
                                      resolve_progression)
from app.models.raw import RawProfile, load_profiles
from app.normalize import load_config, normalize

CFG = load_config()
ORDER = management_order(CFG)

SAMPLES = [normalize(r, CFG) for r in load_profiles("data/raw/sample.json")]
PM, RN = SAMPLES[0], SAMPLES[1]


def role(**kw):
    base = {"position_title": "Product Manager", "company_name": "Acme Health",
            "company_industry": "Hospital & Health Care", "management_level": "Manager",
            "department": "Product", "company_employees_count": 120,
            "date_from": "01/2018", "date_from_year": 2018, "date_from_month": 1,
            "date_to": "01/2022", "date_to_year": 2022, "date_to_month": 1,
            "duration_months": 48}
    base.update(kw)
    return base


def prof(roles=(), **kw):
    base = {"mdm_person_id": "t", "headline": "Test", "experience": list(roles),
            "education": [], "total_experience_duration_months": None}
    base.update(kw)
    return normalize(RawProfile.model_validate(base), CFG)


def chrono(p):
    """Roles oldest-first (canonical order is most-recent-first)."""
    return sorted([r for r in p.roles if r.start_date], key=lambda r: r.start_date.index)


# ===========================================================================
# CP4-R2 — one resolution, consumed by both paths
# ===========================================================================
def test_supplied_pm_profile_resolves_as_a_same_family_promotion():
    """Provider levels say Manager → Senior (a regression). The titles say
    Product Manager → Senior Product Manager. CP3 resolves it as +1."""
    first, last = chrono(PM)
    res = resolve_progression(first, last)
    assert res.provider_steps == -1
    assert res.steps == 1
    assert res.basis == TITLE_OVERRIDE
    assert set(res.source_fields) == {"experience[0].position_title",
                                      "experience[1].position_title"}


def test_both_paths_see_the_same_progression_on_the_pm_profile():
    """The broad signal reports positive trajectory; the detector reads the same
    +1 and simply finds it far short of the exceptional rule. Neither sees -1."""
    traj = {s.name: s for s in compute_signals(PM, CFG)}["career_trajectory"]
    assert traj.observed is True and traj.value > 0
    ev = detect_exceptional(PM, CFG)
    assert "exceptional_progression" not in {s.name for s in ev.signals}
    assert "CP3-resolved progression" in ev.not_fired["exceptional_progression"]


@pytest.mark.parametrize("profile", SAMPLES + [
    prof([role(management_level="Specialist", position_title="Analyst",
               date_from="01/2015", date_from_year=2015, date_from_month=1),
          role(management_level="VP", position_title="VP Strategy",
               date_from="01/2019", date_from_year=2019, date_from_month=1)]),
    prof([role(management_level="C-Level", position_title="Chief Nursing Officer",
               date_from="01/2014", date_from_year=2014, date_from_month=1),
          role(management_level="Senior", position_title="Staff Engineer",
               date_from="01/2018", date_from_year=2018, date_from_month=1)]),
])
def test_the_two_paths_agree_on_direction(profile):
    """Whatever the broad signal concludes about direction, the shared resolver
    must agree — including agreeing that nothing can be concluded."""
    dated = [r for r in chrono(profile) if r.management_level in LEVEL_RANK]
    if len(dated) < 2:
        pytest.skip("no measurable progression in this profile")
    res = resolve_progression(dated[0], dated[-1])
    traj = {s.name: s for s in compute_signals(profile, CFG)}["career_trajectory"]

    if not res.resolved:
        assert traj.observed is False, "signal asserted a trajectory the resolver would not"
        return
    assert traj.observed is True
    # sign agreement: positive steps <=> positive signal value
    assert (res.steps > 0) == (traj.value > 0)


def test_load_population_paths_never_disagree():
    """Same property, swept across the whole synthetic population."""
    profiles = [normalize(r, CFG) for r in
                load_profiles("data/synthetic/load_800.json")]
    checked = 0
    for p in profiles:
        dated = [r for r in chrono(p) if r.management_level in LEVEL_RANK]
        if len(dated) < 2 or dated[0].start_date.index == dated[-1].start_date.index:
            continue
        res = resolve_progression(dated[0], dated[-1])
        traj = {s.name: s for s in compute_signals(p, CFG)}["career_trajectory"]
        assert traj.observed == res.resolved
        if res.resolved:
            assert (res.steps > 0) == (traj.value > 0)
        checked += 1
    assert checked > 100, f"only {checked} profiles exercised the property"


def test_unresolvable_conflict_asserts_nothing_not_a_regression():
    a = prof([role(management_level="C-Level", position_title="Chief Nursing Officer",
                   date_from="01/2014", date_from_year=2014, date_from_month=1),
              role(management_level="Senior", position_title="Staff Engineer",
                   date_from="01/2018", date_from_year=2018, date_from_month=1)])
    first, last = chrono(a)
    res = resolve_progression(first, last)
    assert res.steps is None and res.basis == UNRESOLVED
    assert res.provider_steps == -4      # what we declined to assert
    assert "No progression asserted" in res.explanation


def test_upward_provider_levels_are_never_second_guessed_by_titles():
    """The title guard is only consulted on a reported regression. It can never
    inflate an already-upward trajectory."""
    a = prof([role(management_level="Specialist", position_title="Senior Analyst",
                   date_from="01/2015", date_from_year=2015, date_from_month=1),
              role(management_level="VP", position_title="VP", date_from="01/2019",
                   date_from_year=2019, date_from_month=1)])
    first, last = chrono(a)
    res = resolve_progression(first, last)
    assert res.basis == PROVIDER
    assert res.steps == res.provider_steps == LEVEL_RANK["VP"] - LEVEL_RANK["Specialist"]


# ===========================================================================
# CP4-R3 — one canonical ordering for "at least" gates
# ===========================================================================
def test_lead_is_below_manager_on_the_canonical_ordering():
    assert ORDER["Lead"] < ORDER["Manager"]
    assert at_least("Manager", "Manager", CFG) is True
    assert at_least("Lead", "Manager", CFG) is False
    assert at_least("Director", "Manager", CFG) is True


def test_unknown_or_missing_level_never_satisfies_a_seniority_gate():
    assert at_least(None, "Manager", CFG) is False
    assert at_least("Grand Poobah", "Manager", CFG) is False


def test_the_step_ladder_never_inverts_the_canonical_ordering():
    """The coarse step ladder is allowed to TIE two levels the canonical
    ordering separates (it measures distance, not standing), but it must never
    put them in the opposite order. That would be two contradictory taxonomies."""
    shared = [lv for lv in LEVEL_RANK if lv in ORDER]
    for a in shared:
        for b in shared:
            if ORDER[a] < ORDER[b]:
                assert LEVEL_RANK[a] <= LEVEL_RANK[b], (
                    f"step ladder inverts {a} vs {b} relative to level_scores")


def test_every_level_in_one_ladder_is_known_to_the_other():
    assert set(LEVEL_RANK) == set(ORDER), "the two ladders cover different vocabularies"
