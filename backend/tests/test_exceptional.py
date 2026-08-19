"""Exceptional-detector tests — PLAN §4.2.

The bias of this file is deliberate: most of it is NEGATIVE. An exceptional
signal escalates a person to PRIORITY_REVIEW under §4.5 rule 1, so a false fire
costs a human's scarce review slot and, worse, asserts something about a person
that the data does not say. Every test below that starts `test_not_` is a claim
the system is forbidden from making.
"""

import pytest

from app.evidence import compute_signals, detect_exceptional
from app.evidence.exceptional import DETECTOR_NAMES, DETECTORS
from app.evidence.signal import SignalType, Strength
from app.models.canonical import FounderTitleFlag
from app.models.raw import RawProfile
from app.normalize import load_config, normalize

CFG = load_config()
EX = CFG.weights["exceptional"]


def role(**kw):
    base = {"position_title": "Product Manager", "company_name": "Acme Health",
            "company_industry": "Hospital & Health Care", "management_level": "Manager",
            "department": "Product",
            "company_size_range": "51-200 employees", "company_employees_count": 120,
            "date_from": "01/2018", "date_from_year": 2018, "date_from_month": 1,
            "date_to": "01/2022", "date_to_year": 2022, "date_to_month": 1,
            "duration_months": 48}
    base.update(kw)
    return base


def prof(roles=(), education=(), **kw):
    base = {"mdm_person_id": "t", "headline": "Test Person",
            "experience": list(roles), "education": list(education),
            "total_experience_duration_months": sum(r.get("duration_months") or 0
                                                    for r in roles)}
    base.update(kw)
    return normalize(RawProfile.model_validate(base), CFG)


def edu(**kw):
    base = {"degree": "Bachelor of Science", "field_of_study": "Biology",
            "institution_name": "Cobalt Ridge University",
            "date_from_year": 2008, "date_to_year": 2012}
    base.update(kw)
    return base


def fired(profile) -> dict:
    return {s.name: s for s in detect_exceptional(profile, CFG).signals}


# ===========================================================================
# A — every fired signal is evidence-backed, and shaped as the contract requires
# ===========================================================================
def test_every_fired_signal_carries_full_provenance():
    p = prof([role(position_title="Co-Founder", company_name="Northwind Bio",
                   date_from="01/2012", date_from_year=2012, date_from_month=1,
                   date_to="01/2016", date_to_year=2016, date_to_month=1),
              role(position_title="Founder", company_name="Southgate Labs",
                   date_from="02/2016", date_from_year=2016, date_from_month=2,
                   date_to=None, date_to_year=None, is_current=1)],
             [edu(degree="MD", field_of_study="Genomics")])
    ev = detect_exceptional(p, CFG)
    assert ev.signals, "expected at least one detector to fire"
    for s in ev.signals:
        assert 0.0 <= s.value <= 1.0
        assert s.strength in (Strength.MEDIUM, Strength.STRONG)
        assert s.source_fields, f"{s.name} fired with no source_fields"
        assert s.type is SignalType.DERIVED
        assert len(s.explanation) > 20
        assert s.observed is True


def test_not_fired_detectors_report_a_reason_and_no_signal():
    ev = detect_exceptional(prof([role()]), CFG)
    assert set(ev.not_fired) | {s.name for s in ev.signals} == set(DETECTOR_NAMES)
    for name, why in ev.not_fired.items():
        assert why.strip(), f"{name} declined to fire without saying why"


def test_not_empty_profile_invents_nothing():
    """Missing data is not exceptional evidence. An empty record must produce
    zero exceptional signals — never a signal justified by the gap itself."""
    ev = detect_exceptional(prof([]), CFG)
    assert ev.signals == []
    assert ev.flag is False
    assert set(ev.not_fired) == set(DETECTOR_NAMES)


@pytest.mark.parametrize("name", DETECTOR_NAMES)
def test_not_every_detector_declines_on_an_empty_profile(name):
    signal, why = DETECTORS[name](prof([]), CFG)
    assert signal is None and why


# ===========================================================================
# B — repeat founder
# ===========================================================================
def test_repeat_founder_two_explicit_founder_roles():
    p = prof([role(position_title="Co-Founder & CEO", company_name="Northwind Bio",
                   date_from="01/2012", date_from_year=2012, date_from_month=1),
              role(position_title="Founder", company_name="Southgate Labs",
                   date_from="01/2018", date_from_year=2018, date_from_month=1)])
    assert [r.founder_title_flag for r in p.roles] == [FounderTitleFlag.EXPLICIT] * 2
    s = fired(p)["repeat_founder"]
    assert s.strength is Strength.STRONG
    # raw title provenance, not a derived summary
    assert set(s.source_fields) == {"experience[0].position_title",
                                    "experience[1].position_title"}


def test_not_repeat_founder_founder_plus_ceo_only_role():
    """One founding plus a CEO job is one founding. CEO is leadership (A8)."""
    p = prof([role(position_title="Founder", company_name="Northwind Bio",
                   date_from="01/2012", date_from_year=2012, date_from_month=1),
              role(position_title="Chief Executive Officer", company_name="Bigco",
                   date_from="01/2018", date_from_year=2018, date_from_month=1)])
    # canonical roles are ordered most-recent-first, so address them by title
    by_title = {r.title: r for r in p.roles}
    assert by_title["Founder"].founder_title_flag is FounderTitleFlag.EXPLICIT
    assert by_title["Chief Executive Officer"].founder_title_flag is FounderTitleFlag.NONE
    assert by_title["Chief Executive Officer"].leadership_title is True
    assert "repeat_founder" not in fired(p)


def test_not_repeat_founder_two_ceo_roles():
    p = prof([role(position_title="CEO", company_name="Northwind Bio",
                   date_from="01/2012", date_from_year=2012, date_from_month=1),
              role(position_title="President", company_name="Southgate Labs",
                   date_from="01/2018", date_from_year=2018, date_from_month=1)])
    assert all(r.founder_title_flag is FounderTitleFlag.NONE for r in p.roles)
    ev = detect_exceptional(p, CFG)
    assert "repeat_founder" not in {s.name for s in ev.signals}
    assert "no EXPLICIT founder title" in ev.not_fired["repeat_founder"]


def test_not_repeat_founder_from_duplicated_representation_of_one_role():
    """The same founding, restated twice by the provider (identical company and
    start date, title reworded), is ONE founding."""
    p = prof([role(position_title="Founder", company_name="Northwind Bio",
                   date_from="01/2012", date_from_year=2012, date_from_month=1),
              role(position_title="Co-Founder", company_name="Northwind Bio",
                   date_from="01/2012", date_from_year=2012, date_from_month=1)])
    ev = detect_exceptional(p, CFG)
    assert "repeat_founder" not in {s.name for s in ev.signals}
    why = ev.not_fired["repeat_founder"]
    assert "1 distinct explicit founder role" in why and "collapsed" in why


def test_not_repeat_founder_from_identical_undated_rows():
    p = prof([role(position_title="Founder", company_name="Northwind Bio",
                   date_from=None, date_from_year=None, date_from_month=None,
                   date_to=None, date_to_year=None, duration_months=None),
              role(position_title="Founder", company_name="Northwind Bio",
                   date_from=None, date_from_year=None, date_from_month=None,
                   date_to=None, date_to_year=None, duration_months=None)])
    assert "repeat_founder" not in fired(p)


def test_not_repeat_founder_from_possible_titles():
    """A8: POSSIBLE is never founder evidence, so it can never be REPEAT
    founder evidence either."""
    p = prof([role(position_title="Product Manager")],
             headline="Building something new | Founder at stealth")
    ev = detect_exceptional(p, CFG)
    assert "repeat_founder" not in {s.name for s in ev.signals}


def test_repeat_founder_counts_distinct_companies_not_rows():
    p = prof([role(position_title="Founder", company_name="Northwind Bio",
                   date_from="01/2012", date_from_year=2012, date_from_month=1),
              role(position_title="Founder", company_name="Northwind Bio",
                   date_from="01/2012", date_from_year=2012, date_from_month=1),
              role(position_title="Founding Engineer", company_name="Southgate Labs",
                   date_from="01/2019", date_from_year=2019, date_from_month=1)])
    s = fired(p)["repeat_founder"]
    assert "2 distinct explicit founder roles" in s.explanation
    assert "rows collapsed" in s.explanation


# ===========================================================================
# C — exit cue: explicit text only, never inferred
# ===========================================================================
def test_exit_cue_fires_only_on_explicit_wording():
    p = prof([role(position_title="Co-Founder (acquired by Medtronic)",
                   company_name="Northwind Bio")])
    s = fired(p)["exit_cue"]
    assert s.strength is Strength.STRONG
    assert s.source_fields == ("experience[0].position_title",)


def test_not_exit_cue_from_growth_size_funding_or_role_ending():
    """None of these is an exit. Each is a fact about a company or a calendar."""
    p = prof([role(position_title="VP Product", company_name="Northwind Bio",
                   company_employees_count=4000,
                   company_employees_count_change_yearly_percentage=140.0,
                   company_last_funding_round_amount_raised=90_000_000,
                   date_to="01/2022", date_to_year=2022, date_to_month=1),
              role(position_title="Chief Product Officer", company_name="Elsewhere Inc",
                   date_from="02/2022", date_from_year=2022, date_from_month=2)])
    ev = detect_exceptional(p, CFG)
    assert "exit_cue" not in {s.name for s in ev.signals}
    assert "no configured exit keyword" in ev.not_fired["exit_cue"]


def test_not_exit_cue_from_company_disappearing_from_later_roles():
    p = prof([role(position_title="Founder", company_name="Northwind Bio",
                   date_from="01/2012", date_from_year=2012, date_from_month=1,
                   date_to="01/2016", date_to_year=2016, date_to_month=1),
              role(position_title="Director of Product", company_name="Elsewhere Inc",
                   date_from="02/2016", date_from_year=2016, date_from_month=2)])
    assert "exit_cue" not in fired(p)


@pytest.mark.parametrize("title", ["Head of Chipotle Partnerships",
                                   "Lipoprotein Research Lead"])
def test_not_exit_cue_substring_false_positive(title):
    """The configured token 'ipo' is matched on word boundaries. Substring
    matching would fire on 'Chipotle' and 'lipoprotein'."""
    assert "exit_cue" not in fired(prof([role(position_title=title)]))


# ===========================================================================
# D — exceptional progression vs ordinary promotion
# ===========================================================================
def test_not_exceptional_progression_for_an_ordinary_one_step_promotion():
    p = prof([role(position_title="Product Manager", management_level="Manager",
                   date_from="01/2016", date_from_year=2016, date_from_month=1,
                   date_to="01/2020", date_to_year=2020, date_to_month=1),
              role(position_title="Director of Product", management_level="Director",
                   date_from="02/2020", date_from_year=2020, date_from_month=2,
                   date_to=None, date_to_year=None, is_current=1)])
    ev = detect_exceptional(p, CFG)
    assert "exceptional_progression" not in {s.name for s in ev.signals}
    assert "ordinary progression is not exceptional" in ev.not_fired["exceptional_progression"]


def test_exceptional_progression_for_multi_level_jump_inside_the_window():
    p = prof([role(position_title="Product Manager", management_level="Manager",
                   date_from="01/2018", date_from_year=2018, date_from_month=1,
                   date_to="01/2021", date_to_year=2021, date_to_month=1),
              role(position_title="Chief Product Officer", management_level="C-Level",
                   date_from="02/2021", date_from_year=2021, date_from_month=2,
                   date_to=None, date_to_year=None, is_current=1)])
    s = fired(p)["exceptional_progression"]
    assert s.strength is Strength.MEDIUM
    assert "+3 levels" in s.explanation


def test_two_steps_in_under_three_years_fires():
    """CP4-R1 rule B: >=2 steps in <=3 years."""
    p = prof([role(position_title="Analyst", management_level="Specialist",
                   date_from="01/2019", date_from_year=2019, date_from_month=1,
                   date_to="06/2021", date_to_year=2021, date_to_month=6),
              role(position_title="Analytics Lead", management_level="Lead",
                   date_from="07/2021", date_from_year=2021, date_from_month=7,
                   date_to=None, date_to_year=None, is_current=1)])
    s = fired(p)["exceptional_progression"]
    assert s.strength is Strength.MEDIUM
    assert "+2 levels" in s.explanation and "2.5 years" in s.explanation


def test_the_same_two_steps_spread_over_five_years_does_not_fire():
    """The shape of the supplied RN record: Specialist → Lead over ~5.2 years.
    Two steps, but not fast. Rule A needs 3 steps, rule B needs <=3 years."""
    p = prof([role(position_title="Registered Nurse", management_level="Specialist",
                   date_from="07/2015", date_from_year=2015, date_from_month=7,
                   date_to="08/2020", date_to_year=2020, date_to_month=8),
              role(position_title="Clinical Operations Lead", management_level="Lead",
                   date_from="09/2020", date_from_year=2020, date_from_month=9,
                   date_to=None, date_to_year=None, is_current=1)])
    ev = detect_exceptional(p, CFG)
    assert "exceptional_progression" not in {s.name for s in ev.signals}
    assert "ordinary progression is not exceptional" in ev.not_fired["exceptional_progression"]


def test_three_steps_in_under_six_years_fires():
    """CP4-R1 rule A: >=3 steps in <=6 years, even though it fails rule B."""
    p = prof([role(position_title="Analyst", management_level="Specialist",
                   date_from="01/2015", date_from_year=2015, date_from_month=1,
                   date_to="01/2020", date_to_year=2020, date_to_month=1),
              role(position_title="VP Strategy", management_level="VP",
                   date_from="06/2020", date_from_year=2020, date_from_month=6,
                   date_to=None, date_to_year=None, is_current=1)])
    s = fired(p)["exceptional_progression"]
    assert "+4 levels" in s.explanation and "5.4 years" in s.explanation


def test_three_steps_spread_past_the_six_year_window_does_not_fire():
    p = prof([role(position_title="Analyst", management_level="Specialist",
                   date_from="01/2012", date_from_year=2012, date_from_month=1,
                   date_to="01/2019", date_to_year=2019, date_to_month=1),
              role(position_title="VP Strategy", management_level="VP",
                   date_from="02/2019", date_from_year=2019, date_from_month=2,
                   date_to=None, date_to_year=None, is_current=1)])
    assert "exceptional_progression" not in fired(p)


def test_not_exceptional_progression_when_the_jump_is_outside_the_window():
    """Same total climb, spread over twice the configured window."""
    p = prof([role(position_title="Product Manager", management_level="Manager",
                   date_from="01/2004", date_from_year=2004, date_from_month=1,
                   date_to="01/2019", date_to_year=2019, date_to_month=1),
              role(position_title="Chief Product Officer", management_level="C-Level",
                   date_from="02/2019", date_from_year=2019, date_from_month=2,
                   date_to=None, date_to_year=None, is_current=1)])
    assert "exceptional_progression" not in fired(p)


def test_not_exceptional_progression_without_chronology():
    p = prof([role(position_title="Product Manager", management_level="Manager",
                   date_from=None, date_from_year=None, date_from_month=None,
                   date_to=None, date_to_year=None),
              role(position_title="Chief Product Officer", management_level="C-Level",
                   date_from=None, date_from_year=None, date_from_month=None,
                   date_to=None, date_to_year=None)])
    ev = detect_exceptional(p, CFG)
    assert "exceptional_progression" not in {s.name for s in ev.signals}
    assert "chronology insufficient" in ev.not_fired["exceptional_progression"]


def test_not_exceptional_progression_without_management_levels():
    p = prof([role(position_title="Engineer", management_level=None,
                   date_from="01/2018", date_from_year=2018, date_from_month=1),
              role(position_title="Chief Technology Officer", management_level=None,
                   date_from="01/2021", date_from_year=2021, date_from_month=1)])
    assert "exceptional_progression" not in fired(p)


def test_not_exceptional_progression_when_every_pair_is_unresolvable():
    """CP3 semantics, applied per role pair: a provider-level regression across
    DIFFERENT job families is unresolvable, so it asserts nothing. Here the only
    pair is unresolvable, so the detector must stay silent — it never falls back
    to the raw provider levels CP3 declined to read."""
    p = prof([role(position_title="Chief Nursing Officer", management_level="C-Level",
                   date_from="01/2014", date_from_year=2014, date_from_month=1,
                   date_to="01/2018", date_to_year=2018, date_to_month=1),
              role(position_title="Staff Engineer", management_level="Senior",
                   date_from="02/2018", date_from_year=2018, date_from_month=2,
                   date_to=None, date_to_year=None, is_current=1)])
    traj = {s.name: s for s in compute_signals(p, CFG)}["career_trajectory"]
    assert traj.observed is False
    ev = detect_exceptional(p, CFG)
    assert "exceptional_progression" not in {s.name for s in ev.signals}
    assert "unresolvable" in ev.not_fired["exceptional_progression"]


def test_an_unresolvable_pair_does_not_silence_a_resolvable_one():
    """Documented consequence of the pair-wise scan the reviewer specified.

    The same career plus a genuine Senior → VP climb inside Engineering. The
    cross-family pairs still assert nothing; the resolvable same-family pair is
    read on its own evidence and does fire. Exceptional evidence is a claim
    about a pair of roles, not about the endpoints of the whole CV."""
    p = prof([role(position_title="Chief Nursing Officer", management_level="C-Level",
                   date_from="01/2014", date_from_year=2014, date_from_month=1,
                   date_to="01/2018", date_to_year=2018, date_to_month=1),
              role(position_title="Staff Engineer", management_level="Senior",
                   date_from="02/2018", date_from_year=2018, date_from_month=2,
                   date_to="01/2020", date_to_year=2020, date_to_month=1),
              role(position_title="VP Engineering", management_level="VP",
                   date_from="01/2020", date_from_year=2020, date_from_month=1,
                   date_to=None, date_to_year=None, is_current=1)])
    s = fired(p)["exceptional_progression"]
    assert "+3 levels" in s.explanation
    assert "1.9 years" in s.explanation


def test_inferred_start_months_cannot_manufacture_acceleration():
    """A year-only date carries up to 6 months of error. Adding that uncertainty
    to the span pushes this 2-step climb just outside the 3-year window, so our
    own inference cannot create speed the record never claimed."""
    p = prof([role(position_title="Product Manager", management_level="Manager",
                   date_from=None, date_from_year=2018, date_from_month=None,
                   date_to=None, date_to_year=2020, date_to_month=None),
              role(position_title="Head of Product", management_level="Head",
                   date_from=None, date_from_year=2021, date_from_month=None,
                   date_to=None, date_to_year=None, is_current=1)])
    assert all(r.start_date.inferred_month for r in p.roles if r.start_date)
    assert "exceptional_progression" not in fired(p)


# ===========================================================================
# E — major leadership scope
# ===========================================================================
def test_major_leadership_scope_at_large_company_without_founder_evidence():
    p = prof([role(position_title="Chief Operating Officer", management_level="C-Level",
                   company_name="Sprawlcorp Health", company_employees_count=8000,
                   company_size_range="5001-10000 employees")])
    s = fired(p)["major_leadership_scope"]
    assert s.strength is Strength.MEDIUM
    assert "does not make the person a founder" in s.explanation
    # the point of the test: leadership scope did NOT leak into founder evidence
    assert p.roles[0].founder_title_flag is FounderTitleFlag.NONE
    fe = {x.name: x for x in compute_signals(p, CFG)}["founder_evidence"]
    assert fe.strength is Strength.NONE and fe.observed is False


def test_not_major_leadership_scope_ceo_of_a_small_company():
    p = prof([role(position_title="CEO", management_level="C-Level",
                   company_name="Tinyco", company_employees_count=12,
                   company_size_range="1-10 employees")])
    ev = detect_exceptional(p, CFG)
    assert "major_leadership_scope" not in {s.name for s in ev.signals}
    assert "below the" in ev.not_fired["major_leadership_scope"]
    assert p.roles[0].founder_title_flag is FounderTitleFlag.NONE


def test_not_major_leadership_scope_when_company_size_is_missing():
    """Missing size cannot satisfy a size threshold."""
    p = prof([role(position_title="CEO", management_level="C-Level",
                   company_name="Unknownco", company_employees_count=None,
                   company_size_range=None)])
    ev = detect_exceptional(p, CFG)
    assert "major_leadership_scope" not in {s.name for s in ev.signals}
    assert "missing size cannot satisfy" in ev.not_fired["major_leadership_scope"]


def test_major_leadership_scope_uses_the_lower_bound_of_a_size_band():
    """A band's lower bound is stated by the record; a midpoint would be ours."""
    below = prof([role(position_title="VP Ops", management_level="VP",
                       company_employees_count=None,
                       company_size_range="501-1000 employees")])
    assert "major_leadership_scope" not in fired(below)
    at_or_above = prof([role(position_title="VP Ops", management_level="VP",
                             company_employees_count=None,
                             company_size_range="1001-5000 employees")])
    assert "major_leadership_scope" in fired(at_or_above)


def test_not_major_leadership_scope_for_a_junior_role_at_a_huge_company():
    p = prof([role(position_title="Analyst", management_level="Entry",
                   company_employees_count=90000, company_size_range="10001+ employees")])
    assert "major_leadership_scope" not in fired(p)


# ===========================================================================
# F — credential / rare domain
# ===========================================================================
def test_exceptional_credential_from_a_configured_degree():
    p = prof([role()], [edu(degree="Doctor of Medicine (MD)", field_of_study="Medicine")])
    s = fired(p)["exceptional_credential"]
    assert s.strength is Strength.MEDIUM
    assert s.source_fields == ("education[0].degree",)


def test_not_exceptional_from_an_elite_school_alone():
    """Prestige is not exceptional evidence. A tier-1 institution with an
    ordinary degree fires nothing, and the credential detector says out loud
    that it never consulted the tier."""
    p = prof([role()], [edu(degree="Bachelor of Arts", field_of_study="History",
                            institution_name="Harvard University")])
    ev = detect_exceptional(p, CFG)
    assert ev.signals == [] or "exceptional_credential" not in {s.name for s in ev.signals}
    assert ev.flag is False
    assert "not consulted" in ev.not_fired["exceptional_credential"]


def test_rare_domain_expertise_from_field_of_study():
    p = prof([role()], [edu(degree="MS", field_of_study="Bioinformatics")])
    s = fired(p)["rare_domain_expertise"]
    assert s.strength is Strength.MEDIUM
    assert "education[0].field_of_study" in s.source_fields


def test_not_rare_domain_expertise_for_a_general_healthcare_role():
    p = prof([role(position_title="Registered Nurse", department="Nursing")],
             [edu(degree="BSN", field_of_study="Nursing")])
    assert "rare_domain_expertise" not in fired(p)


def test_not_exceptional_from_a_long_ordinary_healthcare_career():
    """Twenty years in healthcare is depth, and the broad score already prices
    it. It is not, by itself, exceptional."""
    p = prof([role(position_title="Registered Nurse", department="Nursing",
                   management_level="Specialist", duration_months=120,
                   date_from="01/2004", date_from_year=2004, date_from_month=1,
                   date_to="01/2014", date_to_year=2014, date_to_month=1),
              role(position_title="Senior Registered Nurse", department="Nursing",
                   management_level="Senior", duration_months=132,
                   date_from="02/2014", date_from_year=2014, date_from_month=2,
                   date_to=None, date_to_year=None, is_current=1)],
             [edu(degree="BSN", field_of_study="Nursing")])
    ev = detect_exceptional(p, CFG)
    assert ev.flag is False, ev.rule


# ===========================================================================
# flag arithmetic — STRONG vs the configured MEDIUM count
# ===========================================================================
def test_flag_needs_a_strong_or_two_mediums():
    one_medium = prof([role()], [edu(degree="MD", field_of_study="Medicine")])
    ev1 = detect_exceptional(one_medium, CFG)
    assert [s.name for s in ev1.signals] == ["exceptional_credential"]
    assert ev1.flag is False and f"< {EX['medium_count']}" in ev1.rule

    two_mediums = prof([role(position_title="Chief Medical Officer",
                             management_level="C-Level", company_employees_count=6000)],
                       [edu(degree="MD", field_of_study="Medicine")])
    ev2 = detect_exceptional(two_mediums, CFG)
    assert {s.name for s in ev2.signals} == {"exceptional_credential",
                                             "major_leadership_scope"}
    assert ev2.flag is True and "MEDIUM detectors" in ev2.rule


def test_flag_from_a_single_strong_detector():
    p = prof([role(position_title="Founder", company_name="A Co",
                   date_from="01/2012", date_from_year=2012, date_from_month=1),
              role(position_title="Co-Founder", company_name="B Co",
                   date_from="01/2018", date_from_year=2018, date_from_month=1)])
    ev = detect_exceptional(p, CFG)
    assert ev.flag is True and "STRONG detector fired" in ev.rule


def test_detectors_are_pure_and_deterministic():
    p = prof([role(position_title="Founder", company_name="A Co",
                   date_from="01/2012", date_from_year=2012, date_from_month=1)],
             [edu(degree="PhD", field_of_study="Genomics")])
    before = p.model_dump(mode="json")
    a, b = detect_exceptional(p, CFG), detect_exceptional(p, CFG)
    assert a.to_dict() == b.to_dict()
    assert p.model_dump(mode="json") == before, "a detector mutated the profile"
