"""CP9 — keep-warm resurfacing, time simulation, stuck detection.

The property under test throughout: **time passing changes what a person is
shown, and nothing else.** A read with `?as_of=` is a lens, not a clock the
system obeys — it writes no row, moves no stage, and touches no assessment.
Only the human Re-engage action mutates anything.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta

import pytest
from sqlalchemy import inspect, select

from app.db.models import AuditLog, Decision, Founder, Stage, Workflow, utcnow
from app.services.views import (DEFAULT_STUCK_DAYS, STUCK_EXCLUDED_STAGES,
                                is_due, keep_warm_inconsistent)
from app.services.workflow_service import TRANSITIONS, add_months

ACTOR = {"actor": "piyush", "reason": "test"}


# --------------------------------------------------------------- helpers
def walk_to(client, fid, *stages, months=None):
    """Move a founder along the frozen MVP path, one audited human act each."""
    for stage in stages:
        body = {"stage": stage, **ACTOR}
        if stage == "KEEP_WARM":
            body["months"] = months
        r = client.post(f"/founders/{fid}/stage", json=body)
        assert r.status_code == 200, r.text
    return r.json()


def set_keep_warm_until(session, fid, value):
    """Reach past the API to place a founder's due date for boundary testing.
    The API cannot produce arbitrary dates — only +3/6/9 months — so the
    boundaries are set directly and then read back through the API."""
    wf = session.get(Workflow, fid)
    wf.keep_warm_until = value
    session.commit()


def db_fingerprint(session) -> str:
    """Hash every column of every row that CP9 must not touch on a read."""
    blob: dict[str, list] = {}
    for model in (Founder, Decision, Workflow, AuditLog):
        cols = [c.key for c in inspect(model).columns]
        rows = session.execute(select(model)).scalars().all()
        key = (lambda r: r.id) if hasattr(model, "id") else (lambda r: r.founder_id)
        blob[model.__tablename__] = [
            {c: str(getattr(r, c)) for c in cols} for r in sorted(rows, key=key)]
    return hashlib.sha256(json.dumps(blob, sort_keys=True).encode()).hexdigest()


@pytest.fixture()
def keep_warm_founder(client, seeded, session):
    """One founder walked NEW → … → KEEP_WARM 6 months by a human."""
    fid = seeded["founder_ids"][0]
    result = walk_to(client, fid, "ASSESSMENT", "POTENTIAL", "NURTURING", "KEEP_WARM", months=6)
    client.post(f"/founders/{fid}/decision",
                json={"disposition": "POTENTIAL", **ACTOR})
    client.patch(f"/founders/{fid}/workflow", json={"owner": "dana",
                                                    "next_action": "check in", **ACTOR})
    client.post(f"/founders/{fid}/notes", json={"text": "met at HLTH", "actor": "piyush"})
    return fid, date.fromisoformat(result["keep_warm_until"])


# ------------------------------------------------------------ due semantics
def test_due_is_inclusive_on_the_boundary(client, session, keep_warm_founder):
    fid, until = keep_warm_founder

    def due_ids(as_of):
        return [r["founder_id"] for r in
                client.get("/queue", params={"due": True, "as_of": as_of.isoformat(),
                                             "limit": 1000}).json()["rows"]]

    assert due_ids(until - timedelta(days=1)) == []          # due tomorrow -> not due
    assert due_ids(until) == [fid]                           # due today    -> due
    assert due_ids(until + timedelta(days=1)) == [fid]       # due yesterday-> due


def test_due_uses_date_semantics_not_timestamps(session, keep_warm_founder):
    fid, until = keep_warm_founder
    wf = session.get(Workflow, fid)
    assert isinstance(wf.keep_warm_until, date)              # SQL DATE, not a datetime
    assert is_due(wf, until) is True
    assert is_due(wf, until - timedelta(days=1)) is False


def test_only_current_keep_warm_founders_can_be_due(client, session, seeded):
    """Four cases at once: due yesterday, due exactly today, due tomorrow, and a
    founder carrying a stale historical date who has since left KEEP_WARM."""
    ids = seeded["founder_ids"][:4]
    today = date(2027, 3, 1)
    yesterday, tomorrow = today - timedelta(days=1), today + timedelta(days=1)

    for fid in ids:
        walk_to(client, fid, "ASSESSMENT", "POTENTIAL", "NURTURING", "KEEP_WARM", months=3)
    set_keep_warm_until(session, ids[0], yesterday)
    set_keep_warm_until(session, ids[1], today)
    set_keep_warm_until(session, ids[2], tomorrow)

    # ids[3] leaves KEEP_WARM: the schedule is cleared, so no stale date survives
    walk_to(client, ids[3], "NURTURING")
    assert session.get(Workflow, ids[3]).keep_warm_until is None

    rows = client.get("/queue", params={"due": True, "as_of": today.isoformat(),
                                        "limit": 1000}).json()["rows"]
    assert sorted(r["founder_id"] for r in rows) == sorted([ids[0], ids[1]])
    assert client.get("/dashboard", params={"as_of": today.isoformat()}).json()[
        "re_engagement_due"] == 2


def test_malformed_keep_warm_without_a_date_is_reported_not_guessed(client, session, seeded):
    """No API path can create this. Injected directly to prove the read model
    refuses to invent a date — the founder is flagged, never surfaced as due."""
    fid = seeded["founder_ids"][0]
    walk_to(client, fid, "ASSESSMENT", "POTENTIAL", "NURTURING", "KEEP_WARM", months=3)
    set_keep_warm_until(session, fid, None)

    far_future = "2099-01-01"
    assert client.get("/queue", params={"due": True, "as_of": far_future}).json()["total"] == 0
    row = next(r for r in client.get("/queue", params={"limit": 1000}).json()["rows"]
               if r["founder_id"] == fid)
    assert row["due"] is False
    assert row["keep_warm_inconsistent"] is True
    assert any("inconsistent" in reason for reason in row["workflow_reasons"])
    assert client.get("/dashboard").json()["keep_warm_inconsistent"] == 1
    assert keep_warm_inconsistent(session.get(Workflow, fid)) is True


def test_api_cannot_create_keep_warm_without_a_date(client, seeded, session):
    fid = seeded["founder_ids"][0]
    walk_to(client, fid, "ASSESSMENT", "POTENTIAL", "NURTURING")
    for body in ({"stage": "KEEP_WARM", **ACTOR},
                 {"stage": "KEEP_WARM", "months": 0, **ACTOR},
                 {"stage": "KEEP_WARM", "months": 5, **ACTOR}):
        assert client.post(f"/founders/{fid}/stage", json=body).status_code == 400
    wf = session.get(Workflow, fid)
    assert wf.stage == "NURTURING" and wf.keep_warm_until is None


# ------------------------------------------------ workflow vs machine reason
def test_due_is_a_workflow_reason_not_a_machine_reason(client, keep_warm_founder):
    """A ROUTINE founder can be due. That is not a contradiction, and the API
    must not blur it: machine reasons and workflow obligations are two fields."""
    fid, until = keep_warm_founder
    row = next(r for r in client.get(
        "/queue", params={"as_of": until.isoformat(), "limit": 1000}).json()["rows"]
        if r["founder_id"] == fid)
    assert row["workflow_reasons"] == ["Re-engagement due"]
    assert "Re-engagement due" not in row["why_surfaced"]


def test_time_passing_changes_no_machine_dimension(client, keep_warm_founder):
    fid, until = keep_warm_founder
    machine_keys = ("attention", "potential", "confidence", "data_state",
                    "recommended_action", "broad_score", "assessment_version",
                    "rubric_version")

    def snapshot(as_of):
        row = next(r for r in client.get(
            "/queue", params={"as_of": as_of, "limit": 1000}).json()["rows"]
            if r["founder_id"] == fid)
        return {k: row[k] for k in machine_keys}

    before = snapshot(date.today().isoformat())
    after = snapshot((until + timedelta(days=365)).isoformat())
    assert before == after


# --------------------------------------------------------- as_of purity
def test_as_of_reads_write_nothing(client, session, keep_warm_founder):
    fid, until = keep_warm_founder
    session.expire_all()
    before = db_fingerprint(session)

    for as_of in (until - timedelta(days=1), until, until + timedelta(days=400),
                  date(2099, 12, 31)):
        client.get("/queue", params={"as_of": as_of.isoformat(), "limit": 1000})
        client.get("/queue", params={"as_of": as_of.isoformat(), "due": True})
        client.get("/dashboard", params={"as_of": as_of.isoformat()})
        client.get(f"/founders/{fid}", params={"as_of": as_of.isoformat()})

    session.expire_all()
    assert db_fingerprint(session) == before                 # HARD GATE


def test_invalid_as_of_is_rejected(client, seeded):
    for bad in ("yesterday", "2027-13-01", "01/02/2027", "2027-02-30", ""):
        for path, params in (("/queue", {"as_of": bad}), ("/dashboard", {"as_of": bad})):
            r = client.get(path, params=params)
            assert r.status_code == 422, (path, bad, r.status_code)
    # and a valid one still works
    assert client.get("/queue", params={"as_of": "2027-02-19"}).status_code == 200


# ------------------------------------------------------------- re-engage
def test_reengage_edge_exists_and_no_generic_backward_edges():
    assert "NURTURING" in TRANSITIONS[Stage.KEEP_WARM.value]      # the authorized edge
    assert "NEW" not in TRANSITIONS[Stage.KEEP_WARM.value]
    assert "ASSESSMENT" not in TRANSITIONS[Stage.KEEP_WARM.value]
    assert "POTENTIAL" not in TRANSITIONS[Stage.KEEP_WARM.value]
    assert TRANSITIONS[Stage.CLOSED.value] == ()


def test_reengage_preserves_everything_except_authorized_workflow_fields(
        client, session, keep_warm_founder):
    fid, until = keep_warm_founder
    session.expire_all()
    founder = session.get(Founder, fid)
    before = {
        "assessment": json.dumps(founder.assessment_json, sort_keys=True),
        "canonical": json.dumps(founder.canonical_json, sort_keys=True),
        "assessment_version": founder.assessment_version,
        "assessed_at": founder.assessed_at,
        "rubric_version": founder.rubric_version,
        "decision": founder.current_decision.disposition,
        "decision_reason": founder.current_decision.reason,
        "owner": founder.workflow.owner,
        "next_action": founder.workflow.next_action,
        "notes": json.dumps(founder.workflow.notes, sort_keys=True),
        "stage_changed_at": founder.workflow.stage_changed_at,
    }

    r = client.post(f"/founders/{fid}/stage",
                    json={"stage": "NURTURING", "actor": "piyush",
                          "reason": "re-engaging — keep-warm date reached"})
    assert r.status_code == 200, r.text
    assert r.json() == {"founder_id": fid, "from": "KEEP_WARM", "to": "NURTURING",
                        "keep_warm_until": None}

    session.expire_all()
    founder = session.get(Founder, fid)
    wf = founder.workflow
    # authorized changes
    assert wf.stage == "NURTURING"
    assert wf.keep_warm_until is None
    assert wf.stage_changed_at > before["stage_changed_at"]
    # everything else
    assert json.dumps(founder.assessment_json, sort_keys=True) == before["assessment"]
    assert json.dumps(founder.canonical_json, sort_keys=True) == before["canonical"]
    assert founder.assessment_version == before["assessment_version"]
    assert founder.assessed_at == before["assessed_at"]
    assert founder.rubric_version == before["rubric_version"]
    assert founder.current_decision.disposition == before["decision"]
    assert founder.current_decision.reason == before["decision_reason"]
    assert wf.owner == before["owner"]
    assert wf.next_action == before["next_action"]
    assert json.dumps(wf.notes, sort_keys=True) == before["notes"]

    # and the founder has left the due set
    assert client.get("/queue", params={"due": True, "as_of": "2099-01-01"}
                      ).json()["total"] == 0


def test_reengage_audit_sequence(client, keep_warm_founder):
    """NURTURING → KEEP_WARM 6m → (time passes, read-only) → Re-engage.
    The time-passing step must contribute no audit event."""
    fid, until = keep_warm_founder
    before_events = client.get(f"/audit/{fid}").json()["events"]

    for as_of in (until - timedelta(days=1), until, until + timedelta(days=30)):
        client.get("/queue", params={"as_of": as_of.isoformat(), "due": True})
        client.get("/dashboard", params={"as_of": as_of.isoformat()})
    assert client.get(f"/audit/{fid}").json()["events"] == before_events   # time is silent

    client.post(f"/founders/{fid}/stage",
                json={"stage": "NURTURING", "actor": "piyush",
                      "reason": "re-engaging after keep-warm"})
    new = client.get(f"/audit/{fid}").json()["events"][len(before_events):]
    assert [(e["event"], e["field"], e["from"], e["to"]) for e in new] == [
        ("STAGE", "stage", "KEEP_WARM", "NURTURING"),
        ("STAGE", "keep_warm_until", until.isoformat(), None),
    ]
    assert all(e["actor"] == "piyush" and e["reason"] for e in new)
    assert "cleared" in new[1]["reason"]


def test_reengage_does_not_change_disposition_or_rescore(client, session, keep_warm_founder):
    fid, _ = keep_warm_founder
    before_decisions = len(client.get(f"/founders/{fid}").json()["decision_history"])
    client.post(f"/founders/{fid}/stage",
                json={"stage": "NURTURING", "actor": "piyush", "reason": "re-engage"})
    detail = client.get(f"/founders/{fid}").json()
    assert len(detail["decision_history"]) == before_decisions
    assert detail["current_decision"]["disposition"] == "POTENTIAL"
    assert not [e for e in client.get(f"/audit/{fid}").json()["events"]
                if e["event"] == "RESCORE"]


# ----------------------------------------------------------------- stuck
def age_stage(session, fid, days, as_of):
    wf = session.get(Workflow, fid)
    wf.stage_changed_at = __import__("datetime").datetime.combine(
        as_of, __import__("datetime").datetime.min.time()) - timedelta(days=days)
    session.commit()


def test_stuck_boundaries_are_strictly_greater_than(client, session, seeded):
    """Frozen wording is "stuck > N days", implemented literally."""
    as_of = date(2027, 6, 1)
    n = DEFAULT_STUCK_DAYS
    ids = seeded["founder_ids"][:3]
    for fid in ids:
        client.post(f"/founders/{fid}/stage", json={"stage": "ASSESSMENT", **ACTOR})
    age_stage(session, ids[0], n - 1, as_of)
    age_stage(session, ids[1], n, as_of)
    age_stage(session, ids[2], n + 1, as_of)
    # every other seeded founder was created "now", far in the past of as_of, so
    # compare the delta rather than the absolute count
    for fid in seeded["founder_ids"][3:]:
        age_stage(session, fid, 0, as_of)

    body = client.get("/dashboard", params={"as_of": as_of.isoformat()}).json()
    assert body["stuck"]["threshold_days"] == n
    assert body["stuck"]["comparison"] == "> N days in current stage"
    assert body["stuck"]["count"] == 1                       # only the N+1 founder


def test_stuck_threshold_is_a_request_parameter(client, session, seeded):
    as_of = date(2027, 6, 1)
    for fid in seeded["founder_ids"]:
        age_stage(session, fid, 0, as_of)
    fid = seeded["founder_ids"][0]
    client.post(f"/founders/{fid}/stage", json={"stage": "ASSESSMENT", **ACTOR})
    age_stage(session, fid, 10, as_of)

    for stuck_days, expected in ((14, 0), (9, 1), (10, 0)):
        body = client.get("/dashboard", params={"as_of": as_of.isoformat(),
                                                "stuck_days": stuck_days}).json()
        assert body["stuck"]["count"] == expected, stuck_days


def test_waiting_on_purpose_is_not_stuck(client, session, seeded):
    """KEEP_WARM is represented by its due date, not by generic ageing; CLOSED
    and DEAL are excluded as they were in CP7."""
    as_of = date(2027, 6, 1)
    for fid in seeded["founder_ids"]:
        age_stage(session, fid, 0, as_of)
    keep, closed = seeded["founder_ids"][0], seeded["founder_ids"][1]

    walk_to(client, keep, "ASSESSMENT", "POTENTIAL", "NURTURING", "KEEP_WARM", months=3)
    client.post(f"/founders/{closed}/stage", json={"stage": "CLOSED", **ACTOR})
    age_stage(session, keep, 400, as_of)
    age_stage(session, closed, 400, as_of)

    body = client.get("/dashboard", params={"as_of": as_of.isoformat()}).json()
    assert body["stuck"]["count"] == 0
    assert set(body["stuck"]["excluded_stages"]) == set(STUCK_EXCLUDED_STAGES)


def test_as_of_moves_stuck_and_due_together(client, session, keep_warm_founder):
    fid, until = keep_warm_founder
    early = client.get("/dashboard", params={"as_of": (until - timedelta(days=1)).isoformat()}
                       ).json()
    late = client.get("/dashboard", params={"as_of": until.isoformat()}).json()
    assert early["re_engagement_due"] == 0
    assert late["re_engagement_due"] == 1
    assert late["stuck"]["count"] >= early["stuck"]["count"]   # ageing only grows


def test_add_months_matches_the_keep_warm_options():
    anchor = date(2026, 8, 19)
    assert [add_months(anchor, m) for m in (3, 6, 9)] == [
        date(2026, 11, 19), date(2027, 2, 19), date(2027, 5, 19)]
