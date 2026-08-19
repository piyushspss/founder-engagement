"""Assessment assembly — the one place the evidence layer meets the safety policy.

This module is deliberately thin. It computes nothing of its own: signals,
confidence, exceptional detectors and the archetype label are computed by
`app.evidence`, the four dimensions are decided by `app.policy`, and this file
only carries values between them and packages the result.

That thinness is the design. If a number could be adjusted here — a nudge to
broad_score, a "well, this one deserves REVIEW" special case — the policy trace
would stop being a complete explanation of the output. There is no such nudge,
and `assess()` has no branches that depend on any individual founder.
"""

from __future__ import annotations

from app.assessment.model import (ArchetypeBlock, Assessment,
                                  ContradictionItem, ExceptionalBlock,
                                  MissingItem, PolicyTraceItem)
from app.evidence import (broad_score, compute_confidence, compute_signals,
                          detect_exceptional, label_archetype)
from app.evidence.confidence import coverage_components, history_depth
from app.models.canonical import CanonicalProfile, FlagKind
from app.policy import PolicyInput, apply_policy

ASSESSMENT_VERSION = "cp5.1"

# Coverage components that, when below 1.0, are worth telling a human about by
# name. `experience_history` is handled separately because it is rule 5's own
# condition and appears in `data_state` instead of as a line item.
_COVERAGE_LABEL = {
    "is_current_known": "whether the most recent role is ongoing is unknown",
    "start_dates_readable": "some roles carry no readable start date, or a month we inferred",
    "seniority_readability": "some roles carry no management_level in the known taxonomy, "
                             "so leadership and career trajectory cannot be evaluated there",
    "tenure_readability": "some roles carry no duration",
    "education_present": "no education recorded",
    "institution_present": "some education entries name no institution",
    "degree_interpretable": "some education entries carry a credential we cannot parse",
    "industry_classified": "some roles have no usable industry (UNKNOWN, which is neither "
                           "health nor non-health)",
    "scope_available": "some roles carry no company size, so operating scope is unevaluable",
    "titles_readable": "some roles carry no title, so founding cannot be ruled in or out",
    "total_experience_stated": "no stated total experience",
    "location_known": "no location recorded",
    "breadth_inputs_readable": "some roles carry no industry string, so breadth is understated",
}


def experience_incomplete(profile: CanonicalProfile) -> bool:
    """Rule 5 / data_state condition (safety.py I-3').

    Keyed on the `history_depth` SUB-component, never on the composite
    `experience_history` component. Since v2.2 Amendment 1 that composite also
    carries `seniority_readability` and `tenure_readability`, so reading it here
    would report a complete two-role history as a *missing history* the moment
    `management_level` went absent — a different and false claim."""
    return history_depth(profile) < 1.0


def collect_missing(profile: CanonicalProfile, components: dict[str, float],
                    subcomponents: dict[str, dict[str, float]]) -> list[MissingItem]:
    """What we do not have, from two sources: the normalizer's QUALITY flags
    (things it noticed were absent) and the §4.3 coverage components that came
    back short. Reported for a human to go and find — never scored."""
    # One line per KIND of gap, not one per role: three roles missing a level is
    # one thing to go and find, and the source_fields carry the detail.
    out: list[MissingItem] = []
    seen: set[str] = set()
    for f in profile.quality_flags:
        if not f.code.startswith(("MISSING_", "NO_", "UNKNOWN_")) or f.code in seen:
            continue
        same = [g for g in profile.quality_flags if g.code == f.code]
        detail = f.detail if len(same) == 1 else f"{f.detail} (and {len(same) - 1} more)"
        out.append(MissingItem(
            code=f.code, detail=detail,
            source_fields=tuple(dict.fromkeys(x for g in same for x in g.source_fields))))
        seen.add(f.code)

    depth = subcomponents["experience_history"]["history_depth"]
    if depth < 1.0:
        code = "NO_EXPERIENCE_HISTORY" if depth == 0.0 else "INCOMPLETE_EXPERIENCE_HISTORY"
        if code not in seen:
            out.append(MissingItem(
                code=code, detail=("no experience history at all" if code.startswith("NO_")
                                   else "a single role — where they are, not how they got there"),
                source_fields=("experience",)))
            seen.add(code)

    # v2.2: report the SHORT SUB-COMPONENT by name. "seniority_readability 0.00"
    # tells a human which field to go and find; "experience_history 0.67" does not.
    for component, parts in subcomponents.items():
        for part, value in parts.items():
            if value < 1.0 and part != "history_depth":   # depth is reported above
                code = f"COVERAGE_{part.upper()}"
                if code not in seen:
                    out.append(MissingItem(
                        code=code,
                        detail=(f"{_COVERAGE_LABEL.get(part, part)} "
                                f"({value:.2f} of 1.00, feeds §4.3 {component})"),
                        source_fields=()))
                    seen.add(code)
    return out


def assess(profile: CanonicalProfile, cfg) -> Assessment:
    """Assemble the complete deterministic assessment for one founder.

    Pure and total: same profile + same config -> same Assessment, with no
    clock, no randomness, no I/O and no per-founder special case. This is the
    property the whole product rests on, and it is what makes `rubric_version`
    a meaningful claim about an assessment.

    The four dimensions come from `apply_policy` and are NOT recomputed here.
    The archetype is a labelling/explanation layer over the same signals and is
    fed the exceptional flag purely so it can describe it — it changes no score
    and no dimension. Nothing produced here is a disposition or a lifecycle
    stage; both are human authority and have no representation in `Assessment`.
    """
    signals = compute_signals(profile, cfg)
    score = broad_score(signals, cfg)
    breakdown = compute_confidence(profile, cfg)
    exceptional = detect_exceptional(profile, cfg)
    archetype = label_archetype(profile, signals, cfg, exceptional.flag)

    components = breakdown.coverage_components
    outcome = apply_policy(
        PolicyInput(
            broad_score=score,
            confidence=breakdown.confidence,
            exceptional=exceptional.flag,
            experience_incomplete=(
                breakdown.coverage_subcomponents["experience_history"]["history_depth"] < 1.0),
            coverage=breakdown.coverage),
        cfg)

    return Assessment(
        person_id=profile.person_id,
        broad_score=score,
        signals=signals,
        exceptional=ExceptionalBlock(flag=exceptional.flag, rule=exceptional.rule,
                                     signals=exceptional.signals,
                                     not_fired=exceptional.not_fired),
        confidence=breakdown.confidence,
        confidence_breakdown=breakdown,
        archetype=ArchetypeBlock(archetype=archetype.archetype,
                                 strong_signals=archetype.strong_signals,
                                 missing_for_archetype=archetype.missing_for_archetype,
                                 secondary=archetype.secondary,
                                 explanation=archetype.explanation),
        potential=outcome.potential,
        attention=outcome.attention,
        data_state=outcome.data_state,
        recommended_action=outcome.recommended_action,
        missing=collect_missing(profile, components, breakdown.coverage_subcomponents),
        contradictions=[ContradictionItem(code=f.code, detail=f.detail,
                                          source_fields=f.source_fields, value=f.value)
                        for f in profile._all_flags() if f.kind is FlagKind.CONTRADICTION],
        policy_trace=[PolicyTraceItem(**e.to_dict()) for e in outcome.policy_trace],
        fired_rules=outcome.fired_rules,
        assessment_version=ASSESSMENT_VERSION,
        rubric_version=cfg.version_hash())
