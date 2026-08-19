"""cp10.2 — validation and the DETERMINISTIC contextual escalation policy.

This module is where the cp10.1 failure is actually fixed. cp10.1 handed the
model's self-rated strength to the deterministic exceptional aggregation rule,
which was calibrated for detectors; two grounded-but-mundane observations
therefore satisfied `2 × MEDIUM -> PRIORITY_REVIEW`. Here the model's rating is
an INPUT to a policy the model cannot see, cannot satisfy by repetition, and
cannot satisfy by asserting a level.

Three gates, in order. A finding must pass ALL of them to touch attention:

    1. GROUNDING     (`validate_contextual_finding`)
       every cited path exists on THIS founder and holds a value; quoted
       literals appear in the cited values. Failing = discarded, never repaired.
       Identical in spirit and in code-path to cp10.1 — the control that worked.

    2. RELATIONSHIP  (`fact_groups` / `relationship_ok`)
       the citations must span at least two DISTINCT fact groups. A group is one
       role, one education entry, or one top-level field. This is the structural
       expression of "a finding needs a relationship between facts, not a list of
       facts", and it is checked against the CITATIONS, which the model cannot
       inflate without citing paths it must then have grounded.

    3. NOVELTY       (`escalation_decision`)
       the model must have rated the finding HIGH. LOW and NONE are display-only
       forever, at any count.

And two ceilings that hold regardless of what came back:

    * ONE STEP. An AI check may raise attention by at most one level.
      ROUTINE -> REVIEW, or REVIEW -> PRIORITY_REVIEW. Never
      ROUTINE -> PRIORITY_REVIEW from AI alone.
    * NO ACCUMULATION. One eligible finding and ten eligible findings produce
      exactly the same one-step raise. There is no count anywhere in this file
      that can turn quantity into severity — the cp10.1 failure mode has no
      expression here.

The policy is provider-independent by construction: it reads a validated finding
and the deterministic attention value, and nothing else. It never lowers, never
writes, and never touches the deterministic assessment.
"""

from __future__ import annotations

import re
from typing import Any

from app.llm.contextual_types import (ALLOWED_NOVELTY, CONTEXTUAL_CATEGORIES,
                                      ContextualCue, Novelty,
                                      RawContextualFinding, contextual_signal)
from app.llm.types import AdapterMetadata, DiscardReason, DiscardedItem
from app.llm.validate import _grounding_failure  # noqa: PLC2701 — one validator, reused
from app.llm.types import EvidenceItem
from app.policy.dimensions import ATTENTION_ORDER, Attention

#: `experience[3].title` -> `experience[3]`; `education[0].institution` ->
#: `education[0]`; `headline` -> `headline`. One indexed container element, or
#: one top-level field, is ONE fact group.
_GROUP = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*(?:\[\d+\])?)")

#: How many distinct fact groups a finding must cite before it is even
#: CONSIDERED a relationship. Two is the minimum that can express a conjunction.
MIN_FACT_GROUPS = 2


def fact_groups(source_fields: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """The distinct fact groups a set of citations spans, sorted.

    Deliberately coarse. `experience[0].title` and `experience[0].company` are
    the SAME group: a claim built from two fields of one role is a description of
    that role, not a relationship between facts. Two roles, or a role and an
    education entry, are two groups."""
    groups = set()
    for path in source_fields:
        match = _GROUP.match(path.strip())
        groups.add(match.group(1) if match else path.strip())
    return tuple(sorted(groups))


def relationship_ok(source_fields: tuple[str, ...] | list[str]) -> bool:
    """True when the citations span enough distinct facts to BE a relationship."""
    return len(fact_groups(source_fields)) >= MIN_FACT_GROUPS


# --------------------------------------------------------------- validation
def validate_contextual_finding(finding: RawContextualFinding,
                                allowed: dict[str, Any],
                                metadata: AdapterMetadata,
                                foreign_paths: dict[str, str] | None = None,
                                ) -> tuple[list[ContextualCue], list[DiscardedItem]]:
    """Turn a raw cp10.2 finding into accepted cues plus a discard report.

    Per-item rather than per-finding: cp10.1 rejected a whole response for one
    bad category because category was a top-level field. Here each finding
    carries its own category and novelty, so one bad item is discarded and the
    rest are still read.

    Grounding failures are DISCARDED, NEVER REPAIRED — guessing which path the
    model meant would turn a hallucination into evidence with a citation
    attached. `foreign_paths` maps a path belonging to ANOTHER founder to that
    founder's id, so a cross-profile citation is named as such."""
    accepted: list[ContextualCue] = []
    discarded: list[DiscardedItem] = []
    foreign_paths = foreign_paths or {}

    for item in finding.findings:
        if item.category not in CONTEXTUAL_CATEGORIES:
            discarded.append(DiscardedItem(
                claim=item.claim, source_fields=list(item.source_fields),
                reason=DiscardReason.INVALID_CATEGORY,
                detail=f"category {item.category!r} is not in the cp10.2 vocabulary"))
            continue

        if item.novelty not in ALLOWED_NOVELTY:
            discarded.append(DiscardedItem(
                claim=item.claim, source_fields=list(item.source_fields),
                reason=DiscardReason.INVALID_NOVELTY,
                detail=(f"novelty {item.novelty!r} is not one of "
                        f"{list(ALLOWED_NOVELTY)}; note there is deliberately no "
                        f"MEDIUM level in cp10.2")))
            continue

        bad: DiscardedItem | None = None
        for path in item.source_fields:
            if path in allowed:
                continue
            if path in foreign_paths:
                bad = DiscardedItem(
                    claim=item.claim, source_fields=list(item.source_fields),
                    reason=DiscardReason.FOREIGN_PROFILE_PATH,
                    detail=(f"{path!r} exists on founder {foreign_paths[path]}, not "
                            f"on this founder — cross-profile citation refused"))
                break
            bad = DiscardedItem(
                claim=item.claim, source_fields=list(item.source_fields),
                reason=DiscardReason.UNKNOWN_SOURCE_PATH,
                detail=(f"{path!r} does not exist on this founder, or holds no "
                        f"value; not repaired to a similar path"))
            break

        if bad is None:
            # The same quoted-literal contradiction check cp10.1 used, run over
            # `claim` and `why_notable` together: a justification that quotes
            # something absent from the cited values is as ungrounded as a claim
            # that does.
            probe = EvidenceItem(claim=f"{item.claim} {item.why_notable}",
                                 source_fields=list(item.source_fields))
            problem = _grounding_failure(probe, allowed)
            if problem:
                bad = DiscardedItem(claim=item.claim,
                                    source_fields=list(item.source_fields),
                                    reason=DiscardReason.UNGROUNDED_LITERAL,
                                    detail=problem)

        if bad is not None:
            discarded.append(bad)
            continue

        novelty = Novelty(item.novelty)
        groups = fact_groups(item.source_fields)
        eligible = novelty is Novelty.HIGH and len(groups) >= MIN_FACT_GROUPS
        if eligible:
            note = (f"HIGH novelty grounded across {len(groups)} fact groups "
                    f"({', '.join(groups)}) — eligible for a one-step raise")
        elif novelty is Novelty.HIGH:
            note = (f"HIGH novelty claimed but the citations span only "
                    f"{len(groups)} fact group ({', '.join(groups)}); a single "
                    f"fact is a description, not a relationship — display only")
        else:
            note = (f"{novelty.value} novelty — display only; no number of "
                    f"{novelty.value} findings can escalate")

        accepted.append(ContextualCue(
            category=item.category, claim=item.claim, why_notable=item.why_notable,
            novelty=novelty, source_fields=tuple(item.source_fields),
            fact_groups=groups, escalation_eligible=eligible, policy_note=note,
            signal=contextual_signal(item.category, novelty, item.claim,
                                     tuple(item.source_fields)),
            metadata=metadata))

    if finding.contextual_signal and not accepted and not discarded:
        discarded.append(DiscardedItem(
            claim="(no findings supplied)", source_fields=[],
            reason=DiscardReason.NO_EVIDENCE_ITEMS,
            detail="contextual_signal was true but the response carried no findings"))

    return accepted, discarded


# ---------------------------------------------------------------- escalation
def one_step_up(attention: Attention) -> Attention:
    """Exactly one level up the attention ladder, capped at the top.

    The smallest provider-neutral helper that expresses the cp10.2 ceiling. It
    is used ONLY by this policy; deterministic policy code does not call it and
    its behaviour is unchanged."""
    ordered = sorted(ATTENTION_ORDER, key=lambda a: ATTENTION_ORDER[a])
    index = ATTENTION_ORDER[attention]
    return ordered[min(index + 1, len(ordered) - 1)]


def escalation_decision(cues: list[ContextualCue],
                        deterministic: Attention) -> tuple[Attention, bool, str]:
    """(attention_with_ai, escalated, human-readable rule).

    The entire escalation logic, and it is deliberately this small:

    * no eligible cue  -> nothing moves, whatever the count or the ratings;
    * any eligible cue -> exactly ONE step up, whatever the count.

    There is no branch here that reads `len(...)` as severity, and none that can
    produce a two-step jump. `ROUTINE -> PRIORITY_REVIEW` from AI alone is not
    reachable by any input to this function."""
    eligible = [c for c in cues if c.escalation_eligible]

    if not eligible:
        if not cues:
            return deterministic, False, "no accepted contextual findings"
        levels = ", ".join(sorted({c.novelty.value for c in cues}))
        return deterministic, False, (
            f"{len(cues)} accepted contextual finding(s) [{levels}] — display "
            f"only; none passed the HIGH-novelty + relationship test, and low-value "
            f"findings never accumulate into an escalation")

    raised = one_step_up(deterministic)
    if raised is deterministic:
        return deterministic, False, (
            f"{len(eligible)} eligible HIGH contextual finding(s) but attention is "
            f"already at the ceiling ({deterministic.value}) — nothing to raise")

    categories = ", ".join(sorted({c.category for c in eligible}))
    return raised, True, (
        f"one-step raise {deterministic.value} -> {raised.value}: "
        f"{len(eligible)} eligible HIGH contextual finding(s) [{categories}]. "
        f"One step is the maximum an AI check may move attention, regardless of "
        f"how many findings qualify")
