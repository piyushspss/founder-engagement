"""The Assessment — PLAN §4.5, the machine's complete and only output.

What is NOT in this model is as deliberate as what is. There is no `decision`
field and no `stage` field, at any depth. Those are human authority (PLAN §0,
§5), so the machine has no field to write them into — the boundary is enforced
by the shape of the type, not by a convention someone has to remember.

The model is serialisable, self-explaining and version-stamped: every assessment
carries the hash of the config that produced it, so a rescore is provably
attributable to a rubric change rather than to drift.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.evidence.confidence import ConfidenceBreakdown
from app.evidence.signal import Signal
from app.policy.dimensions import (Attention, DataState, Potential,
                                   RecommendedAction)


class ExceptionalBlock(BaseModel):
    """§4.2's separate path, kept separate in the output too — it is never
    averaged into `broad_score`."""

    model_config = ConfigDict(frozen=True)

    flag: bool
    rule: str
    signals: list[Signal] = Field(default_factory=list)
    not_fired: dict[str, str] = Field(default_factory=dict)


class ArchetypeBlock(BaseModel):
    """A LABEL. Nothing here is an input to any number (proved by test)."""

    model_config = ConfigDict(frozen=True)

    archetype: str
    strong_signals: list[str] = Field(default_factory=list)
    missing_for_archetype: list[str] = Field(default_factory=list)
    secondary: list[str] = Field(default_factory=list)
    explanation: str = ""


class MissingItem(BaseModel):
    """One thing we do not have. Missing data is reported, never scored as
    negative evidence — it lowers confidence and raises review pressure."""

    model_config = ConfigDict(frozen=True)

    code: str
    detail: str
    source_fields: tuple[str, ...] = ()


class ContradictionItem(BaseModel):
    """One way the record disagrees with ITSELF (not with the world).

    Reported to a human and charged against confidence — never against the
    founder's score."""

    model_config = ConfigDict(frozen=True)

    code: str
    detail: str
    source_fields: tuple[str, ...] = ()
    value: float | int | str | None = None


class PolicyTraceItem(BaseModel):
    """One safety-policy rule's evaluation, serialised.

    Present for rules that did NOT fire too, which is what makes "why is this
    founder not priority?" answerable from a stored assessment alone."""

    model_config = ConfigDict(frozen=True)

    rule: str
    fired: bool
    condition: str
    evidence: str
    sets: dict[str, str] = Field(default_factory=dict)
    overrode: dict[str, str] = Field(default_factory=dict)
    preserved: dict[str, str] = Field(default_factory=dict)
    note: str = ""


class Assessment(BaseModel):
    """The complete MACHINE assessment of one founder. Immutable.

    Note what is absent and stays absent: there is no `decision` field, no
    `stage` field and no AI field. Disposition and lifecycle stage are human
    authority; AI evidence is ephemeral and is never persisted here, so
    `signals` never contains an `AI_INTERPRETED` entry in stored data.

    `rubric_version` + `assessment_version` make the result auditable: the first
    says which effective config produced it, the second counts successful
    reassessments."""

    model_config = ConfigDict(frozen=True)

    person_id: str

    # ---- evidence ----
    broad_score: float
    signals: list[Signal]
    exceptional: ExceptionalBlock
    confidence: float
    confidence_breakdown: ConfidenceBreakdown
    archetype: ArchetypeBlock

    # ---- the four orthogonal machine dimensions (§4.5) ----
    potential: Potential
    attention: Attention
    data_state: DataState
    recommended_action: RecommendedAction

    # ---- explainability ----
    missing: list[MissingItem] = Field(default_factory=list)
    contradictions: list[ContradictionItem] = Field(default_factory=list)
    policy_trace: list[PolicyTraceItem] = Field(default_factory=list)
    fired_rules: list[str] = Field(default_factory=list)

    # ---- provenance of the assessment itself ----
    assessment_version: str
    rubric_version: str

    def to_dict(self) -> dict[str, Any]:
        """JSON form — exactly what is persisted in `founders.assessment_json`."""
        return self.model_dump(mode="json")
