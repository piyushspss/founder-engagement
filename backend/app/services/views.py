"""Read models: queue rows, founder detail, dashboard metrics.

These are projections over persisted state. They compute no assessment and make
no judgment — where a number here looks like a judgment (`why_surfaced`) it is
assembled from the stored policy trace and signals, never recalculated.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditLog, Founder, Stage, Workflow, utcnow
from app.services.workflow_service import TRANSITIONS

#: Queue ordering — recall-first. PRIORITY_REVIEW before REVIEW before ROUTINE,
#: then confidence descending, then founder id as a stable tie-breaker.
#: `potential` is deliberately ABSENT from the sort: UNKNOWN is not a worse
#: answer than LOW, it is a different one (PLAN §4.5).
ATTENTION_RANK = {"PRIORITY_REVIEW": 0, "REVIEW": 1, "ROUTINE": 2}

LOW_CONFIDENCE = 0.6      # the operating threshold from weights.yaml thresholds

#: MVP default for "stuck". The frozen wording is "stuck > N days", so the
#: comparison is STRICTLY greater-than: at exactly N days a founder is not yet
#: stuck. Overridable per request via `?stuck_days=`; deliberately NOT part of
#: the rubric/config — it is an operational display threshold, not a scoring one,
#: and it must never enter `rubric_version`.
DEFAULT_STUCK_DAYS = 14

#: Stages where waiting is the intended state, so ageing is not "stuck":
#:   KEEP_WARM  the wait IS the commitment; it is represented by its due date;
#:   CLOSED     nobody is waiting on it;
#:   DEAL       terminal-adjacent, excluded since CP7 — interpretation preserved.
STUCK_EXCLUDED_STAGES = (Stage.KEEP_WARM.value, Stage.CLOSED.value, Stage.DEAL.value)


def _assessment(f: Founder) -> dict[str, Any]:
    """The stored assessment JSON, or {} for a founder not yet assessed."""
    return f.assessment_json or {}


def why_surfaced(f: Founder) -> list[str]:
    """MACHINE reasons only — what the assessment says about this founder.

    Time-derived workflow obligations deliberately do NOT appear here (CP9 §4):
    a keep-warm date falling due is a human commitment coming round, not the
    model changing its mind. See `workflow_reasons`."""
    a = _assessment(f)
    out: list[str] = []
    exceptional = a.get("exceptional") or {}
    if exceptional.get("flag"):
        out.append(f"Exceptional evidence: {exceptional.get('rule', '')}".strip())
    observed = [s for s in a.get("signals", []) if s.get("observed")]
    for s in sorted(observed, key=lambda s: -(s.get("value") or 0))[:2]:
        out.append(f"{s['name']} {s.get('strength', '')}".strip())
    if a.get("data_state") in ("PARTIAL", "NEEDS_INFORMATION"):
        out.append(f"Data state {a['data_state']}")
    return out


def workflow_reasons(wf: Workflow | None, as_of: date) -> list[str]:
    """HUMAN/time-derived reasons this founder is in front of someone today.

    Separate from `why_surfaced` on purpose. A founder may legitimately read
    "machine attention: ROUTINE" and "workflow: Re-engagement due" at the same
    time — the first is the model's current assessment, the second is a
    commitment a person made coming due. Neither contradicts the other."""
    out: list[str] = []
    if is_due(wf, as_of):
        out.append("Re-engagement due")
    if keep_warm_inconsistent(wf):
        out.append("Keep-warm date missing — inconsistent workflow data")
    return out


def is_due(wf: Workflow | None, as_of: date) -> bool:
    """Re-engagement due, exactly and only when:

        stage == KEEP_WARM  AND  keep_warm_until <= as_of

    Both sides are `datetime.date`, never datetimes: `keep_warm_until` is a
    date-only commitment ("come back to this founder on this day"), so it is
    stored as SQL DATE and compared as a date. The comparison is INCLUSIVE, so
    due-today is due, due-yesterday is due, and due-tomorrow is not. No clock,
    no timezone and no browser locale takes part in this decision."""
    if wf is None or wf.stage != Stage.KEEP_WARM.value or wf.keep_warm_until is None:
        return False
    return wf.keep_warm_until <= as_of


def keep_warm_inconsistent(wf: Workflow | None) -> bool:
    """KEEP_WARM with no date. No API path can produce this (the stage endpoint
    requires months in {3,6,9}); it is reported, never guessed at, and never
    counted as due."""
    return bool(wf and wf.stage == Stage.KEEP_WARM.value and wf.keep_warm_until is None)


def queue_row(f: Founder, as_of: date) -> dict[str, Any]:
    """One queue/table row, with machine and human fields kept visibly apart.

    `why_surfaced` carries MACHINE reasons and `workflow_reasons` carries
    human/time-derived ones. That separation is the product point: a founder can
    read "machine attention: Routine" and "workflow: Re-engagement due" at the
    same time without contradiction, because re-engagement is derived from
    workflow state rather than manufactured as machine state.

    `as_of` is a read-time lens only — this function writes nothing."""
    a = _assessment(f)
    wf = f.workflow
    decision = f.current_decision
    due = is_due(wf, as_of)
    return {
        "founder_id": f.id,
        "mdm_person_id": f.mdm_person_id,
        # ---- machine ----
        "attention": a.get("attention"),
        "potential": a.get("potential"),
        "confidence": a.get("confidence"),
        "data_state": a.get("data_state"),
        "recommended_action": a.get("recommended_action"),
        "broad_score": a.get("broad_score"),
        "archetype": (a.get("archetype") or {}).get("archetype"),
        "exceptional": bool((a.get("exceptional") or {}).get("flag")),
        "exceptional_count": len((a.get("exceptional") or {}).get("signals", [])),
        "why_surfaced": why_surfaced(f),                 # machine reasons

        "assessment_version": f.assessment_version,
        "assessed_at": f.assessed_at,
        "rubric_version": f.rubric_version,
        "duplicate_count": len(f.duplicate_flags or []),
        # ---- human ----
        "stage": wf.stage if wf else None,
        "owner": wf.owner if wf else None,
        "next_action": wf.next_action if wf else None,
        "keep_warm_until": wf.keep_warm_until if wf else None,
        "due": due,
        "workflow_reasons": workflow_reasons(wf, as_of),  # human / time-derived
        "keep_warm_inconsistent": keep_warm_inconsistent(wf),
        "current_decision": decision.disposition if decision else None,
        "decided_at": decision.created_at if decision else None,
        "notes_count": len(wf.notes or []) if wf else 0,
        "stage_changed_at": wf.stage_changed_at if wf else None,
        "created_at": f.created_at,
    }


def list_queue(session: Session, *, attention: list[str] | None = None,
               data_state: list[str] | None = None, stage: list[str] | None = None,
               owner: str | None = None, due: bool | None = None,
               as_of: date | None = None, limit: int = 100,
               offset: int = 0) -> dict[str, Any]:
    """The priority queue, filtered server-side and ordered by the API's rule
    (attention → evidence confidence → id).

    POTENTIAL IS NEVER THE RANKING KEY: ordering by a quality claim would bury
    exactly the uncertain founders the recall-first policy exists to surface.

    `as_of` defaults to today in UTC and is a pure READ-TIME LENS — it changes
    what a person is shown and writes no row, stage, assessment or audit entry."""
    as_of = as_of or utcnow().date()
    founders = list(session.execute(
        select(Founder).outerjoin(Workflow).order_by(Founder.id)).scalars())

    rows = [queue_row(f, as_of) for f in founders]
    if attention:
        rows = [r for r in rows if r["attention"] in set(attention)]
    if data_state:
        rows = [r for r in rows if r["data_state"] in set(data_state)]
    if stage:
        rows = [r for r in rows if r["stage"] in set(stage)]
    if owner is not None:
        rows = ([r for r in rows if not r["owner"]] if owner == ""
                else [r for r in rows if r["owner"] == owner])
    if due is not None:
        rows = [r for r in rows if r["due"] is due]

    rows.sort(key=lambda r: (ATTENTION_RANK.get(r["attention"], 99),
                             -(r["confidence"] or 0.0), r["founder_id"]))
    return {"total": len(rows), "as_of": as_of, "limit": limit, "offset": offset,
            "rows": rows[offset:offset + limit]}


# -------------------------------------------------------------------- detail
def founder_detail(session: Session, f: Founder, as_of: date | None = None) -> dict[str, Any]:
    """Sections are kept apart on purpose: machine assessment never carries a
    disposition or a stage, and human state never carries a score."""
    as_of = as_of or utcnow().date()
    wf = f.workflow
    decision = f.current_decision
    return {
        "founder_id": f.id,
        "facts": {
            "mdm_person_id": f.mdm_person_id,
            "funnel": f.funnel,
            "source": f.source,
            "created_at": f.created_at,
            "raw": f.raw_json,
            "canonical": f.canonical_json,
        },
        "assessment": f.assessment_json,
        "assessment_metadata": {
            "assessment_version": f.assessment_version,
            "assessed_at": f.assessed_at,
            "rubric_version": f.rubric_version,
            "engine_version": f.engine_version,
        },
        "current_decision": None if decision is None else {
            "disposition": decision.disposition, "reason": decision.reason,
            "actor": decision.actor, "at": decision.created_at,
        },
        "decision_history": [
            {"disposition": d.disposition, "reason": d.reason, "actor": d.actor,
             "at": d.created_at} for d in f.decisions],
        "workflow": None if wf is None else {
            "stage": wf.stage, "owner": wf.owner, "next_action": wf.next_action,
            "keep_warm_until": wf.keep_warm_until, "notes": wf.notes or [],
            "stage_changed_at": wf.stage_changed_at,
            "due": is_due(wf, as_of),
            "workflow_reasons": workflow_reasons(wf, as_of),
            "keep_warm_inconsistent": keep_warm_inconsistent(wf),
            "allowed_transitions": list(TRANSITIONS.get(wf.stage, ())),
        },
        "duplicates": {
            "links": f.duplicate_flags or [],
            "auto_merged": False,
            "policy": "A6b — flagged, never merged.",
        },
    }


# ----------------------------------------------------------------- dashboard
def dashboard(session: Session, *, stuck_days: int = DEFAULT_STUCK_DAYS,
              as_of: date | None = None, weeks: int = 8) -> dict[str, Any]:
    """Operating metrics: stage counts, weekly intake, ageing, stuck, due,
    low-confidence share and human decisions recorded.

    `stuck_days` is an OPERATIONAL DISPLAY THRESHOLD and never enters
    `rubric_version` — changing it changes a view, not an assessment. Read-only
    and `as_of`-lensed like the queue."""
    as_of = as_of or utcnow().date()
    founders = list(session.execute(select(Founder)).scalars())
    total = len(founders)
    now = datetime.combine(as_of, datetime.min.time())

    stage_counts = Counter()
    ageing_buckets = Counter()
    stuck = 0
    due = 0
    inconsistent = 0
    ages: list[int] = []
    for f in founders:
        wf = f.workflow
        stage = wf.stage if wf else "UNKNOWN"
        stage_counts[stage] += 1
        if wf:
            days = max((now - wf.stage_changed_at).days, 0)
            ages.append(days)
            bucket = ("0-6d" if days < 7 else "7-13d" if days < 14
                      else "14-29d" if days < 30 else "30d+")
            ageing_buckets[bucket] += 1
            # "> N days", strictly: at exactly N days a founder is not yet stuck.
            if days > stuck_days and stage not in STUCK_EXCLUDED_STAGES:
                stuck += 1
            if is_due(wf, as_of):
                due += 1
            if keep_warm_inconsistent(wf):
                inconsistent += 1

    weekly: Counter = Counter()
    for f in founders:
        monday = f.created_at.date() - timedelta(days=f.created_at.weekday())
        weekly[monday.isoformat()] += 1
    recent_weeks = sorted(weekly)[-weeks:]

    attention = Counter(_assessment(f).get("attention") for f in founders)
    potential = Counter(_assessment(f).get("potential") for f in founders)
    data_state = Counter(_assessment(f).get("data_state") for f in founders)
    low_conf = sum(1 for f in founders if (f.confidence or 0.0) < LOW_CONFIDENCE)
    decided = sum(1 for f in founders if f.current_decision is not None)

    return {
        "as_of": as_of,
        "founders": total,
        "stage_counts": {s.value: stage_counts.get(s.value, 0) for s in Stage},
        "weekly_intake": [{"week_starting": w, "count": weekly[w]} for w in recent_weeks],
        "ageing_in_stage": {k: ageing_buckets.get(k, 0)
                            for k in ("0-6d", "7-13d", "14-29d", "30d+")},
        "median_days_in_stage": (sorted(ages)[len(ages) // 2] if ages else 0),
        "stuck": {"threshold_days": stuck_days, "count": stuck,
                  "comparison": "> N days in current stage",
                  "excluded_stages": list(STUCK_EXCLUDED_STAGES)},
        "re_engagement_due": due,
        "keep_warm_inconsistent": inconsistent,
        "review_queue_size": attention.get("PRIORITY_REVIEW", 0) + attention.get("REVIEW", 0),
        "attention_distribution": dict(attention),
        "potential_distribution": dict(potential),
        "data_state_distribution": dict(data_state),
        "low_confidence_pct": round(100.0 * low_conf / total, 2) if total else 0.0,
        "low_confidence_threshold": LOW_CONFIDENCE,
        "human_decisions_recorded": decided,
    }


def audit_trail(session: Session, founder_id: str) -> list[dict[str, Any]]:
    """The founder's full audit history in insertion order.

    Machine events (RESCORE) and human events (DECISION, STAGE, NOTE) share one
    ordered trail but keep distinct `event` values, so "who changed what, when
    and why" stays answerable. The optional AI layer creates no event here."""
    rows = session.execute(
        select(AuditLog).where(AuditLog.founder_id == founder_id)
        .order_by(AuditLog.id)).scalars()
    return [{"id": r.id, "actor": r.actor, "event": r.event, "field": r.field,
             "from": r.from_value, "to": r.to_value, "reason": r.reason, "at": r.created_at}
            for r in rows]
