"""Archetype labeller tests — PLAN §4.4.

The single most important property in this file is the LAST section: assigning,
changing or removing an archetype must not move any number. An archetype is a
frame for a human conversation, not an input to the machine's judgment. If a
label could nudge a score, the label would quietly become a second rubric.
"""

import pytest

from app.evidence import (broad_score, compute_confidence, compute_signals,
                          detect_exceptional, label_archetype)
from app.models.raw import RawProfile, load_profiles
from app.normalize import load_config, normalize

CFG = load_config()
ACFG = CFG.archetypes
CONFIGURED_NAMES = [a["name"] for a in ACFG["archetypes"]]


def role(**kw):
    base = {"position_title": "Product Manager", "company_name": "Acme Health",
            "company_industry": "Hospital & Health Care", "management_level": "Manager",
            "department": "Product", "company_employees_count": 120,
            "date_from": "01/2018", "date_from_year": 2018, "date_from_month": 1,
            "date_to": "01/2022", "date_to_year": 2022, "date_to_month": 1,
            "duration_months": 48}
    base.update(kw)
    return base


def edu(**kw):
    base = {"degree": "Bachelor of Science", "field_of_study": "Biology",
            "institution_name": "Cobalt Ridge University",
            "date_from_year": 2008, "date_to_year": 2012}
    base.update(kw)
    return base


def prof(roles=(), education=(), **kw):
    base = {"mdm_person_id": "t", "headline": "Test Person",
            "experience": list(roles), "education": list(education),
            "total_experience_duration_months": sum(r.get("duration_months") or 0
                                                    for r in roles)}
    base.update(kw)
    return normalize(RawProfile.model_validate(base), CFG)


def label(p):
    ev = detect_exceptional(p, CFG)
    return label_archetype(p, compute_signals(p, CFG), CFG, ev.flag)


SAMPLES = {c.person_id: c for c in
           (normalize(r, CFG) for r in load_profiles("data/raw/sample.json"))}
PM = SAMPLES["00000000-0000-0000-0000-000000000001"]
RN = SAMPLES["00000000-0000-0000-0000-000000000002"]


# ===========================================================================
# rule-based assignment
# ===========================================================================
def test_product_builder_from_department():
    r = label(PM)
    assert r.archetype == "Product Builder"
    assert "Product" in r.explanation
    assert "founder_evidence" in r.missing_for_archetype


def test_repeat_founder_archetype_when_it_is_the_only_material_match():
    p = prof([role(position_title="Founder", company_name="A Co", department="Executive",
                   company_industry="Computer Software",
                   date_from="01/2012", date_from_year=2012, date_from_month=1,
                   date_to="01/2017", date_to_year=2017, date_to_month=1),
              role(position_title="Co-Founder", company_name="B Co", department="Executive",
                   company_industry="Computer Software",
                   date_from="02/2017", date_from_year=2017, date_from_month=2,
                   date_to=None, date_to_year=None, is_current=1)])
    r = label(p)
    assert r.archetype == "Repeat Founder"
    assert r.matched == ["Repeat Founder"]
    assert "founder_evidence" in r.strong_signals


def test_repeat_founder_keeps_the_primary_label_and_retains_co_matches():
    """CP4-R4. These two foundings are at healthcare companies with an
    `Executive` department, so Healthcare Operator also matches. Repeat Founder
    is a high-specificity claim and keeps the PRIMARY label; the co-match is
    retained as secondary rather than discarded or collapsed into Hybrid."""
    p = prof([role(position_title="Founder", company_name="A Co", department="Executive",
                   company_industry="Hospital & Health Care", duration_months=60,
                   date_from="01/2012", date_from_year=2012, date_from_month=1,
                   date_to="01/2017", date_to_year=2017, date_to_month=1),
              role(position_title="Co-Founder", company_name="B Co", department="Executive",
                   company_industry="Hospital & Health Care", duration_months=48,
                   date_from="02/2017", date_from_year=2017, date_from_month=2,
                   date_to=None, date_to_year=None, is_current=1)])
    r = label(p)
    assert r.archetype == "Repeat Founder" == r.primary_archetype
    assert {"Repeat Founder", "Healthcare Operator"} <= set(r.matched)
    assert r.secondary == ["Healthcare Operator"]
    assert "founder_evidence" in r.strong_signals
    assert "retained as secondary" in r.explanation


def test_technical_builder_from_engineering_department():
    p = prof([role(position_title="Staff Engineer", department="Engineering",
                   company_industry="Computer Software", management_level="Senior")])
    r = label(p)
    assert r.archetype == "Technical Builder"


def test_commercial_gtm_from_sales_department():
    p = prof([role(position_title="Head of Sales", department="Sales",
                   company_industry="Computer Software", management_level="Head")])
    assert label(p).archetype == "Commercial/GTM"


def test_clinical_expert_from_clinical_degree_and_health_months():
    """Degree alone is not enough — the configured rule also needs health months,
    so a nurse who never worked in healthcare would not be labelled a clinician."""
    p = prof([role(position_title="Registered Nurse", department="Nursing",
                   management_level="Specialist", duration_months=60)],
             [edu(degree="Bachelor of Science in Nursing", field_of_study="Nursing")])
    r = label(p)
    assert "Clinical Expert" in r.matched
    assert r.archetype in ("Clinical Expert", "Hybrid")


def test_rn_to_clinical_operations_profile_resolves_from_raw_fields():
    """The supplied RN → Clinical Operations Lead record.

    NOTE (reported to the reviewer, not tuned): this record satisfies BOTH
    Clinical Expert and Healthcare Operator under the frozen archetype config,
    because `Clinical Operations` is listed as a department under both, and
    because `management_level_at_least: Manager` is evaluated on the codebase's
    single ordinal ladder, on which `Lead` ties `Manager`. Two material matches
    trigger the configured Hybrid behaviour. The assertions below fix the parts
    that are not in question — Clinical Expert IS matched from raw fields, and
    the archetype-specific gaps are founder and technical evidence — and leave
    the Clinical-Expert-vs-Hybrid resolution to the reviewer decision recorded
    in docs/EVAL_DECISIONS.md."""
    r = label(RN)
    assert "Clinical Expert" in r.matched
    assert r.archetype in ("Clinical Expert", "Hybrid")
    assert "healthcare_depth" in r.strong_signals
    assert {"founder_evidence", "technical_evidence"} <= set(r.missing_for_archetype)
    # matched from raw evidence, not from a score
    assert "BSN" in r.explanation or "Nursing" in r.explanation


def test_hybrid_names_its_constituents_and_needs_a_material_share():
    """A clinician who became a product leader: two archetypes, each carrying a
    material share of role-months."""
    p = prof([role(position_title="Registered Nurse", department="Nursing",
                   management_level="Specialist", duration_months=60,
                   date_from="01/2010", date_from_year=2010, date_from_month=1,
                   date_to="01/2015", date_to_year=2015, date_to_month=1),
              role(position_title="Director of Product", department="Product",
                   management_level="Director", duration_months=84,
                   date_from="02/2015", date_from_year=2015, date_from_month=2,
                   date_to=None, date_to_year=None, is_current=1)],
             [edu(degree="Bachelor of Science in Nursing", field_of_study="Nursing")])
    r = label(p)
    assert r.archetype == "Hybrid"
    assert {"Clinical Expert", "Product Builder"} <= set(r.matched)
    assert "Clinical Expert" in r.explanation and "Product Builder" in r.explanation


def test_an_incidental_short_role_does_not_manufacture_a_hybrid():
    """Two months of product work inside a fifteen-year nursing career is below
    the configured 25% share gate, so the second label is reported as a match
    but does not take over the archetype."""
    p = prof([role(position_title="Registered Nurse", department="Nursing",
                   management_level="Specialist", duration_months=180,
                   date_from="01/2008", date_from_year=2008, date_from_month=1,
                   date_to="01/2023", date_to_year=2023, date_to_month=1),
              role(position_title="Product Advisor", department="Product",
                   management_level="Specialist", duration_months=2,
                   date_from="02/2023", date_from_year=2023, date_from_month=2,
                   date_to="04/2023", date_to_year=2023, date_to_month=4)],
             [edu(degree="Bachelor of Science in Nursing", field_of_study="Nursing")])
    r = label(p)
    assert r.archetype != "Hybrid"
    assert "Product Builder" in r.matched
    assert r.shares["Product Builder"] < ACFG["hybrid"]["min_role_month_share"]


# ===========================================================================
# fallback state
# ===========================================================================
def test_insufficient_evidence_is_a_fallback_state_not_an_archetype():
    p = prof([])
    r = label(p)
    assert r.archetype == ACFG["unknown_label"] == "Insufficient Evidence"
    assert r.archetype not in CONFIGURED_NAMES, "the fallback must not be a 9th archetype"
    assert r.strong_signals == [] and r.matched == []
    assert "no configured archetype" in r.explanation


def test_unmatched_departments_fall_back_rather_than_guessing():
    p = prof([role(position_title="Zookeeper", department="Animal Care",
                   company_industry="Entertainment", management_level="Specialist")])
    assert label(p).archetype == ACFG["unknown_label"]


# ===========================================================================
# G — the labeller changes NOTHING
# ===========================================================================
CASES = {
    "pm_sample": PM,
    "rn_sample": RN,
    "repeat_founder": prof([
        role(position_title="Founder", company_name="A Co", department="Executive",
             date_from="01/2012", date_from_year=2012, date_from_month=1,
             date_to="01/2017", date_to_year=2017, date_to_month=1),
        role(position_title="Co-Founder", company_name="B Co", department="Executive",
             date_from="02/2017", date_from_year=2017, date_from_month=2)]),
    "empty": prof([]),
}


@pytest.mark.parametrize("name", list(CASES))
def test_archetype_assignment_changes_no_number(name):
    p = CASES[name]
    signals = compute_signals(p, CFG)
    before = {
        "profile": p.model_dump(mode="json"),
        "signals": [s.model_dump(mode="json") for s in signals],
        "broad_score": broad_score(signals, CFG),
        "confidence": compute_confidence(p, CFG).confidence,
        "exceptional": detect_exceptional(p, CFG).to_dict(),
    }
    label_archetype(p, signals, CFG, before["exceptional"]["flag"])

    signals_after = compute_signals(p, CFG)
    after = {
        "profile": p.model_dump(mode="json"),
        "signals": [s.model_dump(mode="json") for s in signals_after],
        "broad_score": broad_score(signals_after, CFG),
        "confidence": compute_confidence(p, CFG).confidence,
        "exceptional": detect_exceptional(p, CFG).to_dict(),
    }
    assert after == before


@pytest.mark.parametrize("name", list(CASES))
def test_forcing_a_different_archetype_changes_no_number(name):
    """Relabelling by hand — the human override the UI will eventually allow —
    cannot feed back into the machine's judgment."""
    p = CASES[name]
    signals = compute_signals(p, CFG)
    ev = detect_exceptional(p, CFG)
    baseline = (broad_score(signals, CFG), compute_confidence(p, CFG).confidence, ev.flag)

    for forced in CONFIGURED_NAMES + [ACFG["unknown_label"]]:
        r = label_archetype(p, signals, CFG, ev.flag)
        r.archetype = forced          # simulate a human overriding the label
        signals_now = compute_signals(p, CFG)
        assert (broad_score(signals_now, CFG),
                compute_confidence(p, CFG).confidence,
                detect_exceptional(p, CFG).flag) == baseline


@pytest.mark.parametrize("name", list(CASES))
def test_labeller_is_deterministic_and_pure(name):
    p = CASES[name]
    signals = compute_signals(p, CFG)
    snapshot = p.model_dump(mode="json")
    a = label_archetype(p, signals, CFG, False).to_dict()
    b = label_archetype(p, signals, CFG, False).to_dict()
    assert a == b
    assert p.model_dump(mode="json") == snapshot


def test_exceptional_flag_only_changes_which_evidence_is_highlighted():
    """The flag is allowed to select a highlight (it is one of the configured
    `highlights` entries). It must not change WHICH archetype is assigned."""
    p = CASES["repeat_founder"]
    signals = compute_signals(p, CFG)
    off = label_archetype(p, signals, CFG, exceptional_flag=False)
    on = label_archetype(p, signals, CFG, exceptional_flag=True)
    assert off.archetype == on.archetype
    assert off.matched == on.matched and off.shares == on.shares
    assert "exceptional_signals" in on.strong_signals
    assert "exceptional_signals" not in off.strong_signals


def test_primary_precedence_changes_the_label_and_nothing_else():
    """CP4-R4 invariance. Re-run the labeller with `primary_precedence` removed
    from config and compare: the primary label moves Repeat Founder ↔ Hybrid,
    every number stays bit-identical, and no co-matched archetype is lost."""
    import copy
    from app.normalize.config import Config

    p = CASES["repeat_founder"]
    signals = compute_signals(p, CFG)
    ev = detect_exceptional(p, CFG)
    numbers = (broad_score(signals, CFG), compute_confidence(p, CFG).confidence,
               ev.flag, ev.to_dict())

    no_precedence = copy.deepcopy(CFG.archetypes)
    no_precedence["primary_precedence"] = []
    cfg2 = Config(weights=CFG.weights, institutions=CFG.institutions,
                  health=CFG.health, archetypes=no_precedence)

    with_pref = label_archetype(p, signals, CFG, ev.flag)
    without = label_archetype(p, signals, cfg2, ev.flag)

    assert with_pref.archetype == "Repeat Founder"
    assert without.archetype == "Hybrid"
    assert set(with_pref.matched) == set(without.matched)   # nothing dropped
    assert with_pref.shares == without.shares

    signals_after = compute_signals(p, CFG)
    ev_after = detect_exceptional(p, CFG)
    assert (broad_score(signals_after, CFG), compute_confidence(p, CFG).confidence,
            ev_after.flag, ev_after.to_dict()) == numbers
