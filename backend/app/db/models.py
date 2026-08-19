"""Persistence model — PLAN §5, RUNBOOK CP7.

The machine/human boundary from PLAN §0 and §4.5 is a *table* boundary here, not
a convention:

* `founders` holds machine-owned state only — raw, canonical, assessment, and
  the version metadata that says which rubric produced it.
* `decisions` and `workflow` hold human-owned state. No import, assessment or
  rescore path writes to them; only the explicit human endpoints do.
* `audit_log` records every human mutation and every machine RESCORE event.

`decisions` is append-only: a disposition is an *event* a person authored at a
point in time, and the current decision is simply the latest event. Overwriting
a row would destroy the record of who thought what, when.
"""

from __future__ import annotations

import enum
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import (JSON, Date, DateTime, ForeignKey, Index, Integer,
                        String, Text)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    """UTC now, stored naive.

    The product dates EVERYTHING from UTC: no local clock and no browser
    timezone takes part in keep-warm due dates, ageing or stuck counts. Stored
    without a tzinfo because SQLite has no timezone-aware type — the value is
    always UTC, so comparisons stay correct."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# --------------------------------------------------------------------- enums
class Disposition(str, enum.Enum):
    """Human disposition — PLAN §5. Deliberately NOT a machine dimension."""

    NEEDS_REVIEW = "NEEDS_REVIEW"
    POTENTIAL = "POTENTIAL"
    NOT_NOW = "NOT_NOW"
    NEEDS_INFORMATION = "NEEDS_INFORMATION"


class Stage(str, enum.Enum):
    """Human lifecycle stage — PLAN §5. Human authority, like `Disposition`.

    `NEW` is the neutral creation default (a founder has to be somewhere), not a
    machine recommendation. Legal moves live in
    `workflow_service.TRANSITIONS`, not in this enum: enum-to-enum would permit
    CLOSED → DEAL simply because nothing said otherwise."""

    NEW = "NEW"
    ASSESSMENT = "ASSESSMENT"
    POTENTIAL = "POTENTIAL"
    NURTURING = "NURTURING"
    KEEP_WARM = "KEEP_WARM"
    DEAL = "DEAL"
    CLOSED = "CLOSED"


# -------------------------------------------------------------------- tables
class Founder(Base):
    """Machine-owned founder record. Contains no disposition and no stage."""

    __tablename__ = "founders"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    mdm_person_id: Mapped[str | None] = mapped_column(String, unique=True, index=True)

    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    canonical_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    assessment_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    #: per-founder reassessment counter: 1 on first assessment, +1 on every
    #: SUCCESSFUL reassessment (import-update or /rescore).
    assessment_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    #: UTC time of the successful assessment that produced `assessment_json`.
    assessed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    #: SHA-256 of the complete effective rubric used for that assessment.
    rubric_version: Mapped[str] = mapped_column(String, nullable=False)
    #: version of the assessment ENGINE (code), distinct from the counter above.
    engine_version: Mapped[str] = mapped_column(String, nullable=False, default="")

    funnel: Mapped[str | None] = mapped_column(String, index=True)
    source: Mapped[str | None] = mapped_column(String, index=True)
    duplicate_flags: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow,
                                                 index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow,
                                                 onupdate=utcnow)

    decisions: Mapped[list["Decision"]] = relationship(
        back_populates="founder", order_by="Decision.id", cascade="all, delete-orphan")
    workflow: Mapped["Workflow"] = relationship(
        back_populates="founder", uselist=False, cascade="all, delete-orphan")
    audit: Mapped[list["AuditLog"]] = relationship(
        back_populates="founder", order_by="AuditLog.id", cascade="all, delete-orphan")

    # -- convenience --------------------------------------------------------
    @property
    def current_decision(self) -> "Decision | None":
        """The latest human decision, or None if nobody has decided yet.

        None is the normal state for a newly imported founder and is NOT a
        machine-assigned disposition."""
        return self.decisions[-1] if self.decisions else None

    @property
    def attention(self) -> str:
        """Machine attention, read off the stored assessment."""
        return self.assessment_json.get("attention", "")

    @property
    def confidence(self) -> float:
        """Evidence confidence (0–1), read off the stored assessment."""
        return float(self.assessment_json.get("confidence") or 0.0)

    @property
    def data_state(self) -> str:
        """Machine data_state, read off the stored assessment."""
        return self.assessment_json.get("data_state", "")


class Decision(Base):
    """Append-only human decision event. `current_decision` = latest row."""

    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    founder_id: Mapped[str] = mapped_column(ForeignKey("founders.id"), index=True,
                                            nullable=False)
    disposition: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    founder: Mapped[Founder] = relationship(back_populates="decisions")


class Workflow(Base):
    """Human-controlled engagement state. The machine may create a neutral NEW
    row at founder creation and may never touch it again."""

    __tablename__ = "workflow"

    founder_id: Mapped[str] = mapped_column(ForeignKey("founders.id"), primary_key=True)
    stage: Mapped[str] = mapped_column(String, nullable=False, default=Stage.NEW.value,
                                       index=True)
    owner: Mapped[str | None] = mapped_column(String, index=True)
    next_action: Mapped[str | None] = mapped_column(Text)
    keep_warm_until: Mapped[date | None] = mapped_column(Date, index=True)
    notes: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    stage_changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False,
                                                       default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    founder: Mapped[Founder] = relationship(back_populates="workflow")


class AuditLog(Base):
    """who · when · field/event · from → to · why."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    founder_id: Mapped[str] = mapped_column(ForeignKey("founders.id"), index=True,
                                            nullable=False)
    actor: Mapped[str] = mapped_column(String, nullable=False)
    event: Mapped[str] = mapped_column(String, nullable=False)      # DECISION / STAGE / ...
    field: Mapped[str] = mapped_column(String, nullable=False)      # the field that moved
    from_value: Mapped[str | None] = mapped_column(Text)
    to_value: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    founder: Mapped[Founder] = relationship(back_populates="audit")


class RuntimeConfig(Base):
    """The EFFECTIVE config, initialised from the frozen YAML/JSON defaults and
    thereafter owned by the API. `PUT /config` writes here; the repository's
    frozen files are never rewritten (RUNBOOK CP7 §2)."""

    __tablename__ = "runtime_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    sections_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    rubric_version: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow,
                                                 onupdate=utcnow)
    updated_by: Mapped[str | None] = mapped_column(String)


Index("ix_audit_founder_created", AuditLog.founder_id, AuditLog.created_at)
