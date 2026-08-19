"""Safety-policy tests — PLAN §4.5. The pre-UI semantic gate.

These tests state founders as five scalars and assert on the four dimensions,
with no scorer in the loop. That is the point: a test that says
`broad=45, confidence=0.40, exceptional=True` means exactly that, and cannot be
made to pass by moving a weight.

Structure mirrors the reviewer's CP5 requirements:
  A  precedence — rule 1's PRIORITY_REVIEW is sticky
  B  rule 2
  C  low-confidence semantics
  D  ROUTINE / LOW safety
  E  threshold boundaries (thresholds are REPORTED, never changed)
  F  recommended_action precedence
  G  potential does not mirror attention
  H  data_state
  I  policy trace
  K  no human authority
"""

import itertools

import pytest

from app.normalize import load_config
from app.policy import (RULE_1, RULE_2, RULE_3, RULE_4, RULE_5, RULE_ELSE,
                        Attention, DataState, PolicyInput, Potential,
                        RecommendedAction, apply_policy)
from app.policy.safety import (ACTION_RULE, DATA_STATE_RULE, GUARD_4,
                               GUARD_5, GUARD_6, GUARD_8)

CFG = load_config()
T = CFG.thresholds
BROAD_HI = T["priority_broad"]            # 65
CONF_BAR = T["priority_confidence"]       # 0.6
BROAD_FLOOR = T["low_confidence_floor_broad"]  # 30
BROAD_LO = T["routine_broad"]             # 40


def P(broad, confidence, exceptional=False, experience_incomplete=False, coverage=1.0):
    return apply_policy(PolicyInput(broad_score=broad, confidence=confidence,
                                    exceptional=exceptional,
                                    experience_incomplete=experience_incomplete,
                                    coverage=coverage), CFG)


def entry(outcome, rule):
    return next(e for e in outcome.policy_trace if e.rule == rule)


# ===========================================================================
# The frozen thresholds. Boundary tests below REPORT behaviour at these values;
# nothing in this file may change them.
# ===========================================================================
def test_thresholds_are_the_frozen_operating_hypotheses():
    assert (BROAD_HI, CONF_BAR, BROAD_FLOOR, BROAD_LO) == (65, 0.6, 30, 40)


# ===========================================================================
# A — precedence: rule 1 is STICKY. No later rule may reduce PRIORITY_REVIEW.
# ===========================================================================
def test_A1_exceptional_with_low_confidence_stays_priority_review():
    """The reviewer's worked example. Rule 3 fires and proposes REVIEW; rule 1
    holds. Potential may be UNKNOWN — exceptional evidence controls ATTENTION,
    not founder-quality certainty."""
    o = P(broad=45, confidence=0.40, exceptional=True)
    assert o.attention is Attention.PRIORITY_REVIEW
    assert o.potential is Potential.UNKNOWN
    assert o.fired_rules == [RULE_1, RULE_3]
    assert "preserved" in entry(o, RULE_3).preserved["attention"]
    assert RULE_1 in entry(o, RULE_3).preserved["attention"]


def test_A2_exceptional_with_low_broad_and_high_confidence_is_never_routine():
    """Rule 4 must never turn an exceptional founder ROUTINE — and it cannot,
    because 'no exceptional' is part of its own condition."""
    o = P(broad=35, confidence=0.80, exceptional=True)
    assert o.attention is Attention.PRIORITY_REVIEW
    assert entry(o, RULE_4).fired is False
    assert "exceptional evidence present" in entry(o, RULE_4).note


def test_A2b_exceptional_at_the_very_bottom_of_the_rubric_is_still_priority():
    o = P(broad=0.0, confidence=1.0, exceptional=True)
    assert o.attention is Attention.PRIORITY_REVIEW
    assert o.potential is Potential.MEDIUM   # I-2 else-completion
    assert o.recommended_action is RecommendedAction.HUMAN_REVIEW


def test_A3_exceptional_plus_missing_experience_is_orthogonal():
    """The headline recall-first output: seen, unexplained, and researched."""
    o = P(broad=45, confidence=0.40, exceptional=True, experience_incomplete=True,
          coverage=0.35)
    assert o.attention is Attention.PRIORITY_REVIEW
    assert o.data_state is DataState.NEEDS_INFORMATION
    assert o.recommended_action is RecommendedAction.RESEARCH
    assert "preserved" in entry(o, RULE_5).preserved["attention"]


@pytest.mark.parametrize("broad", [0.0, 29.99, 30, 39.99, 40, 64.99, 65, 100.0])
@pytest.mark.parametrize("conf", [0.0, 0.4, 0.599, 0.6, 1.0])
@pytest.mark.parametrize("incomplete", [False, True])
def test_A4_exceptional_ALWAYS_yields_priority_review(broad, conf, incomplete):
    """Exhaustive: across the whole input space, exceptional evidence forces
    PRIORITY_REVIEW. This is the single most important property in the system."""
    o = P(broad, conf, exceptional=True, experience_incomplete=incomplete,
          coverage=0.5 if incomplete else 1.0)
    assert o.attention is Attention.PRIORITY_REVIEW


def test_A5_attention_never_decreases_across_the_trace():
    """Structural: replay the trace and assert monotonic non-decreasing attention."""
    order = {"ROUTINE": 0, "REVIEW": 1, "PRIORITY_REVIEW": 2}
    for broad in (0, 35, 45, 70):
        for conf in (0.3, 0.7):
            for exc in (False, True):
                o = P(broad, conf, exceptional=exc)
                seen = 0
                for e in o.policy_trace:
                    if "attention" in e.sets:
                        assert order[e.sets["attention"]] >= seen
                        seen = order[e.sets["attention"]]


# ===========================================================================
# B — rule 2: high broad + sufficient confidence
# ===========================================================================
def test_B1_rule_2_sets_all_three_dimensions():
    o = P(broad=70, confidence=0.75)
    assert o.attention is Attention.PRIORITY_REVIEW
    assert o.potential is Potential.HIGH
    assert o.recommended_action is RecommendedAction.CONSIDER_ENGAGEMENT
    assert o.fired_rules == [RULE_2]


def test_B2_rule_2_yields_to_rule_5_on_action_only():
    """Rule 5 changes the ACTION and the data_state and does not touch attention.

    v2.2 Amendment 3 (guard 6): it DOES now demote HIGH to UNKNOWN. Strong
    evidence that is provably incomplete is not a claim we are entitled to make.
    Attention stays PRIORITY_REVIEW throughout — the founder is still seen."""
    o = P(broad=70, confidence=0.75, experience_incomplete=True, coverage=0.6)
    assert o.attention is Attention.PRIORITY_REVIEW
    assert o.potential is Potential.UNKNOWN
    assert o.data_state is DataState.NEEDS_INFORMATION
    assert o.recommended_action is RecommendedAction.RESEARCH
    assert entry(o, ACTION_RULE).overrode["recommended_action"] == \
        "CONSIDER_ENGAGEMENT -> RESEARCH"


def test_B3_consider_engagement_requires_rule_2_and_nothing_else_produces_it():
    """Exhaustive sweep: CONSIDER_ENGAGEMENT appears only when rule 2 fired."""
    for broad in (0, 29.99, 30, 39.99, 40, 50, 64.99, 65, 65.01, 100):
        for conf in (0.0, 0.599, 0.6, 0.601, 1.0):
            for exc, inc in itertools.product((False, True), (False, True)):
                o = P(broad, conf, exc, inc, coverage=0.5 if inc else 1.0)
                if o.recommended_action is RecommendedAction.CONSIDER_ENGAGEMENT:
                    assert RULE_2 in o.fired_rules and not inc


def test_B4_exceptional_alone_does_not_produce_consider_engagement():
    o = P(broad=50, confidence=0.9, exceptional=True)
    assert o.attention is Attention.PRIORITY_REVIEW
    assert o.recommended_action is RecommendedAction.HUMAN_REVIEW
    assert "must be SEEN" in entry(o, ACTION_RULE).note


# ===========================================================================
# C — low-confidence semantics. Uncertainty raises review, never lowers it.
# ===========================================================================
def test_C1_high_broad_low_confidence_does_not_leave_potential_high():
    """The reviewer's case: rule 2's confidence half failed, so rule 2 did not
    fire at all and cannot leave HIGH behind."""
    o = P(broad=80, confidence=0.55)
    assert o.attention is Attention.REVIEW
    assert o.potential is Potential.UNKNOWN
    assert o.potential is not Potential.HIGH
    assert o.recommended_action is RecommendedAction.HUMAN_REVIEW
    assert RULE_2 not in o.fired_rules


def test_C2_rule_3_potential_is_deterministically_unknown():
    """I-1, documented in safety.py: rule 3 is unconditionally UNKNOWN. No second
    threshold decides between UNKNOWN and MEDIUM."""
    for broad in (30, 45, 64.99, 65, 90, 100):
        o = P(broad, confidence=0.3)
        assert RULE_3 in o.fired_rules
        assert o.potential is Potential.UNKNOWN
    assert "UNKNOWN, never MEDIUM" in entry(P(45, 0.3), RULE_3).note


@pytest.mark.parametrize("broad", [0.0, 10, 29.99, 30, 40, 55, 65, 80, 100.0])
@pytest.mark.parametrize("conf", [0.0, 0.2, 0.4, 0.599])
def test_C3_low_confidence_is_never_routine(broad, conf):
    """Exhaustive over the low-confidence half-plane: uncertainty can only
    increase review pressure."""
    o = P(broad, conf)
    assert o.attention is not Attention.ROUTINE
    assert o.potential is not Potential.LOW
    assert o.recommended_action is not RecommendedAction.NO_URGENT_ACTION


def test_C4_low_broad_low_confidence_falls_to_the_else_row_not_routine():
    """Below rule 3's broad floor AND below the confidence bar: no scoring rule
    speaks, so the else row sends it to a human.

    v2.2 Amendment 3 (guard 5): potential is UNKNOWN, not MEDIUM. This is the
    former F-5 inversion removed — see test_C5."""
    o = P(broad=20, confidence=0.3)
    assert o.fired_rules == [RULE_ELSE]
    assert o.attention is Attention.REVIEW
    assert o.potential is Potential.UNKNOWN


# ===========================================================================
# D — ROUTINE / LOW safety
# ===========================================================================
def test_D1_routine_low_requires_exactly_rule_4s_conditions():
    o = P(broad=30, confidence=0.8)
    assert (o.attention, o.potential, o.recommended_action) == (
        Attention.ROUTINE, Potential.LOW, RecommendedAction.NO_URGENT_ACTION)
    assert o.fired_rules == [RULE_4]


@pytest.mark.parametrize("broad", [0.0, 20, 29.99, 30, 39.99, 40, 55, 65, 100.0])
@pytest.mark.parametrize("conf", [0.0, 0.4, 0.599, 0.6, 0.8, 1.0])
@pytest.mark.parametrize("exc", [False, True])
@pytest.mark.parametrize("inc", [False, True])
def test_D2_routine_implies_rule_4_conditions_held(broad, conf, exc, inc):
    """Exhaustive proof of the ROUTINE precondition: ROUTINE occurs only with
    broad < 40 AND confidence >= 0.6 AND no exceptional evidence."""
    o = P(broad, conf, exc, inc, coverage=0.5 if inc else 1.0)
    if o.attention is Attention.ROUTINE:
        assert broad < BROAD_LO and conf >= CONF_BAR and not exc
        assert o.potential is Potential.LOW


def test_D3_routine_and_low_are_the_same_set():
    """ROUTINE <=> LOW. Neither can occur without the other."""
    for broad in (0, 20, 39.99, 40, 60, 100):
        for conf in (0.0, 0.599, 0.6, 1.0):
            for exc, inc in itertools.product((False, True), (False, True)):
                o = P(broad, conf, exc, inc, coverage=0.5 if inc else 1.0)
                assert (o.attention is Attention.ROUTINE) == (o.potential is Potential.LOW)


def test_D4_missingness_alone_cannot_make_a_founder_routine():
    """A sparse profile: the same weak score, but the data we would need is
    absent. It must not read as 'safely low'."""
    complete = P(broad=25, confidence=0.85, experience_incomplete=False)
    sparse = P(broad=25, confidence=0.45, experience_incomplete=True, coverage=0.3)
    assert complete.attention is Attention.ROUTINE
    assert sparse.attention is Attention.REVIEW
    assert sparse.data_state is DataState.NEEDS_INFORMATION
    assert sparse.recommended_action is RecommendedAction.RESEARCH


def test_D5_needs_information_never_coexists_with_no_urgent_action():
    for broad in (0, 25, 39.99, 60, 100):
        for conf in (0.2, 0.6, 1.0):
            o = P(broad, conf, experience_incomplete=True, coverage=0.4)
            assert o.recommended_action is RecommendedAction.RESEARCH
            assert o.recommended_action is not RecommendedAction.NO_URGENT_ACTION


# ===========================================================================
# E — threshold boundaries. These tests REPORT the frozen behaviour.
#     Values were not chosen to make any case pass and are not tuned.
# ===========================================================================
@pytest.mark.parametrize("broad,expected_rule3", [
    (29.99, False), (30, True), (30.01, True)])
def test_E1_broad_30_boundary_rule_3_is_inclusive(broad, expected_rule3):
    o = P(broad, confidence=0.5)
    assert (RULE_3 in o.fired_rules) is expected_rule3
    assert o.attention is Attention.REVIEW      # either way — never ROUTINE


@pytest.mark.parametrize("broad,expected_rule4", [
    (39.99, True), (40, False), (40.01, False)])
def test_E2_broad_40_boundary_rule_4_is_strict(broad, expected_rule4):
    o = P(broad, confidence=0.8)
    assert (RULE_4 in o.fired_rules) is expected_rule4
    assert o.attention is (Attention.ROUTINE if expected_rule4 else Attention.REVIEW)
    assert o.potential is (Potential.LOW if expected_rule4 else Potential.MEDIUM)


@pytest.mark.parametrize("broad,expected_rule2", [
    (64.99, False), (65, True), (65.01, True)])
def test_E3_broad_65_boundary_rule_2_is_inclusive(broad, expected_rule2):
    o = P(broad, confidence=0.8)
    assert (RULE_2 in o.fired_rules) is expected_rule2
    assert o.attention is (Attention.PRIORITY_REVIEW if expected_rule2 else Attention.REVIEW)
    assert o.potential is (Potential.HIGH if expected_rule2 else Potential.MEDIUM)


@pytest.mark.parametrize("conf,rule2,rule3", [
    (0.599, False, True), (0.600, True, False), (0.601, True, False)])
def test_E4_confidence_0_6_boundary_is_inclusive_for_rule_2(conf, rule2, rule3):
    o = P(broad=70, confidence=conf)
    assert (RULE_2 in o.fired_rules) is rule2
    assert (RULE_3 in o.fired_rules) is rule3
    assert o.attention is (Attention.PRIORITY_REVIEW if rule2 else Attention.REVIEW)
    assert o.potential is (Potential.HIGH if rule2 else Potential.UNKNOWN)


@pytest.mark.parametrize("conf,routine", [
    (0.599, False), (0.600, True), (0.601, True)])
def test_E5_confidence_0_6_boundary_governs_routine(conf, routine):
    o = P(broad=25, confidence=conf)
    assert (o.attention is Attention.ROUTINE) is routine


def test_E6_rules_2_3_4_are_pairwise_mutually_exclusive_at_every_boundary():
    """No ordering-dependent race can exist between the potential-setting rules."""
    for broad in (0, 29.99, 30, 30.01, 39.99, 40, 40.01, 64.99, 65, 65.01, 100):
        for conf in (0.0, 0.599, 0.6, 0.601, 1.0):
            for exc in (False, True):
                fired = set(P(broad, conf, exc).fired_rules) & {RULE_2, RULE_3, RULE_4}
                assert len(fired) <= 1


# ===========================================================================
# F — recommended_action precedence
# ===========================================================================
@pytest.mark.parametrize("broad,conf,exc,inc,expected", [
    (70, 0.8, False, True, RecommendedAction.RESEARCH),           # 1 beats 2
    (25, 0.9, False, True, RecommendedAction.RESEARCH),           # 1 beats 4
    (45, 0.3, True, True, RecommendedAction.RESEARCH),            # 1 beats 3
    (70, 0.8, False, False, RecommendedAction.CONSIDER_ENGAGEMENT),  # 2
    (70, 0.8, True, False, RecommendedAction.CONSIDER_ENGAGEMENT),   # 2 with exceptional
    (45, 0.3, False, False, RecommendedAction.HUMAN_REVIEW),      # 3 via rule 3
    (50, 0.9, True, False, RecommendedAction.HUMAN_REVIEW),       # 3 via rule 1
    (50, 0.9, False, False, RecommendedAction.HUMAN_REVIEW),      # 3 via else
    (25, 0.9, False, False, RecommendedAction.NO_URGENT_ACTION),  # 4
])
def test_F1_action_precedence_matrix(broad, conf, exc, inc, expected):
    assert P(broad, conf, exc, inc, coverage=0.5 if inc else 1.0).recommended_action is expected


def test_F2_exactly_one_action_and_it_is_always_valid():
    for broad in (0, 30, 40, 65, 100):
        for conf in (0.0, 0.599, 0.6, 1.0):
            for exc, inc in itertools.product((False, True), (False, True)):
                o = P(broad, conf, exc, inc, coverage=0.5 if inc else 1.0)
                assert isinstance(o.recommended_action, RecommendedAction)
                assert o.recommended_action in set(RecommendedAction)


def test_F3_no_urgent_action_only_with_routine_and_low():
    for broad in (0, 30, 39.99, 40, 65, 100):
        for conf in (0.0, 0.6, 1.0):
            for exc, inc in itertools.product((False, True), (False, True)):
                o = P(broad, conf, exc, inc, coverage=0.5 if inc else 1.0)
                if o.recommended_action is RecommendedAction.NO_URGENT_ACTION:
                    assert o.attention is Attention.ROUTINE
                    assert o.potential is Potential.LOW
                    assert o.data_state is not DataState.NEEDS_INFORMATION


# ===========================================================================
# G — potential must NOT mirror attention
# ===========================================================================
def test_G1_priority_review_with_unknown_potential():
    o = P(broad=45, confidence=0.40, exceptional=True)
    assert (o.attention, o.potential) == (Attention.PRIORITY_REVIEW, Potential.UNKNOWN)


def test_G2_priority_review_with_medium_potential():
    o = P(broad=35, confidence=0.90, exceptional=True)
    assert (o.attention, o.potential) == (Attention.PRIORITY_REVIEW, Potential.MEDIUM)


def test_G3_review_with_three_different_potentials():
    assert P(80, 0.5).potential is Potential.UNKNOWN      # rule 3
    assert P(50, 0.9).potential is Potential.MEDIUM       # else
    seen = {(P(b, c, e).attention, P(b, c, e).potential)
            for b in (0, 35, 45, 70) for c in (0.3, 0.9) for e in (False, True)}
    # attention alone does not determine potential, and vice versa
    by_attention = {}
    for a, p in seen:
        by_attention.setdefault(a, set()).add(p)
    assert len(by_attention[Attention.PRIORITY_REVIEW]) > 1
    assert len(by_attention[Attention.REVIEW]) > 1


def test_G4_potential_is_not_a_function_of_attention_nor_attention_of_potential():
    pairs = {(P(b, c, e, i).attention, P(b, c, e, i).potential)
             for b in (0, 25, 45, 70) for c in (0.3, 0.9)
             for e in (False, True) for i in (False, True)}
    attn = {a for a, _ in pairs}
    pot = {p for _, p in pairs}
    assert len(pairs) > max(len(attn), len(pot))   # neither is a function of the other


# ===========================================================================
# H — data_state (approved clarification)
# ===========================================================================
def test_H1_complete_and_clean_is_sufficient():
    o = P(broad=50, confidence=1.0, coverage=1.0)
    assert o.data_state is DataState.SUFFICIENT


def test_H2_complete_but_contradictory_is_sufficient_with_lower_confidence():
    """Contradictions reduce confidence; they do NOT by themselves make a
    profile PARTIAL. The dimensions stay orthogonal."""
    o = P(broad=50, confidence=0.55, coverage=1.0)
    assert o.data_state is DataState.SUFFICIENT
    assert o.attention is Attention.REVIEW     # the low confidence still raises review
    assert o.potential is Potential.UNKNOWN


def test_H3_some_decision_relevant_fields_absent_is_partial():
    o = P(broad=50, confidence=0.85, experience_incomplete=False, coverage=0.82)
    assert o.data_state is DataState.PARTIAL


def test_H4_missing_experience_is_needs_information():
    o = P(broad=50, confidence=0.5, experience_incomplete=True, coverage=0.45)
    assert o.data_state is DataState.NEEDS_INFORMATION
    assert o.recommended_action is RecommendedAction.RESEARCH


def test_H5_needs_information_outranks_the_coverage_ladder():
    o = P(broad=50, confidence=0.9, experience_incomplete=True, coverage=1.0)
    assert o.data_state is DataState.NEEDS_INFORMATION


def test_H6_data_state_is_independent_of_confidence_given_coverage():
    """Same coverage, wildly different confidence -> same data_state."""
    for cov, expected in ((1.0, DataState.SUFFICIENT), (0.7, DataState.PARTIAL)):
        states = {P(50, c, coverage=cov).data_state for c in (0.05, 0.3, 0.6, 0.95, 1.0)}
        assert states == {expected}


# ===========================================================================
# I — policy trace: no silent precedence
# ===========================================================================
def test_I1_every_rule_appears_in_the_trace_in_order():
    o = P(broad=45, confidence=0.4, exceptional=True, experience_incomplete=True, coverage=0.4)
    rules = [e.rule for e in o.policy_trace]
    assert rules == [RULE_1, RULE_2, RULE_3, RULE_4, RULE_5, RULE_ELSE,
                     DATA_STATE_RULE, GUARD_4, GUARD_5, GUARD_6, GUARD_8, ACTION_RULE]


def test_I2_every_fired_rule_records_condition_evidence_and_dimensions():
    o = P(broad=45, confidence=0.4, exceptional=True, experience_incomplete=True, coverage=0.4)
    for e in o.policy_trace:
        assert e.condition and e.evidence
        if e.fired:
            assert e.sets or e.preserved, f"{e.rule} fired but recorded no dimension effect"


def test_I3_non_fires_carry_a_stated_reason():
    o = P(broad=50, confidence=0.9)
    for e in o.policy_trace:
        if not e.fired:
            assert e.note, f"{e.rule} did not fire and gave no reason"


def test_I4_preservation_names_the_rule_that_holds_the_dimension():
    o = P(broad=45, confidence=0.4, exceptional=True)
    assert RULE_1 in entry(o, RULE_3).preserved["attention"]
    assert "ratchet" in entry(o, RULE_3).preserved["attention"]


def test_I5_override_is_recorded_with_from_and_to():
    o = P(broad=70, confidence=0.8)
    assert entry(o, RULE_2).overrode["attention"] == "ROUTINE -> PRIORITY_REVIEW"


def test_I6_the_trace_explains_the_final_state_of_every_dimension():
    """For every input, each of the four dimensions is either `set` by some
    trace entry or explicitly `preserved` by one. Nothing appears from nowhere."""
    for broad in (0, 25, 45, 70):
        for conf in (0.3, 0.9):
            for exc, inc in itertools.product((False, True), (False, True)):
                o = P(broad, conf, exc, inc, coverage=0.5 if inc else 1.0)
                final = {"attention": o.attention.value, "potential": o.potential.value,
                         "data_state": o.data_state.value,
                         "recommended_action": o.recommended_action.value}
                for dim, value in final.items():
                    assert any(e.sets.get(dim) == value for e in o.policy_trace), \
                        f"{dim}={value} never appears as `sets` in the trace"


# ===========================================================================
# K — no human authority (policy layer). See test_assessment.py for the
#     serialized-output and module-wide sweep.
# ===========================================================================
def test_K1_the_action_vocabulary_is_exactly_the_four_permitted_values():
    assert {a.value for a in RecommendedAction} == {
        "CONSIDER_ENGAGEMENT", "HUMAN_REVIEW", "RESEARCH", "NO_URGENT_ACTION"}


def test_K2_no_action_value_is_the_word_engage():
    """Semantic, not substring: CONSIDER_ENGAGEMENT is permitted; the bare
    imperative `Engage` is a human disposition and must not exist."""
    for a in RecommendedAction:
        assert a.value.strip().upper() != "ENGAGE"
        assert a.name.strip().upper() != "ENGAGE"


def test_K3_the_policy_module_defines_no_decision_or_stage_vocabulary():
    import app.policy.dimensions as dims
    import app.policy.safety as safety
    for module in (dims, safety):
        names = {n.upper() for n in vars(module)}
        assert "DECISION" not in names and "STAGE" not in names
    human_dispositions = {"NEEDS_REVIEW", "POTENTIAL", "NOT_NOW"}
    human_stages = {"NEW", "ASSESSMENT", "NURTURING", "KEEP_WARM", "DEAL", "CLOSED"}
    machine_values = ({a.value for a in RecommendedAction} | {a.value for a in Attention}
                      | {p.value for p in Potential} | {d.value for d in DataState})
    assert not (machine_values & human_stages)
    assert not (machine_values & (human_dispositions - {"POTENTIAL"}))


# ===========================================================================
# v2.3 Amendment 4 — potential = LOW requires sufficient evidence.
#
# LOW asserts "we had enough to assess this founder and found little". On
# incomplete data we are not entitled to the first half. The asymmetry with
# HIGH/MEDIUM is deliberate: incomplete evidence cannot support a NEGATIVE
# conclusion, because the missing part is exactly where the positive evidence
# would have been — but what WAS observed was still observed.
# ===========================================================================

def test_v23_case1_sufficient_and_weak_is_the_only_low():
    o = P(broad=25, confidence=0.85, coverage=1.0)
    assert (o.attention, o.potential, o.data_state, o.recommended_action) == (
        Attention.ROUTINE, Potential.LOW, DataState.SUFFICIENT,
        RecommendedAction.NO_URGENT_ACTION)
    assert entry(o, GUARD_8).fired is False


def test_v23_case2_partial_with_the_same_score_is_unknown_not_low():
    o = P(broad=25, confidence=0.85, coverage=0.85)
    assert (o.attention, o.potential, o.data_state, o.recommended_action) == (
        Attention.REVIEW, Potential.UNKNOWN, DataState.PARTIAL,
        RecommendedAction.HUMAN_REVIEW)
    assert entry(o, GUARD_8).overrode["potential"] == "LOW -> UNKNOWN"


def test_v23_case3_needs_information_is_unknown_and_research():
    o = P(broad=25, confidence=0.85, experience_incomplete=True, coverage=0.7)
    assert (o.attention, o.potential, o.data_state, o.recommended_action) == (
        Attention.REVIEW, Potential.UNKNOWN, DataState.NEEDS_INFORMATION,
        RecommendedAction.RESEARCH)


def test_v23_case4_partial_does_not_erase_a_supported_positive_conclusion():
    """The PARTIAL attention floor must not cost rule 2 its conclusion."""
    o = P(broad=70, confidence=0.8, coverage=0.85)
    assert (o.attention, o.potential, o.data_state, o.recommended_action) == (
        Attention.PRIORITY_REVIEW, Potential.HIGH, DataState.PARTIAL,
        RecommendedAction.CONSIDER_ENGAGEMENT)


def test_v23_case5_partial_does_not_globally_force_unknown():
    o = P(broad=50, confidence=0.8, coverage=0.85)
    assert (o.attention, o.potential, o.data_state) == (
        Attention.REVIEW, Potential.MEDIUM, DataState.PARTIAL)


def test_v23_case6_exceptional_plus_partial_is_priority_but_not_manufactured_high():
    """Exceptional evidence controls ATTENTION. It does not invent HIGH."""
    o = P(broad=25, confidence=0.85, exceptional=True, coverage=0.85)
    assert o.attention is Attention.PRIORITY_REVIEW
    assert o.potential is Potential.MEDIUM
    assert o.potential is not Potential.HIGH


@pytest.mark.parametrize("broad", [0.0, 10, 25, 29.99, 30, 39.99, 40, 50, 65, 100.0])
@pytest.mark.parametrize("conf", [0.0, 0.4, 0.599, 0.6, 0.85, 1.0])
@pytest.mark.parametrize("cov", [0.4, 0.85, 1.0])
@pytest.mark.parametrize("exc", [False, True])
def test_v23_low_implies_all_four_conditions(broad, conf, cov, exc):
    """Exhaustive: the LOW invariant, proved over the whole input space."""
    for inc in (False, True):
        o = P(broad, conf, exc, inc, coverage=cov)
        if o.potential is Potential.LOW:
            assert o.data_state is DataState.SUFFICIENT
            assert conf >= CONF_BAR
            assert broad < BROAD_LO
            assert not exc


def test_v23_low_never_coexists_with_partial_or_needs_information():
    for broad in (0, 20, 25, 39.99, 50, 70):
        for conf in (0.3, 0.6, 0.85, 1.0):
            for cov in (0.3, 0.7, 0.9, 1.0):
                for inc in (False, True):
                    o = P(broad, conf, False, inc, coverage=cov)
                    if o.data_state is not DataState.SUFFICIENT:
                        assert o.potential is not Potential.LOW


def test_v23_partial_preserves_high_and_medium_but_not_low():
    """The asymmetry, stated as one test."""
    assert P(70, 0.8, coverage=0.85).potential is Potential.HIGH
    assert P(50, 0.8, coverage=0.85).potential is Potential.MEDIUM
    assert P(25, 0.8, coverage=0.85).potential is Potential.UNKNOWN   # not LOW
    assert P(25, 0.8, coverage=1.0).potential is Potential.LOW


def test_v23_guard_8_appears_in_the_trace_before_the_action_rule():
    o = P(broad=25, confidence=0.85, coverage=0.85)
    rules = [e.rule for e in o.policy_trace]
    assert rules.index(GUARD_8) < rules.index(ACTION_RULE)
    assert rules.index(GUARD_4) < rules.index(GUARD_8)


def test_v23_routine_still_requires_sufficient_evidence():
    for broad in (0, 20, 39.99, 50, 70):
        for conf in (0.3, 0.6, 1.0):
            for cov in (0.3, 0.85, 1.0):
                for exc, inc in itertools.product((False, True), (False, True)):
                    o = P(broad, conf, exc, inc, coverage=cov)
                    if o.attention is Attention.ROUTINE:
                        assert o.data_state is DataState.SUFFICIENT
                        assert o.potential is Potential.LOW
