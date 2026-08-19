"""The Signal — PLAN §4.5b.

Every claim the system makes about a founder is a Signal, and every Signal
carries its own provenance. The point is that "why did you conclude this?" is
answerable by pointing at raw JSON paths, and that a fact and a judgment are
visibly different things.

`strength` is NOT a restatement of `value`. A signal whose value is the
configured neutral default because nothing was observed has strength NONE, no
matter what that default number is. Absence of evidence is not weak evidence.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class SignalType(str, Enum):
    """Provenance CLASS of a signal — how the claim came to exist.

    `AI_INTERPRETED` is structurally separate so an LLM reading can never be
    presented as an observed fact, and so the optional AI layer's output is
    filterable everywhere it appears."""

    OBSERVED = "OBSERVED"            # read directly off a raw field
    DERIVED = "DERIVED"              # computed deterministically from raw fields
    AI_INTERPRETED = "AI_INTERPRETED"  # produced by the optional LLM layer (CP10)


class Strength(str, Enum):
    """Evidential weight. `NONE` means "not observed", not "observed and weak"."""

    NONE = "NONE"
    WEAK = "WEAK"
    MEDIUM = "MEDIUM"
    STRONG = "STRONG"


class Signal(BaseModel):
    """One claim plus its provenance. Immutable once built.

    `observed=False` marks a value that is the configured NEUTRAL DEFAULT
    because the inputs were absent — not a measured low score. Consumers must
    keep the two apart: an unobserved signal is missing data (which reduces
    confidence), never negative evidence about the founder."""

    model_config = ConfigDict(frozen=True)

    name: str
    value: float = Field(ge=0.0, le=1.0)
    strength: Strength
    source_fields: tuple[str, ...] = ()
    type: SignalType = SignalType.DERIVED
    explanation: str = ""
    observed: bool = True   # False => value is the configured neutral default

    def weighted(self, weight: float) -> float:
        """This signal's contribution to `broad_score`, for the UI signal table."""
        return weight * self.value


def strength_for(value: float, observed: bool) -> Strength:
    """Map a value to a strength band. Unobserved signals are always NONE: the
    neutral default is a placeholder for 'we do not know', and reporting it as
    WEAK evidence would be a lie about the data."""
    if not observed:
        return Strength.NONE
    if value <= 0.0:
        return Strength.NONE
    if value < 0.40:
        return Strength.WEAK
    if value < 0.70:
        return Strength.MEDIUM
    return Strength.STRONG
