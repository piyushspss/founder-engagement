"""cp10.2 types — GROUNDING and NOTABILITY are different fields, on purpose.

At cp10.1 one word (`strength`) carried both meanings, and the deterministic
aggregation rule read it as if it meant the detector-calibrated one. Here they
are structurally separate and can never be confused:

* GROUNDING lives in `source_fields` and is settled by the validator, which the
  model cannot influence — an ungrounded finding is discarded outright.
* NOTABILITY lives in `novelty`, is per-finding, and is an INPUT to a
  deterministic policy rather than a verdict. A model-claimed HIGH is a request,
  not an escalation.

The vocabulary itself is part of the fix. Every category below names a
RELATIONSHIP; there is deliberately no category a single ordinary fact could be
filed under, so "holds a senior title" has nowhere to go.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.evidence.signal import Signal, SignalType, Strength
from app.llm.types import AdapterMetadata

#: Relationship shapes a contextual finding may claim. Anything outside this set
#: is rejected rather than mapped to a neighbour — an unknown category means the
#: model is reasoning outside the vocabulary we validate, and we fail closed.
CONTEXTUAL_CATEGORIES = (
    "cross_domain_combination",
    "uncommon_transition",
    "expertise_plus_operating",
    "multi_role_pattern",
    "material_contradiction",
    "unusual_trajectory",
)

#: Notability levels. There is deliberately NO MEDIUM: the middle rung is where
#: cp10.1 failed, because it let "true and grounded" borrow the meaning of "a
#: named detector fired". A finding is either ordinary (NONE), mildly
#: interesting (LOW), or genuinely unusual (HIGH).
ALLOWED_NOVELTY = ("NONE", "LOW", "HIGH")


class Novelty(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    HIGH = "HIGH"


class RawContextualItem(BaseModel):
    """One proposed finding, exactly as the model returned it."""

    model_config = ConfigDict(extra="forbid")

    category: str
    claim: str = Field(min_length=1, max_length=2000)
    why_notable: str = Field(min_length=1, max_length=2000)
    source_fields: list[str] = Field(min_length=1, max_length=12)
    novelty: str


class RawContextualFinding(BaseModel):
    """Exactly the JSON cp10.2 requires. `extra="forbid"`, so a model that
    invents a field fails validation instead of having it quietly ignored."""

    model_config = ConfigDict(extra="forbid")

    contextual_signal: bool
    findings: list[RawContextualItem] = Field(default_factory=list, max_length=10)
    unsupported_inferences: list[str] = Field(default_factory=list, max_length=10)


class ContextualCue(BaseModel):
    """An ACCEPTED finding: grounded, and carrying the policy's verdict on it.

    `novelty` is what the MODEL said. `escalation_eligible` is what the
    DETERMINISTIC POLICY decided, and only the latter can affect attention. Both
    are kept so a reviewer can see where the two disagreed."""

    model_config = ConfigDict(frozen=True)

    category: str
    claim: str
    why_notable: str
    novelty: Novelty
    source_fields: tuple[str, ...]
    #: Distinct fact groups the citations span — the relationship test's input.
    fact_groups: tuple[str, ...] = ()
    escalation_eligible: bool = False
    policy_note: str = ""
    signal: Signal
    metadata: AdapterMetadata


class ContextualCheckResult(BaseModel):
    """The whole answer for one profile. Shaped so the deterministic assessment
    and the AI overlay can never be mistaken for one another, and so that the
    escalation DECISION is reported separately from the model's rating."""

    model_config = ConfigDict(frozen=True)

    founder_id: str
    available: bool
    provider: str
    prompt_version: str
    status: str                       # ok | unavailable | error | malformed
    detail: str = ""

    deterministic_attention: str
    attention_with_ai: str
    attention_changed: bool
    attention_change_reason: str = ""

    #: True when the contextual policy raised attention. Never more than one
    #: step, and never from an accumulation of low-value findings.
    escalated: bool = False
    escalation_rule: str = ""

    cues: list[ContextualCue] = Field(default_factory=list)
    discarded: list[Any] = Field(default_factory=list)
    unsupported_inferences: list[str] = Field(default_factory=list)

    metadata: AdapterMetadata | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON form. RETURNED, never persisted — the overlay is ephemeral and
        leaves no row behind, exactly as at cp10.1."""
        return self.model_dump(mode="json")


def contextual_signal(category: str, novelty: Novelty, claim: str,
                      source_fields: tuple[str, ...]) -> Signal:
    """The supplemental Signal. `type` is AI_INTERPRETED, always — a contextual
    reading is never relabelled OBSERVED or DERIVED. `value` is a display band,
    not an input to any score: nothing multiplies it by a weight, and it does
    not reach `broad_score`, `confidence` or `potential`.

    `strength` is filled with the WEAK/MEDIUM band only because `Signal`
    requires the enum for display. It is never read by the contextual policy —
    escalation is decided from `novelty` plus the relationship test, so this
    value cannot re-enter the deterministic exceptional aggregation the way
    cp10.1's self-rated strength did."""
    band = {Novelty.HIGH: (0.6, Strength.MEDIUM),
            Novelty.LOW: (0.3, Strength.WEAK),
            Novelty.NONE: (0.0, Strength.NONE)}[novelty]
    return Signal(name=f"ai_ctx_{category}", value=band[0], strength=band[1],
                  source_fields=tuple(source_fields),
                  type=SignalType.AI_INTERPRETED, explanation=claim, observed=True)
