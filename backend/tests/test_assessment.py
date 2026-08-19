"""Assessment assembly, data_state, the machine/human boundary, and the
missing-data safety property — PLAN §4.5, CP5 gate.

Unlike `test_policy.py`, which states founders as five scalars, everything here
runs the real pipeline: raw JSON -> normalize -> signals/confidence/exceptional
-> policy. These tests are what prove the scalars in `test_policy.py` are wired
to something true.
"""

import copy
import itertools
import json
from pathlib import Path

import pytest

from app.assessment import ASSESSMENT_VERSION, Assessment, assess
from app.models.raw import RawProfile, load_profiles
from app.normalize import load_config, normalize
from app.policy import Attention, DataState, Potential, RecommendedAction

CFG = load_config()
ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "data" / "raw" / "sample.json"


def A(raw: dict) -> Assessment:
    return assess(normalize(RawProfile.model_validate(raw), CFG), CFG)


def base(**kw) -> dict:
    d = {"mdm_person_id": "p-test", "headline": None, "experience": [], "education": [],
         "total_experience_duration_months": None}
    d.update(kw)
    return d


def role(**kw) -> dict:
    r = {"position_title": "Analyst", "company_name": "Acme Health",
         "company_industry": "Hospital & Health Care", "management_level": "Senior",
         "date_from_year": 2015, "date_from_month": 3, "date_to_year": 2018,
         "date_to_month": 3, "duration_months": 36, "is_current": False,
         "active_experience": False}
    r.update(kw)
    return r


# A profile whose §4.3 coverage is exactly 1.00: two dated titled roles with a
# readable industry, a known current-role state, education, a stated total and a
# location. Used as the SUFFICIENT baseline and as the ablation subject.
COMPLETE = base(
    headline="Director of Clinical Operations",
    experience=[
        role(position_title="Director of Clinical Operations", management_level="Director",
             date_from_year=2019, date_from_month=1, date_to_year=None, date_to_month=None,
             duration_months=60, is_current=True, active_experience=True,
             company_employees_count=800),
        role(position_title="Clinical Operations Manager", management_level="Manager",
             date_from_year=2014, date_from_month=6, date_to_year=2018, date_to_month=12,
             duration_months=54, company_employees_count=300),
    ],
    education=[{"institution_name": "Cornell University", "degree": "BSN, Nursing",
                "field_of_study": "Nursing", "date_from_year": 2008, "date_to_year": 2012}],
    total_experience_duration_months=114,
    location_country="United States", location_city="Boston")


# ===========================================================================
# Assembly
# ===========================================================================
def test_assessment_carries_version_metadata():
    a = A(COMPLETE)
    assert a.assessment_version == ASSESSMENT_VERSION
    assert a.rubric_version == CFG.version_hash()
    # CP7: rubric_version is the FULL SHA-256 of the effective config (was a
    # 12-char prefix through CP6). Representation only — no rubric changed.
    assert len(a.rubric_version) == 64


def test_assessment_is_deterministic():
    assert A(COMPLETE).to_dict() == A(COMPLETE).to_dict()


def test_assessment_serialises_to_json():
    json.dumps(A(COMPLETE).to_dict())


def test_every_signal_reaches_the_assessment_with_provenance():
    a = A(COMPLETE)
    assert len(a.signals) == 7
    for s in a.signals:
        if s.observed:
            assert s.source_fields, f"{s.name} is observed but names no raw field"


def test_broad_score_in_the_assessment_matches_the_weighted_sum():
    a = A(COMPLETE)
    w = CFG.weights["signal_weights"]
    assert a.broad_score == pytest.approx(round(sum(w[s.name] * s.value for s in a.signals), 2))


def test_the_two_supplied_profiles_assess_without_error():
    for p in load_profiles(SAMPLE):
        a = assess(normalize(p, CFG), CFG)
        assert a.attention in set(Attention) and a.potential in set(Potential)
        assert a.policy_trace and a.fired_rules


# ===========================================================================
# H — data_state, one real assessment per state
# ===========================================================================
def test_data_state_complete_and_clean_is_sufficient():
    a = A(COMPLETE)
    assert a.confidence_breakdown.coverage == 1.0
    assert a.data_state is DataState.SUFFICIENT
    assert not a.contradictions


def test_data_state_complete_but_contradictory_is_sufficient_with_lower_confidence():
    """Same coverage, a stated total that disagrees with the roles. The
    contradiction costs confidence and does NOT change data_state."""
    clean = A(COMPLETE)
    contradictory = copy.deepcopy(COMPLETE)
    contradictory["total_experience_duration_months"] = 400   # vs 114 months of roles
    c = A(contradictory)
    assert c.data_state is DataState.SUFFICIENT
    assert c.confidence_breakdown.coverage == clean.confidence_breakdown.coverage == 1.0
    assert c.confidence < clean.confidence
    assert any(x.code == "TOTAL_MISMATCH" for x in c.contradictions)


def test_data_state_partial_when_a_decision_relevant_field_is_absent():
    """Experience history is still usable — two dated roles — but education is
    gone, so coverage is short of 1.0."""
    partial = copy.deepcopy(COMPLETE)
    partial["education"] = []
    a = A(partial)
    assert a.data_state is DataState.PARTIAL
    assert a.confidence_breakdown.coverage < 1.0
    assert any(m.code in ("NO_EDUCATION", "COVERAGE_EDUCATION") for m in a.missing)


def test_data_state_needs_information_when_experience_history_is_missing():
    a = A(base(education=[{"institution_name": "Cornell University", "degree": "MD"}]))
    assert a.data_state is DataState.NEEDS_INFORMATION
    assert a.recommended_action is RecommendedAction.RESEARCH


def test_data_state_needs_information_when_experience_history_is_incomplete():
    """A single role: where they are, not how they got there (I-3)."""
    one = copy.deepcopy(COMPLETE)
    one["experience"] = one["experience"][:1]
    a = A(one)
    assert a.data_state is DataState.NEEDS_INFORMATION
    assert a.recommended_action is RecommendedAction.RESEARCH
    assert any(m.code == "INCOMPLETE_EXPERIENCE_HISTORY" for m in a.missing)


def test_contradictions_alone_never_move_data_state_off_sufficient():
    for total in (200, 400, 900):
        d = copy.deepcopy(COMPLETE)
        d["total_experience_duration_months"] = total
        assert A(d).data_state is DataState.SUFFICIENT


# ===========================================================================
# Missing / contradiction reporting
# ===========================================================================
def test_missing_is_reported_but_never_scored_as_negative():
    """Removing education adds a `missing` item and lowers confidence. It must
    not push the education signal below the value a profile with NO education
    gets — absence is not negative evidence."""
    without = A(base(experience=COMPLETE["experience"]))
    empty_edu = next(s for s in without.signals if s.name == "education_signal")
    unknown_edu = next(
        s for s in A(base(experience=COMPLETE["experience"],
                          education=[{"institution_name": "Cobalt Ridge University",
                                      "degree": "Certificate"}])).signals
        if s.name == "education_signal")
    assert empty_edu.value == unknown_edu.value == 0.0


def test_an_empty_profile_reports_missing_and_is_never_routine():
    a = A(base())
    assert a.missing
    assert a.attention is Attention.REVIEW
    assert a.data_state is DataState.NEEDS_INFORMATION
    assert a.recommended_action is RecommendedAction.RESEARCH
    assert a.potential is not Potential.LOW


# ===========================================================================
# K — no human authority in anything the machine emits
# ===========================================================================
HUMAN_DECISIONS = {"NEEDS_REVIEW", "POTENTIAL", "NOT_NOW", "NEEDS_INFORMATION"}
HUMAN_STAGES = {"NEW", "ASSESSMENT", "POTENTIAL", "NURTURING", "KEEP_WARM", "DEAL", "CLOSED"}


def _walk(obj, path="$"):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield path, k, v
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]")


def test_K_assessment_model_declares_no_decision_or_stage_field():
    assert "decision" not in Assessment.model_fields
    assert "stage" not in Assessment.model_fields


def test_K_serialized_assessment_has_no_decision_or_stage_key_at_any_depth():
    for raw in (COMPLETE, base()) + tuple(
            p.model_dump(mode="json") for p in load_profiles(SAMPLE)):
        d = A(raw).to_dict()
        for path, key, _ in _walk(d):
            assert key.lower() not in ("decision", "stage", "disposition"), \
                f"human-authority key {key!r} at {path}"


def test_K_no_emitted_enum_value_is_a_human_disposition_or_stage():
    """Semantic, not substring: the enum VALUES are checked, so
    CONSIDER_ENGAGEMENT passes and a bare `Engage` would not."""
    a = A(COMPLETE)
    emitted = {a.attention.value, a.potential.value, a.data_state.value,
               a.recommended_action.value}
    assert not (emitted & HUMAN_STAGES)
    assert not (emitted & (HUMAN_DECISIONS - {"POTENTIAL", "NEEDS_INFORMATION"}))


def test_K_the_machine_never_emits_the_action_word_engage():
    """`CONSIDER_ENGAGEMENT` is permitted; the imperative `Engage` is not. This
    tests the token, so it cannot be satisfied or broken by substring accident."""
    for raw in (COMPLETE, base()) + tuple(
            p.model_dump(mode="json") for p in load_profiles(SAMPLE)):
        a = A(raw)
        assert a.recommended_action.value != "Engage"
        for dim in (a.attention.value, a.potential.value, a.data_state.value,
                    a.recommended_action.value):
            tokens = {t.strip(".,;:!?()[]'\"").upper() for t in dim.replace("_", " ").split()}
            assert "ENGAGE" not in tokens, f"bare imperative ENGAGE in {dim!r}"


def test_K_core_modules_hold_no_human_workflow_vocabulary():
    """The assessment core is API-independent and holds no human state.

    This is checked SEMANTICALLY — against each module's public namespace and
    the values its enums can emit — not by grepping the source text. A prose
    grep would fire on the very docstrings that document why `NOT_NOW` and
    `stage` are excluded, which is the opposite of what we want to police."""
    import importlib

    forbidden = {"DECISION", "STAGE", "DISPOSITION", "NOT_NOW", "NEEDS_REVIEW",
                 "KEEP_WARM", "NURTURING", "OWNER", "NEXT_ACTION", "AUDIT_LOG"}
    for name in ("app.assessment.assess", "app.assessment.model",
                 "app.policy.safety", "app.policy.dimensions"):
        mod = importlib.import_module(name)
        public = {n.upper() for n in vars(mod) if not n.startswith("_")}
        leaked = public & forbidden
        assert not leaked, f"{name} exposes human-workflow symbol(s) {leaked}"


def test_K_no_machine_enum_can_express_a_stage_transition():
    from app.policy.dimensions import (Attention, DataState, Potential,
                                       RecommendedAction)
    machine = {v.value for e in (Attention, DataState, Potential, RecommendedAction)
               for v in e}
    assert not (machine & (HUMAN_STAGES - {"POTENTIAL", "ASSESSMENT"}))


# ===========================================================================
# L — missing-data safety. What actually holds, stated exactly.
# ===========================================================================
# Fields the §4.3 coverage model reads (their loss lowers coverage -> confidence).
COVERAGE_FIELDS = ["position_title", "company_industry", "date_from_year", "is_current",
                   "active_experience", "education", "total_experience_duration_months",
                   "location_country"]
# Fields that move broad_score but that NO coverage component reads. Their loss
# is invisible to confidence — this is the gap CP5 finding F-1 reports.
EVIDENCE_ONLY_FIELDS = ["management_level", "duration_months", "company_employees_count",
                        "department"]


# Some evidence FAMILIES are carried by more than one raw field, and removing
# one leaves the fact readable from the other: `is_current` is recoverable from
# `active_experience`, and country from city. Ablating a family means removing
# every field that carries it — otherwise the "ablation" removes nothing.
FAMILY = {
    "is_current": ["is_current", "active_experience"],
    "location_country": ["location_country", "location_city"],
    "date_from_year": ["date_from_year", "date_from_month", "date_from"],
    "company_employees_count": ["company_employees_count", "company_size_range"],
}


def ablate(raw: dict, field: str) -> dict:
    d = copy.deepcopy(raw)
    for f in FAMILY.get(field, [field]):
        if f in ("experience", "education"):
            d[f] = []
            continue
        if f in d:
            d[f] = None
        for key in ("experience", "education"):
            for row in d.get(key) or []:
                if f in row:
                    row[f] = None
    return d


@pytest.mark.parametrize("field", COVERAGE_FIELDS + EVIDENCE_ONLY_FIELDS + ["experience"])
def test_L1_ablation_never_increases_confidence(field):
    before, after = A(COMPLETE), A(ablate(COMPLETE, field))
    assert after.confidence <= before.confidence + 1e-9


@pytest.mark.parametrize("field", COVERAGE_FIELDS + EVIDENCE_ONLY_FIELDS + ["experience"])
def test_L2_a_profile_that_loses_confidence_below_the_bar_is_never_routine(field):
    """The load-bearing recall-first guarantee: we only ever say ROUTINE about a
    profile we positively trust. Uncertainty cannot be mistaken for safety."""
    after = A(ablate(COMPLETE, field))
    if after.confidence < CFG.thresholds["priority_confidence"]:
        assert after.attention is not Attention.ROUTINE
        assert after.potential is not Potential.LOW


@pytest.mark.parametrize("field", COVERAGE_FIELDS + EVIDENCE_ONLY_FIELDS + ["experience"])
def test_L3_routine_after_ablation_always_implies_a_trusted_profile(field):
    after = A(ablate(COMPLETE, field))
    if after.attention is Attention.ROUTINE:
        assert after.confidence >= CFG.thresholds["priority_confidence"]
        assert after.broad_score < CFG.thresholds["routine_broad"]
        assert not after.exceptional.flag


def test_L4_total_data_loss_produces_review_not_routine():
    """The extreme: strip everything. A profile we know nothing about is the
    LEAST safe thing to call routine, and never is."""
    for field in ("experience", "education"):
        pass
    empty = A(base())
    assert empty.attention is Attention.REVIEW
    assert empty.broad_score == 0.0 and empty.confidence == 0.0
    assert empty.data_state is DataState.NEEDS_INFORMATION


def test_L5_ablating_every_field_at_once_is_never_routine():
    d = COMPLETE
    for f in COVERAGE_FIELDS + EVIDENCE_ONLY_FIELDS:
        d = ablate(d, f)
    a = A(d)
    assert a.attention is not Attention.ROUTINE


def test_L6_exceptional_evidence_survives_ablations_that_do_not_remove_it():
    """Removing supporting/coverage data around exceptional evidence must not
    remove the priority. Only removing the evidence ITSELF may."""
    repeat_founder = base(
        experience=[role(position_title="Co-Founder & CEO", company_name="Alpha Health",
                         management_level="C-Level", date_from_year=2020, duration_months=40),
                    role(position_title="Founder", company_name="Beta Care",
                         management_level="C-Level", date_from_year=2014, duration_months=48)],
        education=[{"institution_name": "Cornell University", "degree": "BS"}],
        total_experience_duration_months=88, location_country="United States")
    assert A(repeat_founder).attention is Attention.PRIORITY_REVIEW
    for field in ("education", "total_experience_duration_months", "location_country",
                  "company_employees_count", "company_industry", "management_level",
                  "duration_months", "is_current"):
        a = A(ablate(repeat_founder, field))
        assert a.exceptional.flag, f"ablating {field} removed the founder titles?"
        assert a.attention is Attention.PRIORITY_REVIEW, \
            f"ablating {field} lowered attention while the evidence was still present"


def test_L7_removing_the_exceptional_evidence_itself_may_legitimately_lower_attention():
    """The distinction the property depends on. Removing `position_title` removes
    the founder titles — the evidence, not merely its support — so the fall is
    correct behaviour, not a safety failure. It still does not land ROUTINE,
    because losing titles also costs coverage."""
    repeat_founder = base(
        experience=[role(position_title="Co-Founder & CEO", company_name="Alpha Health",
                         management_level="C-Level", date_from_year=2020, duration_months=40),
                    role(position_title="Founder", company_name="Beta Care",
                         management_level="C-Level", date_from_year=2014, duration_months=48)],
        education=[{"institution_name": "Cornell University", "degree": "BS"}],
        total_experience_duration_months=88, location_country="United States")
    after = A(ablate(repeat_founder, "position_title"))
    assert after.exceptional.flag is False        # the evidence itself is gone
    assert after.attention is not Attention.ROUTINE


# --- v2.2: the CP5 F-1 finding, now FIXED and pinned ------------------------
# At v2.1 this documented a real hole: `management_level` carried 30 broad points
# that NO coverage component read, so deleting it dropped a REVIEW founder to
# ROUTINE with confidence unchanged. Amendments 1 and 2 close it from both ends.
def test_L8_management_level_loss_is_now_visible_to_confidence():
    """Amendment 1. The field that used to vanish for free now costs coverage."""
    before, after = A(COMPLETE), A(ablate(COMPLETE, "management_level"))
    assert before.confidence_breakdown.coverage == 1.0
    assert after.confidence < before.confidence            # it was == at v2.1
    assert after.confidence_breakdown.coverage_subcomponents[
        "experience_history"]["seniority_readability"] == 0.0
    assert any(m.code == "COVERAGE_SENIORITY_READABILITY" for m in after.missing)


def test_L8b_management_level_loss_no_longer_reaches_routine():
    """Amendment 2. Broad still falls below 40 and confidence is still >= 0.6,
    so rule 4 still fires — but PARTIAL data floors attention at REVIEW."""
    after = A(ablate(COMPLETE, "management_level"))
    assert after.broad_score < CFG.thresholds["routine_broad"]
    assert after.confidence >= CFG.thresholds["priority_confidence"]
    assert after.data_state is DataState.PARTIAL
    assert after.attention is Attention.REVIEW             # was ROUTINE at v2.1
    assert after.recommended_action is not RecommendedAction.NO_URGENT_ACTION


def test_L8c_rule_5_is_keyed_on_history_depth_not_the_composite_component():
    """Regression: Amendment 1 enriched `experience_history`, and reading the
    composite here reported a complete two-role history as a MISSING history."""
    after = A(ablate(COMPLETE, "management_level"))
    assert after.confidence_breakdown.coverage_subcomponents[
        "experience_history"]["history_depth"] == 1.0
    assert after.data_state is DataState.PARTIAL           # not NEEDS_INFORMATION
    assert not any(m.code.endswith("EXPERIENCE_HISTORY") for m in after.missing)


# --- v2.2 Amendment 1: the source -> coverage matrix, proved field by field ---
# Every evidence family that materially feeds a deterministic signal must move at
# least one coverage component when it disappears. This is the whole amendment.
COVERAGE_MATRIX = [
    ("position_title", "founder_evidence", "titles_readable"),
    ("management_level", "experience_history", "seniority_readability"),
    ("duration_months", "experience_history", "tenure_readability"),
    ("date_from_year", "chronology", "start_dates_readable"),
    ("company_industry", "company_domain_classification", "industry_classified"),
    ("company_employees_count", "company_domain_classification", "scope_available"),
    ("is_current", "current_role", "is_current_known"),
    ("education", "education", "education_present"),
    ("total_experience_duration_months", "other", "total_experience_stated"),
    ("location_country", "other", "location_known"),
]


@pytest.mark.parametrize("field,component,subcomponent", COVERAGE_MATRIX)
def test_A1_every_evidence_family_moves_its_coverage_subcomponent(
        field, component, subcomponent):
    before, after = A(COMPLETE), A(ablate(COMPLETE, field))
    b = before.confidence_breakdown.coverage_subcomponents[component][subcomponent]
    a = after.confidence_breakdown.coverage_subcomponents[component][subcomponent]
    assert b == 1.0, f"{subcomponent} was not satisfied in the baseline profile"
    assert a < b, f"removing {field} left {component}.{subcomponent} unchanged"


@pytest.mark.parametrize("field,component,_sub", COVERAGE_MATRIX)
def test_A1_every_evidence_family_moves_overall_coverage(field, component, _sub):
    before, after = A(COMPLETE), A(ablate(COMPLETE, field))
    assert after.confidence_breakdown.coverage < before.confidence_breakdown.coverage
    assert after.confidence < before.confidence


def test_A1_institution_tier_is_deliberately_not_a_coverage_input():
    """Availability, not recognisability. A school off the tier list is still an
    institution we can read, and A7 fixes unknown as a valid neutral outcome —
    scoring coverage on it would measure the size of our starter list."""
    tiered = copy.deepcopy(COMPLETE)
    untiered = copy.deepcopy(COMPLETE)
    untiered["education"] = [{"institution_name": "Cobalt Ridge University",
                              "degree": "BSN, Nursing", "field_of_study": "Nursing"}]
    a, b = A(tiered), A(untiered)
    assert b.confidence_breakdown.coverage_subcomponents[
        "education"]["institution_present"] == 1.0
    assert b.confidence_breakdown.coverage_components["education"] == \
        a.confidence_breakdown.coverage_components["education"]


def test_A1_unrecognised_value_lowers_coverage_but_never_a_signal():
    """An unparseable credential is unevaluable, so it costs coverage. It must
    still not push the education signal below its neutral floor."""
    d = copy.deepcopy(COMPLETE)
    d["education"] = [{"institution_name": "Cornell University", "degree": "Certificate, X"}]
    a = A(d)
    assert a.confidence_breakdown.coverage_subcomponents[
        "education"]["degree_interpretable"] == 0.0
    assert next(s for s in a.signals if s.name == "education_signal").value >= 0.0


# --- v2.2 Amendment 2 / 3 at the assessment level ---------------------------
def test_A2_routine_never_coexists_with_partial_or_needs_information():
    for field in COVERAGE_FIELDS + EVIDENCE_ONLY_FIELDS + ["experience"]:
        a = A(ablate(COMPLETE, field))
        if a.attention is Attention.ROUTINE:
            assert a.data_state is DataState.SUFFICIENT


def test_A2_partial_never_rests_on_no_urgent_action():
    for field in COVERAGE_FIELDS + EVIDENCE_ONLY_FIELDS:
        a = A(ablate(COMPLETE, field))
        if a.data_state is DataState.PARTIAL:
            assert a.recommended_action is not RecommendedAction.NO_URGENT_ACTION


def test_A3_low_confidence_profiles_are_unknown_at_the_assessment_level():
    d = COMPLETE
    for f in ("position_title", "company_industry", "date_from_year", "is_current"):
        d = ablate(d, f)
    a = A(d)
    assert a.confidence < CFG.thresholds["priority_confidence"]
    assert a.potential is Potential.UNKNOWN


# --- L (v2.2): the HARD invariant. Zero downgrades, no exemptions. ----------
ALL_ABLATION_FIELDS = COVERAGE_FIELDS + EVIDENCE_ONLY_FIELDS + ["experience"]


@pytest.mark.parametrize("field", ALL_ABLATION_FIELDS)
def test_L9_no_ablation_moves_priority_or_review_to_routine(field):
    """The v2.2 hard invariant, with the v2.1 'positive evidence removed'
    exemption REMOVED. If the evidence disappears, coverage must fall too, so
    PARTIAL/NEEDS_INFORMATION protects the founder from routine dismissal."""
    before, after = A(COMPLETE), A(ablate(COMPLETE, field))
    assert before.attention is not Attention.ROUTINE
    assert after.attention is not Attention.ROUTINE, \
        f"ablating {field} downgraded {before.attention.value} -> ROUTINE"


def test_L10_removing_exceptional_evidence_no_longer_reaches_routine():
    """The v2.1 semantic edge, now closed. Removing `management_level` clears
    both progression and leadership-scope detectors — the evidence itself — but
    the same removal now costs coverage, so the founder lands REVIEW."""
    senior = base(
        experience=[role(position_title="VP of Operations", management_level="VP",
                         company_name="Alpha Health", company_employees_count=4000,
                         date_from_year=2021, duration_months=36),
                    role(position_title="Analyst", management_level="Entry",
                         company_name="Beta Care", company_employees_count=300,
                         date_from_year=2019, duration_months=24)],
        education=[{"institution_name": "Cornell University", "degree": "BS"}],
        total_experience_duration_months=60, location_country="United States")
    before = A(senior)
    after = A(ablate(senior, "management_level"))
    assert before.exceptional.flag and before.attention is Attention.PRIORITY_REVIEW
    assert after.exceptional.flag is False        # the evidence itself is gone
    assert after.attention is not Attention.ROUTINE
    assert after.data_state is DataState.PARTIAL


# --- v2.2 FINDING F-6: deleting a contradiction's carrier removes the -------
# contradiction, and that can outweigh the coverage it costs. Reported, not
# tuned. It is NOT a safety failure: it never reaches ROUTINE (test_L9), and
# after the deletion the record genuinely IS self-consistent. But it means
# confidence is not monotonic under data removal in general, so the CP3
# monotonicity property is scoped to fields that carry no contradiction.
def test_F6_deleting_the_contradicting_total_raises_confidence():
    """`total_experience_duration_months` is the field that CREATES
    TOTAL_MISMATCH. Delete it and the profile stops disagreeing with itself."""
    contradictory = copy.deepcopy(COMPLETE)
    contradictory["total_experience_duration_months"] = 400
    before = A(contradictory)
    after = A(ablate(contradictory, "total_experience_duration_months"))
    assert any(c.code == "TOTAL_MISMATCH" for c in before.contradictions)
    assert not after.contradictions
    assert after.confidence_breakdown.coverage < before.confidence_breakdown.coverage
    assert after.confidence > before.confidence          # <- the finding
    assert after.attention is not Attention.ROUTINE      # but never unsafe


def test_F6_deleting_a_contradictory_currentness_claim_raises_coverage():
    """A role claiming to be current while carrying an end date resolves to
    UNKNOWN. Remove the claim and the end date alone says NO, cleanly — so
    coverage itself rises. Semantically right, and still reported."""
    # The conflict must sit on the MOST RECENT role — that is the one
    # `is_current_known` reads.
    conflicted = copy.deepcopy(COMPLETE)
    conflicted["experience"][0]["date_to_year"] = 2023    # claims current AND ends
    conflicted["experience"][0]["date_to_month"] = 6
    before = A(conflicted)
    after = A(ablate(conflicted, "is_current"))
    assert any(c.code == "AMBIGUOUS_CURRENT" for c in before.contradictions)
    assert not any(c.code == "AMBIGUOUS_CURRENT" for c in after.contradictions)
    assert after.confidence >= before.confidence
    assert after.attention is not Attention.ROUTINE


def test_F6_confidence_is_monotonic_for_fields_carrying_no_contradiction():
    """The property that DOES hold universally, stated at its true scope."""
    clean = COMPLETE       # no contradictions in the baseline
    assert not A(clean).contradictions
    for field in ("position_title", "management_level", "company_industry",
                  "company_employees_count", "education", "date_from_year",
                  "duration_months", "location_country"):
        assert A(ablate(clean, field)).confidence <= A(clean).confidence + 1e-9
