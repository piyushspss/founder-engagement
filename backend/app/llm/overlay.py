"""Raise-only aggregation.

The rule is the deterministic exceptional rule, reused rather than reinvented:
one STRONG cue, or `exceptional.medium_count` MEDIUM cues (2 in the frozen
config), justifies a PRIORITY_REVIEW floor. A single MEDIUM cue is shown as an
unusual-evidence cue and floors attention at REVIEW without claiming the
aggregate override fired — the same distinction CP8 had to draw for F-13, now
on the AI side.

Two invariants, both asserted rather than assumed:

* the result is a MAX with the deterministic value — attention can only ratchet
  up, never down;
* the deterministic assessment is not an input to anything here and is never
  written to. The overlay is a second value carried beside it.
"""

from __future__ import annotations

from app.evidence.signal import Strength
from app.llm.types import AICue
from app.policy.dimensions import ATTENTION_ORDER, Attention


def aggregate(cues: list[AICue], cfg) -> tuple[bool, Attention | None, str]:
    """Returns (aggregate_override, attention_floor, human-readable rule).

    `attention_floor` is the floor this evidence justifies on its own — the
    caller still takes the maximum with the deterministic value."""
    if not cues:
        return False, None, "no accepted AI evidence"

    medium_count = int(cfg.weights["exceptional"]["medium_count"])
    strong = [c for c in cues if c.strength is Strength.STRONG]
    medium = [c for c in cues if c.strength is Strength.MEDIUM]

    if strong:
        return True, Attention.PRIORITY_REVIEW, (
            f"{len(strong)} STRONG AI cue(s): "
            f"{', '.join(sorted({c.category for c in strong}))}")
    if len(medium) >= medium_count:
        return True, Attention.PRIORITY_REVIEW, (
            f"{len(medium)} MEDIUM AI cues (>= {medium_count}): "
            f"{', '.join(sorted({c.category for c in medium}))}")
    if medium:
        return False, Attention.REVIEW, (
            f"{len(medium)} MEDIUM AI cue (< {medium_count} required for the "
            f"priority override) — shown as an unusual-evidence cue, attention "
            f"floored at REVIEW")
    return False, None, (
        f"{len(cues)} WEAK AI cue(s) — shown, no escalation")


def raise_only(deterministic: Attention, floor: Attention | None) -> Attention:
    """The ratchet. Never returns anything below `deterministic`."""
    if floor is None:
        return deterministic
    return (floor if ATTENTION_ORDER[floor] > ATTENTION_ORDER[deterministic]
            else deterministic)
