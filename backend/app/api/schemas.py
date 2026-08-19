"""Request/response schemas for the human endpoints.

Every human mutation schema requires `actor` and `reason`. There is no schema
anywhere in this package that accepts a `decision` or a `stage` alongside
machine input — the machine literally has no way to say those words.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class DecisionRequest(BaseModel):
    """HUMAN disposition. `actor` and `reason` are mandatory — an unattributed
    or unexplained decision is not auditable."""

    model_config = ConfigDict(extra="forbid")

    disposition: Literal["NEEDS_REVIEW", "POTENTIAL", "NOT_NOW", "NEEDS_INFORMATION"]
    actor: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class StageRequest(BaseModel):
    """HUMAN stage transition. `months` is required iff the target is KEEP_WARM
    and must be 3, 6 or 9; the service rejects it anywhere else."""

    model_config = ConfigDict(extra="forbid")

    stage: Literal["NEW", "ASSESSMENT", "POTENTIAL", "NURTURING", "KEEP_WARM", "DEAL",
                   "CLOSED"]
    actor: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    months: int | None = Field(default=None, description="required iff stage == KEEP_WARM; "
                                                         "must be 3, 6 or 9")


class NoteRequest(BaseModel):
    """HUMAN note. Append-only; there is no edit or delete schema."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    actor: str = Field(min_length=1)


class WorkflowPatchRequest(BaseModel):
    """Transport-completion endpoint: owner / next_action only."""

    model_config = ConfigDict(extra="forbid")

    actor: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    owner: str | None = None
    next_action: str | None = None


class ImportRequest(BaseModel):
    """Machine import payload. `extra="forbid"` is the point: a `stage` or
    `decision` key arriving with machine input is REFUSED, never ignored."""

    model_config = ConfigDict(extra="forbid")

    profiles: list[dict[str, Any]]
    source: str | None = None
    funnel: str | None = None


class ConfigPutRequest(BaseModel):
    """Config patch. Accepted and persisted without rescoring anything."""

    model_config = ConfigDict(extra="forbid")

    config: dict[str, Any]
    actor: str | None = None


class RescoreRequest(BaseModel):
    """Explicit rescore request. Re-evaluates the MACHINE assessment only."""

    model_config = ConfigDict(extra="forbid")

    actor: str = "system"
    reason: str | None = None


class KeepWarmInfo(BaseModel):
    """Keep-warm date carried on read responses. A date, not a datetime — the
    due comparison is inclusive and date-based in UTC."""

    keep_warm_until: date | None = None
