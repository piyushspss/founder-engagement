"""Human-owned mutations: decision, stage, notes, owner/next_action.

Every function here requires an `actor` and a `reason` and writes an audit row.
That is the whole point of the module: the machine can explain a *score*, but
only the audit log can explain a *decision*, and a decision without an author is
not a decision anyone can be accountable for.

The stage graph is an explicit transition map, not `Stage -> Stage`. An
enum-to-enum move would let a founder go CLOSED → DEAL or KEEP_WARM → NEW
because nothing said otherwise; the conservative map below says otherwise.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AuditLog, Decision, Disposition, Founder, Stage, utcnow

KEEP_WARM_MONTHS = (3, 6, 9)

#: Conservative transition map (documented in README / CHECKPOINT_LOG).
#: The frozen workflow (PLAN §5) states the intended path
#: NEW → ASSESSMENT → POTENTIAL → NURTURING → KEEP_WARM and "later movement
#: toward DEAL or CLOSED". Where it is silent we chose the RESTRICTIVE reading:
#:   * CLOSED is terminal — reopening is a new record decision, not a stage move;
#:   * no backward moves are invented (POTENTIAL → ASSESSMENT is NOT allowed);
#:   * KEEP_WARM ⇄ NURTURING is allowed both ways because re-engagement is the
#:     explicit product loop (PLAN §5, CP9);
#:   * CLOSED is reachable from every non-terminal stage — a human may always
#:     stop pursuing a founder.
TRANSITIONS: dict[str, tuple[str, ...]] = {
    Stage.NEW.value:        (Stage.ASSESSMENT.value, Stage.CLOSED.value),
    Stage.ASSESSMENT.value: (Stage.POTENTIAL.value, Stage.NURTURING.value, Stage.CLOSED.value),
    Stage.POTENTIAL.value:  (Stage.NURTURING.value, Stage.KEEP_WARM.value, Stage.DEAL.value,
                             Stage.CLOSED.value),
    Stage.NURTURING.value:  (Stage.KEEP_WARM.value, Stage.DEAL.value, Stage.CLOSED.value),
    Stage.KEEP_WARM.value:  (Stage.NURTURING.value, Stage.DEAL.value, Stage.CLOSED.value),
    Stage.DEAL.value:       (Stage.CLOSED.value,),
    Stage.CLOSED.value:     (),
}


class WorkflowError(ValueError):
    """Rejected human mutation. Nothing has been written when this is raised."""

    def __init__(self, message: str, code: str = "invalid_transition"):
        self.code = code
        super().__init__(message)


# ----------------------------------------------------------------- utilities
def add_months(anchor: date, months: int) -> date:
    """Deterministic calendar-month addition, clamped to the month end."""
    total = anchor.month - 1 + months
    year = anchor.year + total // 12
    month = total % 12 + 1
    last = [31, 29 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 28,
            31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    return date(year, month, min(anchor.day, last))


def _audit(session: Session, founder_id: str, actor: str, event: str, field: str,
           before: Any, after: Any, reason: str | None) -> AuditLog:
    """Append one audit row. Called on every human mutation in this module.

    Stamped with `utcnow()` — the product dates everything from UTC and no local
    clock or browser timezone takes part. The row is added to the caller's
    session, so it commits or rolls back with the change it describes."""
    row = AuditLog(founder_id=founder_id, actor=actor, event=event, field=field,
                   from_value=None if before is None else str(before),
                   to_value=None if after is None else str(after),
                   reason=reason, created_at=utcnow())
    session.add(row)
    return row


def _require(value: str | None, name: str) -> str:
    """Return a stripped non-empty string, or reject the whole mutation.

    `actor` and `reason` are mandatory on every human act: an unattributed or
    unexplained decision is not one anybody can be accountable for."""
    if value is None or not str(value).strip():
        raise WorkflowError(f"{name} is required", code="missing_field")
    return str(value).strip()


# ------------------------------------------------------------------ decision
def record_decision(session: Session, founder: Founder, *, disposition: str, actor: str,
                    reason: str) -> Decision:
    """Record a HUMAN disposition. Append-only, audited.

    Disposition is human authority: no machine path — import, assess, rescore,
    config change or AI check — reaches this function. Decisions are appended
    rather than overwritten, so `founder.current_decision` is the latest of a
    preserved history. Touches no assessment field and no stage."""
    actor = _require(actor, "actor")
    reason = _require(reason, "reason")
    try:
        disp = Disposition(disposition)
    except ValueError:
        raise WorkflowError(
            f"unknown disposition {disposition!r}; allowed: "
            f"{', '.join(d.value for d in Disposition)}", code="invalid_disposition")

    previous = founder.current_decision
    row = Decision(founder_id=founder.id, disposition=disp.value, reason=reason,
                   actor=actor, created_at=utcnow())
    session.add(row)
    _audit(session, founder.id, actor, "DECISION", "decision",
           previous.disposition if previous else None, disp.value, reason)
    session.flush()
    return row


# --------------------------------------------------------------------- stage
def change_stage(session: Session, founder: Founder, *, target: str, actor: str, reason: str,
                 keep_warm_months: int | None = None,
                 now: datetime | None = None) -> dict[str, Any]:
    """Move a founder to `target` if `TRANSITIONS` allows it. HUMAN-only, audited.

    Rejects anything the conservative map does not permit, plus same-stage
    no-ops, and raises BEFORE writing so a rejected move leaves no trace.

    KEEP-WARM SEMANTICS: entering KEEP_WARM requires `keep_warm_months` in
    3/6/9 and sets `keep_warm_until` to that many calendar months from the UTC
    date; leaving KEEP_WARM clears the now-obsolete schedule and audits the
    clearing. Both sides of the re-engagement loop are therefore explicit human
    acts — nothing here ever moves a stage on the machine's behalf, and the
    deterministic assessment is neither read nor written."""
    actor = _require(actor, "actor")
    reason = _require(reason, "reason")
    try:
        want = Stage(target)
    except ValueError:
        raise WorkflowError(f"unknown stage {target!r}; allowed: "
                            f"{', '.join(s.value for s in Stage)}", code="invalid_stage")

    wf = founder.workflow
    if wf is None:
        raise WorkflowError("founder has no workflow row", code="not_found")
    current = wf.stage
    if want.value == current:
        raise WorkflowError(f"founder is already in stage {current}", code="no_op")
    if want.value not in TRANSITIONS.get(current, ()):
        allowed = ", ".join(TRANSITIONS.get(current, ())) or "(terminal stage)"
        raise WorkflowError(f"{current} -> {want.value} is not an allowed transition; "
                            f"allowed from {current}: {allowed}")

    if want is Stage.KEEP_WARM:
        if keep_warm_months not in KEEP_WARM_MONTHS:
            raise WorkflowError(
                f"KEEP_WARM requires months in {list(KEEP_WARM_MONTHS)}; got "
                f"{keep_warm_months!r}", code="invalid_keep_warm_months")
    elif keep_warm_months is not None:
        raise WorkflowError("months is only valid when moving to KEEP_WARM",
                            code="invalid_keep_warm_months")

    stamp = now or utcnow()
    before_until = wf.keep_warm_until
    wf.stage = want.value
    wf.stage_changed_at = stamp
    wf.updated_at = stamp
    _audit(session, founder.id, actor, "STAGE", "stage", current, want.value, reason)

    if want is Stage.KEEP_WARM:
        wf.keep_warm_until = add_months(stamp.date(), keep_warm_months)
        _audit(session, founder.id, actor, "STAGE", "keep_warm_until", before_until,
               wf.keep_warm_until, f"{reason} (keep warm {keep_warm_months} months)")
    elif before_until is not None:
        # Leaving KEEP_WARM: the schedule is obsolete, clearing it is audited.
        wf.keep_warm_until = None
        _audit(session, founder.id, actor, "STAGE", "keep_warm_until", before_until, None,
               f"{reason} (left KEEP_WARM — re-engagement schedule cleared)")

    session.flush()
    return {"from": current, "to": wf.stage, "keep_warm_until": wf.keep_warm_until}


# --------------------------------------------------------------------- notes
def append_note(session: Session, founder: Founder, *, text: str, actor: str) -> dict[str, Any]:
    """Append a human note. Append-only — notes are never edited or removed.

    The JSON column is REASSIGNED rather than mutated in place; SQLAlchemy does
    not detect in-place mutation of a JSON list and the write would be lost."""
    actor = _require(actor, "actor")
    text = _require(text, "text")
    wf = founder.workflow
    if wf is None:
        raise WorkflowError("founder has no workflow row", code="not_found")
    note = {"text": text, "actor": actor, "at": utcnow().isoformat()}
    wf.notes = list(wf.notes or []) + [note]        # new list: JSON columns need reassignment
    wf.updated_at = utcnow()
    _audit(session, founder.id, actor, "NOTE", "notes", len(wf.notes) - 1, len(wf.notes), text)
    session.flush()
    return note


# ----------------------------------------------------- owner / next_action
def patch_workflow(session: Session, founder: Founder, *, actor: str, reason: str,
                   owner: str | None = None, next_action: str | None = None,
                   fields_present: set[str] | None = None) -> dict[str, Any]:
    """The transport-completion endpoint. Touches `owner` and `next_action` and
    nothing else — stage, keep_warm_until, notes and decisions are unreachable
    from here by construction."""
    actor = _require(actor, "actor")
    reason = _require(reason, "reason")
    wf = founder.workflow
    if wf is None:
        raise WorkflowError("founder has no workflow row", code="not_found")
    present = fields_present if fields_present is not None else {
        k for k, v in (("owner", owner), ("next_action", next_action)) if v is not None}
    if not present:
        raise WorkflowError("supply at least one of: owner, next_action",
                            code="missing_field")

    changed: dict[str, Any] = {}
    for name, value in (("owner", owner), ("next_action", next_action)):
        if name not in present:
            continue
        before = getattr(wf, name)
        if before == value:
            continue
        setattr(wf, name, value)
        _audit(session, founder.id, actor, "WORKFLOW", name, before, value, reason)
        changed[name] = {"from": before, "to": value}
    if changed:
        wf.updated_at = utcnow()
    session.flush()
    return changed
