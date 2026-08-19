"""The ordered safety policy — PLAN §4.5, implemented exactly as the frozen table.

    | # | Condition                                  | Sets                                       |
    | 1 | Exceptional signal present                 | attention = PRIORITY_REVIEW                |
    | 2 | broad >= 65 and confidence >= 0.6          | PRIORITY_REVIEW; HIGH; CONSIDER_ENGAGEMENT |
    | 3 | confidence < 0.6 and broad >= 30           | REVIEW; UNKNOWN/MEDIUM; HUMAN_REVIEW       |
    | 4 | broad < 40, confidence >= 0.6, no exceptional | ROUTINE; LOW; NO_URGENT_ACTION           |
    | 5 | Experience history missing/incomplete      | NEEDS_INFORMATION; RESEARCH (no lowering)  |
    | – | Else                                       | REVIEW; MEDIUM                             |

This module is a PURE FUNCTION of five numbers/booleans. It never sees a
profile, so a policy test can state a founder as `broad=45, confidence=0.40,
exceptional=True` and mean exactly that, with no scorer in the loop to argue
with. Thresholds come from config; not one is written here.

Three properties are structural, not incidental — each is proved by test:

* **Attention ratchets.** Rules propose; `_raise` only ever moves attention up
  the recall-first ordering. Rule 1's PRIORITY_REVIEW is therefore sticky by
  construction: no later rule can express "lower it", because no such operation
  exists in this module.
* **Potential is assigned at most once.** Rules 2, 3 and 4 are pairwise mutually
  exclusive on their own conditions (2 vs 3 and 3 vs 4 disagree about
  confidence; 2 vs 4 disagree about broad), so there is no ordering-dependent
  race between them, and the `else` row exists to complete the assignment.
* **Nothing is silent.** Every rule appends a trace entry whether it fired or
  not, and a rule that proposed a dimension which a higher-precedence rule
  already holds records that as `preserved`, naming the rule that holds it.

THREE INTERPRETATIONS are recorded here because the frozen table leaves them
open. All three were confirmed with the reviewer before implementation; none
introduces a threshold.

**I-1 — rule 3 sets `potential = UNKNOWN`, always.** The table permits
"UNKNOWN/MEDIUM". Rule 3's whole trigger is that confidence is below the bar at
which we are willing to make a claim, and `MEDIUM` *is* a claim — it asserts mid
founder quality. `UNKNOWN` asserts nothing. **v2.2 generalises this into safety
guard 5**: I-1's reasoning applied only where rule 3 reached, i.e. broad >= 30,
which produced the v2.1 F-5 inversion (29.99 at confidence 0.5 asserted MEDIUM
while 30.00 asserted UNKNOWN — a higher score making a *more* committed claim on
identically untrustworthy evidence). Guard 5 now applies the same reasoning
across the whole score range, using the same 0.6 threshold. Rule 3 is unchanged.

**I-2 — the `else` row is the potential-completion rule.** It fires when none of
rules 2–4 assigned a `potential`. Rules 1 and 5 do not assign one (rule 1 speaks
only about attention, rule 5 only about data_state/action), so an exceptional
founder whose numbers match no scoring rule still lands `MEDIUM` — and, because
attention only ratchets, still `PRIORITY_REVIEW`. Reading the `else` as "no rule
at all fired" would leave such a founder with no `potential`, which the output
contract forbids.

**I-3' — "experience history missing/incomplete" is the §4.3
`experience_history.history_depth` SUB-component being below 1.0** — i.e. zero
roles (missing) or exactly one role (incomplete: it tells us where the person is,
not how they got there). v2.2 Amendment 1 enriched the `experience_history`
component with `seniority_readability` and `tenure_readability`, so the condition
is pinned to the depth sub-component specifically. Without that pin, a two-role
history with no `management_level` would start reporting itself as a *missing
history*, which it is not. The same sub-component drives
`data_state = NEEDS_INFORMATION`, so rule 5 and the data_state ladder cannot
disagree.

------------------------------------------------------------------------------
PLAN v2.2 AMENDMENTS (semantic/evaluation only; thresholds, weights, detectors,
archetypes, workflow, architecture and LLM rules are all unchanged).

The ordered rules 1-5 and the `else` row are v2.1 VERBATIM. The amendments are
applied afterwards as GUARDS, because each is a floor or an override on the
result rather than another scoring rule.

* **Guard 4 (Amendment 2) — incomplete data creates an attention floor.**
  `data_state in {PARTIAL, NEEDS_INFORMATION}` forces `attention >= REVIEW`, so
  `ROUTINE + PARTIAL` and `ROUTINE + NEEDS_INFORMATION` become unreachable and
  PRIORITY_REVIEW is untouched. On the action side, PARTIAL promotes
  NO_URGENT_ACTION to HUMAN_REVIEW while preserving stronger actions such as
  CONSIDER_ENGAGEMENT. **This changes what ROUTINE MEANS**: it is now the
  positive assertion that there is sufficient evidence to be comfortable not
  prioritising this founder, rather than the absence of a reason to look.
* **Guard 5 (Amendment 3) — `confidence < 0.6` forces `potential = UNKNOWN`**,
  regardless of broad score, reusing the existing threshold.
* **Guard 6 (Amendment 3) — `data_state == NEEDS_INFORMATION` forces
  `potential = UNKNOWN`.** This can override rule 2's HIGH: strong evidence that
  is provably incomplete is still not a claim we are entitled to make. Attention
  is untouched, so `PRIORITY_REVIEW + UNKNOWN` is a normal, expected output.
* **Guard 8 (v2.3 Amendment 4) — `potential = LOW` requires sufficient evidence.**
  LOW is valid only when `data_state == SUFFICIENT` and `confidence >= 0.6` and
  `broad < 40` and there is no exceptional evidence. `PARTIAL` + otherwise-LOW
  becomes UNKNOWN (attention already floored at REVIEW by guard 4, action
  HUMAN_REVIEW). **PARTIAL does NOT globally force UNKNOWN**: HIGH and MEDIUM
  survive incomplete minor data. The asymmetry is deliberate — incomplete
  evidence cannot support a NEGATIVE conclusion, because the missing part is
  exactly where the positive evidence would have been, but what was observed
  was still observed.
* **Guard 7 (ordering) — ROUTINE is valid only when** there is no exceptional
  floor, confidence >= 0.6, `data_state == SUFFICIENT`, and broad < 40 under the
  existing rule 4. Asserted at the end of every evaluation.

**Product definition of LOW (v2.3):** the system had sufficient decision-relevant
evidence, confidence was at least the operating threshold, no exceptional
evidence required escalation, and currently observable positive evidence was
weak. LOW is a conclusion, not a default.

**F-6, accepted at v2.3 (no code change).** Deleting the field that CARRIES a
contradiction can legitimately RAISE confidence, because the remaining record
becomes internally consistent. Confidence is therefore NOT globally monotonic
under deletion, and is not required to be. Recall safety is enforced separately
and structurally — through evidence coverage, `data_state`, and the attention
floor. The required monotonic safety property is the one that is actually about
safety: **missing data must never make a founder easier to silently dismiss**,
i.e. zero PRIORITY_REVIEW/REVIEW -> ROUTINE transitions under ablation.

Amendment 1 lives in `evidence/confidence.py`: the seven coverage weights are
unchanged, but each component now measures the availability of the evidence a
dimension needs. Together with guard 4 this is what makes the missing-data
property hold — losing any decision-relevant family lowers coverage, which makes
the profile PARTIAL, which floors attention at REVIEW.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.policy.dimensions import (ATTENTION_ORDER, Attention, DataState,
                                   Potential, RecommendedAction)

RULE_1 = "rule_1_exceptional"
RULE_2 = "rule_2_high_broad_sufficient_confidence"
RULE_3 = "rule_3_low_confidence"
RULE_4 = "rule_4_low_broad_sufficient_confidence"
RULE_5 = "rule_5_missing_experience"
RULE_ELSE = "rule_else_default"
DATA_STATE_RULE = "data_state_ladder"
GUARD_4 = "guard_4_incomplete_data_attention_floor"     # v2.2 Amendment 2
GUARD_5 = "guard_5_low_confidence_potential_unknown"    # v2.2 Amendment 3
GUARD_6 = "guard_6_needs_information_potential_unknown"  # v2.2 Amendment 3
GUARD_8 = "guard_8_low_requires_sufficient_evidence"     # v2.3 Amendment 4
ACTION_RULE = "recommended_action_precedence"

FLOOR_OWNER = "(floor — no rule has spoken yet)"

RULE_ORDER = [RULE_1, RULE_2, RULE_3, RULE_4, RULE_5, RULE_ELSE]


@dataclass(frozen=True)
class PolicyInput:
    """Everything the policy is allowed to know. Deliberately five scalars."""

    broad_score: float
    confidence: float
    exceptional: bool
    experience_incomplete: bool   # I-3
    coverage: float               # §4.3 decision-relevant coverage, 0–1

    @property
    def exceptional_reason(self) -> str:
        """Human-readable evidence string for rule 1's trace entry."""
        return "exceptional evidence present" if self.exceptional else "no exceptional evidence"


@dataclass
class PolicyTraceEntry:
    """One rule's evaluation. `fired` is recorded for non-fires too, so
    "why is this founder NOT priority?" is answerable from the same object."""

    rule: str
    fired: bool
    condition: str
    evidence: str
    sets: dict[str, str] = field(default_factory=dict)
    overrode: dict[str, str] = field(default_factory=dict)   # dim -> "FROM -> TO"
    preserved: dict[str, str] = field(default_factory=dict)  # dim -> why it was not changed
    note: str = ""

    def to_dict(self) -> dict:
        """JSON form for the API and the UI's "why this assessment?" panel."""
        return {"rule": self.rule, "fired": self.fired, "condition": self.condition,
                "evidence": self.evidence, "sets": self.sets, "overrode": self.overrode,
                "preserved": self.preserved, "note": self.note}


@dataclass
class PolicyOutcome:
    """The four dimensions plus the complete trace that produced them.

    `policy_trace` holds an entry for EVERY rule, fired or not, so the question
    "why is this founder not priority?" is answerable from the outcome alone
    without re-running the policy."""

    attention: Attention
    potential: Potential
    data_state: DataState
    recommended_action: RecommendedAction
    policy_trace: list[PolicyTraceEntry]
    fired_rules: list[str]

    def to_dict(self) -> dict:
        """JSON form; enums are flattened to their string values."""
        return {"attention": self.attention.value, "potential": self.potential.value,
                "data_state": self.data_state.value,
                "recommended_action": self.recommended_action.value,
                "fired_rules": list(self.fired_rules),
                "policy_trace": [e.to_dict() for e in self.policy_trace]}


def apply_policy(inp: PolicyInput, cfg) -> PolicyOutcome:
    """Run the six ordered rules and return the four dimensions plus the trace.

    Pure: no I/O, no profile, no persistence, no clock. Thresholds are read
    from `cfg` and none is written here, so re-tuning is a config change.

    Invariants held by construction, not by discipline:

    * `attention` only ever ratchets UP (`raise_attention` has no lowering
      branch), so incomplete data can raise a founder into REVIEW but can never
      demote one into ROUTINE;
    * `potential` is assigned at most once (rules 2/3/4 are pairwise mutually
      exclusive), so there is no ordering-dependent race;
    * rule 5 sets `data_state` only — a missing history is reported, never
      converted into negative evidence about the person."""
    t = cfg.thresholds
    broad_hi = t["priority_broad"]                 # 65
    conf_bar = t["priority_confidence"]            # 0.6
    broad_floor = t["low_confidence_floor_broad"]  # 30
    broad_lo = t["routine_broad"]                  # 40

    trace: list[PolicyTraceEntry] = []
    fired: list[str] = []

    # `attention` starts at the ROUTINE floor. This is NOT a decision that the
    # founder is routine — it is the bottom of the ratchet, and every path below
    # either raises it or (rule 4 only) affirms it against an explicit condition.
    attention = Attention.ROUTINE
    attention_owner = FLOOR_OWNER
    potential: Potential | None = None
    potential_owner = ""

    def raise_attention(entry: PolicyTraceEntry, proposed: Attention) -> None:
        """The ratchet. Raises attention, affirms the floor, or records why the
        proposal was preserved-against — but never lowers. There is deliberately
        no code path here that moves attention down the ordering."""
        nonlocal attention, attention_owner
        if ATTENTION_ORDER[proposed] > ATTENTION_ORDER[attention]:
            entry.overrode["attention"] = f"{attention.value} -> {proposed.value}"
            entry.sets["attention"] = proposed.value
            attention, attention_owner = proposed, entry.rule
        elif proposed is attention and attention_owner is FLOOR_OWNER:
            # Rule 4 proposing ROUTINE is the only case: it does not RAISE
            # attention, it AFFIRMS the floor against an explicit condition, and
            # it takes ownership so the trace can say which rule stands behind
            # the final value. Without this, ROUTINE would be the one outcome no
            # trace entry claimed.
            entry.sets["attention"] = proposed.value
            attention_owner = entry.rule
        elif proposed is attention:
            entry.preserved["attention"] = (
                f"{attention.value} already held by {attention_owner}; this rule proposes "
                f"the same value")
        else:
            entry.preserved["attention"] = (
                f"proposed {proposed.value} but {attention.value} is preserved — set by the "
                f"higher-precedence {attention_owner}; attention is a ratchet and is never "
                f"lowered")

    def set_potential(entry: PolicyTraceEntry, proposed: Potential) -> None:
        """First writer wins. Reaching the `else` would mean two of rules 2/3/4
        fired together, which their conditions make impossible (test-proved)."""
        nonlocal potential, potential_owner
        if potential is None:
            entry.sets["potential"] = proposed.value
            potential, potential_owner = proposed, entry.rule
        else:  # unreachable: rules 2/3/4 are pairwise mutually exclusive (test-proved)
            entry.preserved["potential"] = (
                f"{potential.value} preserved — set by {potential_owner}")

    # ------------------------------------------------------------ rule 1
    e1 = PolicyTraceEntry(
        rule=RULE_1, fired=inp.exceptional,
        condition="exceptional signal present",
        evidence=inp.exceptional_reason)
    if inp.exceptional:
        fired.append(RULE_1)
        raise_attention(e1, Attention.PRIORITY_REVIEW)
        e1.note = ("Exceptional evidence controls ATTENTION only. It deliberately makes no "
                   "claim about founder potential — see something rare, look at it.")
    else:
        e1.note = "No dimension set."
    trace.append(e1)

    # ------------------------------------------------------------ rule 2
    cond2 = inp.broad_score >= broad_hi and inp.confidence >= conf_bar
    e2 = PolicyTraceEntry(
        rule=RULE_2, fired=cond2,
        condition=f"broad_score >= {broad_hi} AND confidence >= {conf_bar}",
        evidence=f"broad_score={inp.broad_score}, confidence={inp.confidence}")
    if cond2:
        fired.append(RULE_2)
        raise_attention(e2, Attention.PRIORITY_REVIEW)
        set_potential(e2, Potential.HIGH)
        e2.note = ("Both halves hold: the evidence is strong AND we trust it. This is the only "
                   "rule that can produce CONSIDER_ENGAGEMENT.")
    else:
        why = []
        if inp.broad_score < broad_hi:
            why.append(f"broad_score {inp.broad_score} < {broad_hi}")
        if inp.confidence < conf_bar:
            why.append(f"confidence {inp.confidence} < {conf_bar}")
        e2.note = "Not fired: " + "; ".join(why) + ". No dimension set."
    trace.append(e2)

    # ------------------------------------------------------------ rule 3
    cond3 = inp.confidence < conf_bar and inp.broad_score >= broad_floor
    e3 = PolicyTraceEntry(
        rule=RULE_3, fired=cond3,
        condition=f"confidence < {conf_bar} AND broad_score >= {broad_floor}",
        evidence=f"broad_score={inp.broad_score}, confidence={inp.confidence}")
    if cond3:
        fired.append(RULE_3)
        raise_attention(e3, Attention.REVIEW)
        set_potential(e3, Potential.UNKNOWN)
        e3.note = ("I-1: potential is UNKNOWN, never MEDIUM. The trigger is that the evidence "
                   "is not trustworthy enough to make a claim, and MEDIUM is a claim.")
    else:
        e3.note = "Not fired. No dimension set."
    trace.append(e3)

    # ------------------------------------------------------------ rule 4
    cond4 = (inp.broad_score < broad_lo and inp.confidence >= conf_bar
             and not inp.exceptional)
    e4 = PolicyTraceEntry(
        rule=RULE_4, fired=cond4,
        condition=f"broad_score < {broad_lo} AND confidence >= {conf_bar} AND no exceptional",
        evidence=(f"broad_score={inp.broad_score}, confidence={inp.confidence}, "
                  f"exceptional={inp.exceptional}"))
    if cond4:
        fired.append(RULE_4)
        raise_attention(e4, Attention.ROUTINE)   # affirms the floor; cannot lower
        set_potential(e4, Potential.LOW)
        e4.note = ("The ONLY route to ROUTINE/LOW: weak evidence that we positively trust, and "
                   "nothing exceptional. Still visible in the queue, never hidden.")
    else:
        why = []
        if inp.broad_score >= broad_lo:
            why.append(f"broad_score {inp.broad_score} >= {broad_lo}")
        if inp.confidence < conf_bar:
            why.append(f"confidence {inp.confidence} < {conf_bar} — uncertainty must not read "
                       f"as ROUTINE")
        if inp.exceptional:
            why.append("exceptional evidence present — an exceptional founder can never be "
                       "ROUTINE")
        e4.note = "Not fired: " + "; ".join(why) + ". No dimension set."
    trace.append(e4)

    # ------------------------------------------------------------ rule 5
    e5 = PolicyTraceEntry(
        rule=RULE_5, fired=inp.experience_incomplete,
        condition="experience history missing or incomplete (I-3: §4.3 coverage component "
                  "`experience_history` < 1.0, i.e. zero or one role)",
        evidence=f"experience_incomplete={inp.experience_incomplete}, coverage={inp.coverage}")
    data_state = DataState.SUFFICIENT
    if inp.experience_incomplete:
        fired.append(RULE_5)
        data_state = DataState.NEEDS_INFORMATION
        e5.sets["data_state"] = DataState.NEEDS_INFORMATION.value
        e5.sets["recommended_action"] = RecommendedAction.RESEARCH.value
        e5.preserved["attention"] = (
            f"{attention.value} preserved — rule 5 sets data_state and action only and is "
            f"structurally incapable of lowering attention")
        e5.preserved["potential"] = (
            f"{potential.value if potential else 'unassigned'} preserved — missing data is not "
            f"negative evidence (PLAN §1)")
        e5.note = ("Orthogonality is the whole point: this founder may be PRIORITY_REVIEW and "
                   "NEEDS_INFORMATION simultaneously.")
    else:
        e5.note = "Not fired: experience history is present and multi-role."
    trace.append(e5)

    # ------------------------------------------------------------ else
    eE = PolicyTraceEntry(
        rule=RULE_ELSE, fired=potential is None,
        condition="I-2: no scoring rule (2, 3, 4) assigned a potential",
        evidence=f"potential after rules 2-4 = {potential.value if potential else 'unassigned'}")
    if potential is None:
        fired.append(RULE_ELSE)
        raise_attention(eE, Attention.REVIEW)
        set_potential(eE, Potential.MEDIUM)
        eE.note = ("Default completion. Every assessment must carry a potential; the middle of "
                   "the rubric with no rule to speak for it is MEDIUM and goes to a human.")
    else:
        eE.note = f"Not fired: potential already {potential.value}."
    trace.append(eE)

    assert potential is not None  # I-2 guarantees completion

    # -------------------------------------------------- data_state ladder
    # Approved clarification. Orthogonal to confidence by construction: this
    # reads COVERAGE, which contradiction and inference penalties do not touch.
    ds = PolicyTraceEntry(
        rule=DATA_STATE_RULE, fired=True,
        condition="experience missing/incomplete -> NEEDS_INFORMATION; else coverage < 1.0 -> "
                  "PARTIAL; else SUFFICIENT",
        evidence=f"experience_incomplete={inp.experience_incomplete}, coverage={inp.coverage}")
    if data_state is not DataState.NEEDS_INFORMATION:
        data_state = DataState.PARTIAL if inp.coverage < 1.0 else DataState.SUFFICIENT
        ds.sets["data_state"] = data_state.value
        ds.note = ("Reads decision-relevant COVERAGE, not confidence: contradictions and "
                   "inferences reduce confidence but do not by themselves make a profile "
                   "PARTIAL when the relevant data is present.")
    else:
        ds.preserved["data_state"] = f"NEEDS_INFORMATION preserved — set by {RULE_5}"
        ds.note = "NEEDS_INFORMATION outranks the coverage ladder."
    trace.append(ds)

    # ============================ v2.2 SAFETY GUARDS ========================
    # The ordered rules above are PLAN v2.1 verbatim and are unchanged. The
    # guards below are the v2.2 amendments, applied AFTER the rules because each
    # is a floor or an override on the result, not another scoring rule. None
    # introduces a threshold: guard 5 reuses the existing 0.6.

    # --- Guard 4 (Amendment 2): incomplete data creates an attention floor ---
    # New product meaning: ROUTINE now asserts something positive — that there
    # is SUFFICIENT evidence to be comfortable NOT prioritising this founder.
    # A profile we have not finished reading can no longer earn that.
    g4 = PolicyTraceEntry(
        rule=GUARD_4, fired=data_state in (DataState.PARTIAL, DataState.NEEDS_INFORMATION),
        condition="data_state in {PARTIAL, NEEDS_INFORMATION} -> attention floor REVIEW",
        evidence=f"data_state={data_state.value}, attention before guard={attention.value}")
    if g4.fired:
        raise_attention(g4, Attention.REVIEW)
        g4.note = ("ROUTINE means 'enough evidence to be comfortable not prioritising this "
                   "founder'. Incomplete data cannot support that claim. PRIORITY_REVIEW is "
                   "untouched — this is a floor, never a ceiling.")
    else:
        g4.note = "Not fired: data_state is SUFFICIENT, so no floor applies."
    trace.append(g4)

    # --- Guard 5 (Amendment 3): low confidence => potential UNKNOWN ----------
    # Removes the v2.1 F-5 inversion, in which broad 29.99 at confidence 0.5 was
    # asserted MEDIUM (a claim) while broad 30.00 at the same confidence was
    # UNKNOWN (no claim) — a higher score producing a LESS committed potential.
    # Now every sub-0.6 profile is UNKNOWN regardless of score.
    g5 = PolicyTraceEntry(
        rule=GUARD_5, fired=inp.confidence < conf_bar,
        condition=f"confidence < {conf_bar} -> potential = UNKNOWN (regardless of broad_score)",
        evidence=f"confidence={inp.confidence}, potential before guard={potential.value}")
    if g5.fired:
        if potential is not Potential.UNKNOWN:
            g5.overrode["potential"] = f"{potential.value} -> {Potential.UNKNOWN.value}"
        g5.sets["potential"] = Potential.UNKNOWN.value
        g5.preserved["attention"] = (
            f"{attention.value} preserved — potential and attention are orthogonal; "
            f"uncertainty refuses to make a claim, it does not reduce urgency")
        potential, potential_owner = Potential.UNKNOWN, GUARD_5
        g5.note = ("Reuses the existing 0.6 threshold. Below it we do not trust the evidence "
                   "enough to assert any founder-quality band, including MEDIUM.")
    else:
        g5.note = f"Not fired: confidence {inp.confidence} >= {conf_bar}."
    trace.append(g5)

    # --- Guard 6 (Amendment 3): NEEDS_INFORMATION => potential UNKNOWN ------
    g6 = PolicyTraceEntry(
        rule=GUARD_6, fired=data_state is DataState.NEEDS_INFORMATION,
        condition="data_state == NEEDS_INFORMATION -> potential = UNKNOWN",
        evidence=f"data_state={data_state.value}, potential before guard={potential.value}")
    if g6.fired:
        if potential is not Potential.UNKNOWN:
            g6.overrode["potential"] = f"{potential.value} -> {Potential.UNKNOWN.value}"
        g6.sets["potential"] = Potential.UNKNOWN.value
        g6.preserved["attention"] = (
            f"{attention.value} preserved — missing history is not negative evidence")
        potential, potential_owner = Potential.UNKNOWN, GUARD_6
        g6.note = ("We cannot assert a founder-quality band from a history we have not read. "
                   "Note this can override rule 2's HIGH: strong evidence that is provably "
                   "incomplete is still not a claim we are entitled to make.")
    else:
        g6.note = "Not fired."
    trace.append(g6)

    # --- Guard 8 (v2.3 Amendment 4): LOW requires sufficient evidence -------
    # A machine LOW claim asserts "we had enough to assess this founder and the
    # observable positive evidence was weak". On incomplete data we are not
    # entitled to the first half, so the claim collapses to UNKNOWN.
    #
    # The asymmetry with HIGH/MEDIUM is deliberate, not an inconsistency:
    # incomplete evidence cannot SUPPORT a negative conclusion, because the
    # missing part is exactly where the positive evidence would have been. It
    # can still leave a positive conclusion standing, because what was observed
    # was observed. PARTIAL therefore does not globally force UNKNOWN.
    g8 = PolicyTraceEntry(
        rule=GUARD_8, fired=(potential is Potential.LOW
                             and data_state is not DataState.SUFFICIENT),
        condition="potential == LOW AND data_state != SUFFICIENT -> potential = UNKNOWN",
        evidence=f"potential={potential.value}, data_state={data_state.value}")
    if g8.fired:
        g8.overrode["potential"] = f"{Potential.LOW.value} -> {Potential.UNKNOWN.value}"
        g8.sets["potential"] = Potential.UNKNOWN.value
        g8.preserved["attention"] = (
            f"{attention.value} preserved — guard 4 already floors incomplete data at REVIEW")
        potential, potential_owner = Potential.UNKNOWN, GUARD_8
        g8.note = ("LOW would have claimed we assessed this founder and found little. We did "
                   "not finish reading them. Incomplete evidence cannot support a negative "
                   "conclusion; strong observed positive evidence can still support HIGH/MEDIUM.")
    elif potential is Potential.LOW:
        g8.note = "Not fired: LOW is backed by SUFFICIENT data."
    else:
        g8.note = f"Not fired: potential is {potential.value}, not LOW."
    trace.append(g8)

    # ------------------------------------------- recommended_action precedence
    if data_state is DataState.NEEDS_INFORMATION:
        action, why = RecommendedAction.RESEARCH, f"1. NEEDS_INFORMATION ({RULE_5})"
    elif RULE_2 in fired:
        action, why = RecommendedAction.CONSIDER_ENGAGEMENT, f"2. {RULE_2} fired"
    elif attention in (Attention.PRIORITY_REVIEW, Attention.REVIEW):
        action, why = RecommendedAction.HUMAN_REVIEW, f"3. attention = {attention.value}"
    else:
        action, why = RecommendedAction.NO_URGENT_ACTION, "4. ROUTINE / LOW"

    # Amendment 2, action half: PARTIAL may never rest on NO_URGENT_ACTION, and
    # a stronger action already selected (CONSIDER_ENGAGEMENT) is preserved.
    partial_promoted = False
    if data_state is DataState.PARTIAL and action is RecommendedAction.NO_URGENT_ACTION:
        action, partial_promoted = RecommendedAction.HUMAN_REVIEW, True

    ae = PolicyTraceEntry(
        rule=ACTION_RULE, fired=True,
        condition="1 RESEARCH (needs info) > 2 CONSIDER_ENGAGEMENT (rule 2) > "
                  "3 HUMAN_REVIEW (attention) > 4 NO_URGENT_ACTION (routine/low); "
                  "then PARTIAL promotes NO_URGENT_ACTION -> HUMAN_REVIEW",
        evidence=f"selected by precedence step {why}"
                 + (" then promoted for PARTIAL data" if partial_promoted else ""),
        sets={"recommended_action": action.value})
    if partial_promoted:
        ae.overrode["recommended_action"] = "NO_URGENT_ACTION -> HUMAN_REVIEW"
        ae.note = ("Amendment 2: PARTIAL data cannot rest on 'no urgent action'. Stronger "
                   "actions are preserved, never downgraded, by this promotion.")
    elif data_state is DataState.NEEDS_INFORMATION and RULE_2 in fired:
        ae.overrode["recommended_action"] = (
            f"{RecommendedAction.CONSIDER_ENGAGEMENT.value} -> {RecommendedAction.RESEARCH.value}")
        ae.note = ("Rule 2 held, but the experience history is missing/incomplete: research the "
                   "gap before engaging. Attention stays PRIORITY_REVIEW.")
    elif data_state is DataState.PARTIAL and action is RecommendedAction.CONSIDER_ENGAGEMENT:
        ae.note = ("PARTIAL data, but rule 2's CONSIDER_ENGAGEMENT is a STRONGER action and is "
                   "preserved rather than promoted (Amendment 2).")
    elif inp.exceptional and action is not RecommendedAction.CONSIDER_ENGAGEMENT:
        ae.note = ("Exceptional evidence alone does not mean CONSIDER_ENGAGEMENT — only rule 2 "
                   "produces that. Exceptional evidence means it must be SEEN.")
    trace.append(ae)

    # ------------------------------------------------------------------------
    # Structural invariants. Assertions, not tests: if the policy ever violates
    # one, the machine must fail loudly rather than emit the result.
    # v2.2 ordering guard 7 — ROUTINE is valid ONLY when all four hold.
    if attention is Attention.ROUTINE:
        assert not inp.exceptional                       # no exceptional floor
        assert inp.confidence >= conf_bar                # trusted
        assert data_state is DataState.SUFFICIENT        # Amendment 2
        assert inp.broad_score < broad_lo                # the existing rule 4
        assert potential is Potential.LOW
        assert action is RecommendedAction.NO_URGENT_ACTION
    assert not (action is RecommendedAction.NO_URGENT_ACTION
                and attention is not Attention.ROUTINE)
    # Amendment 3, both halves.
    assert not (inp.confidence < conf_bar and potential is not Potential.UNKNOWN)
    assert not (data_state is DataState.NEEDS_INFORMATION
                and potential is not Potential.UNKNOWN)
    assert not (data_state is DataState.NEEDS_INFORMATION
                and action is not RecommendedAction.RESEARCH)
    # v2.3 Amendment 4 — the four conditions LOW asserts.
    if potential is Potential.LOW:
        assert data_state is DataState.SUFFICIENT
        assert inp.confidence >= conf_bar
        assert inp.broad_score < broad_lo
        assert not inp.exceptional

    return PolicyOutcome(attention=attention, potential=potential, data_state=data_state,
                         recommended_action=action, policy_trace=trace, fired_rules=fired)
