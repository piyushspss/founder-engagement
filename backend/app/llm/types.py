"""The strictly-typed contract between the model and the rest of the system.

Nothing an adapter returns enters the application except through these types,
and nothing in these types can reach a deterministic field. The LLM layer is an
OVERLAY: it produces supplemental evidence and, at most, a raised attention
value carried alongside the deterministic assessment — never inside it.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.evidence.signal import Signal, SignalType, Strength

#: The categories a cue may claim. A category outside this set is rejected
#: rather than mapped to "other" — an unrecognised category means the model is
#: reasoning outside the vocabulary we validate, and we fail closed.
ALLOWED_CATEGORIES = (
    "unusual_progression",
    "exceptional_credential",
    "major_leadership_scope",
    "repeat_founding",
    "rare_domain_expertise",
    "exit_signal",
)

#: Strengths a cue may claim. NONE is not offerable: a cue with no strength is
#: not a cue. WEAK is accepted, shown, and never escalates.
ALLOWED_STRENGTHS = ("WEAK", "MEDIUM", "STRONG")


class EvidenceItem(BaseModel):
    """One claim plus the raw source paths it says it is grounded in."""

    model_config = ConfigDict(extra="forbid")

    claim: str = Field(min_length=1, max_length=2000)
    source_fields: list[str] = Field(min_length=1, max_length=12)


class RawFinding(BaseModel):
    """Exactly the JSON the model is required to return. `extra="forbid"` so a
    model that invents a field fails validation instead of having it ignored."""

    model_config = ConfigDict(extra="forbid")

    exceptional_signal: bool
    strength: str
    category: str
    evidence: list[EvidenceItem] = Field(default_factory=list, max_length=10)
    unsupported_inferences: list[str] = Field(default_factory=list, max_length=10)


class AdapterMetadata(BaseModel):
    """Provenance of the *call*, distinct from the provenance of the evidence.
    `provider = "mock"` is never presented as a real model result."""

    model_config = ConfigDict(frozen=True)

    provider: str
    model: str
    prompt_version: str
    prompt_sha256: str
    generated_at: str
    settings: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int | None = None


class DiscardReason(str, Enum):
    """Why an item never became evidence. Every one of these is reported."""

    UNKNOWN_SOURCE_PATH = "UNKNOWN_SOURCE_PATH"
    EMPTY_SOURCE_VALUE = "EMPTY_SOURCE_VALUE"
    FOREIGN_PROFILE_PATH = "FOREIGN_PROFILE_PATH"
    UNGROUNDED_LITERAL = "UNGROUNDED_LITERAL"
    INVALID_CATEGORY = "INVALID_CATEGORY"
    INVALID_STRENGTH = "INVALID_STRENGTH"
    NO_EVIDENCE_ITEMS = "NO_EVIDENCE_ITEMS"
    MALFORMED_OUTPUT = "MALFORMED_OUTPUT"
    # Additive, cp10.2 only. cp10.1 has no `novelty` field and can never emit
    # this reason; its prompt, schema, hash and behaviour are unchanged.
    INVALID_NOVELTY = "INVALID_NOVELTY"


class DiscardedItem(BaseModel):
    """A proposed claim that did not survive validation. Kept and reported so a
    reviewer can see what the model tried to assert and why it was refused."""

    model_config = ConfigDict(frozen=True)

    claim: str
    source_fields: list[str] = Field(default_factory=list)
    reason: DiscardReason
    detail: str


class AICue(BaseModel):
    """An ACCEPTED cue. Supplemental — never a deterministic signal, never
    merged into `broad_score`, and always typed AI_INTERPRETED."""

    model_config = ConfigDict(frozen=True)

    category: str
    strength: Strength
    claim: str
    source_fields: tuple[str, ...]
    signal: Signal
    metadata: AdapterMetadata


class AICheckResult(BaseModel):
    """The endpoint's whole answer. Deliberately shaped so the deterministic
    assessment and the AI overlay can never be confused for one another."""

    model_config = ConfigDict(frozen=True)

    founder_id: str
    available: bool
    provider: str
    status: str                       # ok | unavailable | error | malformed
    detail: str = ""

    deterministic_attention: str
    attention_with_ai: str
    attention_changed: bool
    attention_change_reason: str = ""

    ai_cues: list[AICue] = Field(default_factory=list)
    discarded: list[DiscardedItem] = Field(default_factory=list)
    unsupported_inferences: list[str] = Field(default_factory=list)
    aggregate_override: bool = False
    aggregate_rule: str = ""

    metadata: AdapterMetadata | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON form for the endpoint. This value is RETURNED, never persisted:
        the AI overlay is ephemeral and leaves no row behind."""
        return self.model_dump(mode="json")


def ai_signal(category: str, strength: Strength, claim: str,
              source_fields: tuple[str, ...]) -> Signal:
    """Build the supplemental Signal. `type` is AI_INTERPRETED, always — an AI
    reading is never relabelled OBSERVED or DERIVED. `value` is a display band,
    not an input to any score: nothing multiplies it by a weight."""
    value = {Strength.STRONG: 1.0, Strength.MEDIUM: 0.6,
             Strength.WEAK: 0.3, Strength.NONE: 0.0}[strength]
    return Signal(name=f"ai_{category}", value=value, strength=strength,
                  source_fields=tuple(source_fields), type=SignalType.AI_INTERPRETED,
                  explanation=claim, observed=True)
