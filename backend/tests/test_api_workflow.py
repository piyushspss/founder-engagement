"""Human mutation contracts: decision, stage transitions, keep-warm, notes,
owner/next_action — and the audit trail that has to exist for every one of them.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.db.models import utcnow
from app.services.workflow_service import TRANSITIONS, add_months


def _fid(seeded):
    return seeded["founder_ids"][0]


def _move(client, fid, stage, **kw):
    body = {"stage": stage, "actor": "piyush", "reason": f"moving to {stage}", **kw}
    return client.post(f"/founders/{fid}/stage", json=body)


# ------------------------------------------------------------------ decision
def test_decision_requires_actor_and_reason(client, seeded):
    fid = _fid(seeded)
    assert client.post(f"/founders/{fid}/decision",
                       json={"disposition": "POTENTIAL"}).status_code == 422
    assert client.post(f"/founders/{fid}/decision",
                       json={"disposition": "POTENTIAL", "actor": "p",
                             "reason": ""}).status_code == 422


def test_decision_rejects_unknown_disposition(client, seeded):
    fid = _fid(seeded)
    r = client.post(f"/founders/{fid}/decision",
                    json={"disposition": "ENGAGE", "actor": "p", "reason": "x"})
    assert r.status_code == 422                       # not in the frozen enum


def test_decision_is_append_only_and_audited(client, seeded):
    fid = _fid(seeded)
    for disp in ("NEEDS_REVIEW", "POTENTIAL"):
        r = client.post(f"/founders/{fid}/decision",
                        json={"disposition": disp, "actor": "piyush", "reason": f"{disp}!"})
        assert r.status_code == 200, r.text
    detail = client.get(f"/founders/{fid}").json()
    assert len(detail["decision_history"]) == 2
    assert detail["current_decision"]["disposition"] == "POTENTIAL"
    events = client.get(f"/audit/{fid}").json()["events"]
    decisions = [e for e in events if e["event"] == "DECISION"]
    assert [(e["from"], e["to"]) for e in decisions] == [
        (None, "NEEDS_REVIEW"), ("NEEDS_REVIEW", "POTENTIAL")]
    assert all(e["actor"] == "piyush" and e["reason"] for e in decisions)


# --------------------------------------------------------------------- stage
def test_mvp_stage_path(client, seeded):
    fid = _fid(seeded)
    for stage in ("ASSESSMENT", "POTENTIAL", "NURTURING"):
        assert _move(client, fid, stage).status_code == 200
    r = _move(client, fid, "KEEP_WARM", months=6)
    assert r.status_code == 200
    body = r.json()
    # Anchored on the SAME clock the product uses. The whole system dates from
    # utcnow() (views.py resolves a default as_of the same way), so asserting
    # against a LOCAL calendar day made this test fail for any tester east of
    # UTC after 18:30 local — a defect in the test, not in the product (CP11-1).
    assert body["keep_warm_until"] == add_months(utcnow().date(), 6).isoformat()
    events = client.get(f"/audit/{fid}").json()["events"]
    stage_events = [(e["from"], e["to"]) for e in events if e["field"] == "stage"]
    assert stage_events == [("NEW", "ASSESSMENT"), ("ASSESSMENT", "POTENTIAL"),
                            ("POTENTIAL", "NURTURING"), ("NURTURING", "KEEP_WARM")]


@pytest.mark.parametrize("months", [1, 4, 12, 0, None])
def test_keep_warm_rejects_bad_months(client, seeded, months):
    fid = _fid(seeded)
    _move(client, fid, "ASSESSMENT")
    _move(client, fid, "POTENTIAL")
    _move(client, fid, "NURTURING")
    kwargs = {} if months is None else {"months": months}
    r = _move(client, fid, "KEEP_WARM", **kwargs)
    assert r.status_code == 400
    assert client.get(f"/founders/{fid}").json()["workflow"]["stage"] == "NURTURING"


def test_months_rejected_outside_keep_warm(client, seeded):
    fid = _fid(seeded)
    r = _move(client, fid, "ASSESSMENT", months=6)
    assert r.status_code == 400
    assert client.get(f"/founders/{fid}").json()["workflow"]["stage"] == "NEW"


def test_leaving_keep_warm_clears_schedule_and_audits(client, seeded):
    fid = _fid(seeded)
    for stage, kw in (("ASSESSMENT", {}), ("POTENTIAL", {}), ("NURTURING", {}),
                      ("KEEP_WARM", {"months": 3})):
        assert _move(client, fid, stage, **kw).status_code == 200
    assert _move(client, fid, "NURTURING").status_code == 200
    wf = client.get(f"/founders/{fid}").json()["workflow"]
    assert wf["stage"] == "NURTURING"
    assert wf["keep_warm_until"] is None
    cleared = [e for e in client.get(f"/audit/{fid}").json()["events"]
               if e["field"] == "keep_warm_until" and e["to"] is None]
    assert len(cleared) == 1 and "cleared" in cleared[0]["reason"]


def test_invalid_transition_rejected_with_no_mutation(client, seeded):
    fid = _fid(seeded)
    before_detail = client.get(f"/founders/{fid}").json()
    before_audit = client.get(f"/audit/{fid}").json()["events"]

    r = _move(client, fid, "DEAL")                    # NEW -> DEAL is not allowed
    assert r.status_code == 409
    assert r.json()["error"] == "invalid_transition"

    assert client.get(f"/founders/{fid}").json() == before_detail
    assert client.get(f"/audit/{fid}").json()["events"] == before_audit


def test_closed_is_terminal(client, seeded):
    fid = _fid(seeded)
    assert _move(client, fid, "CLOSED").status_code == 200
    for stage in ("NEW", "ASSESSMENT", "POTENTIAL", "NURTURING", "DEAL"):
        assert _move(client, fid, stage).status_code == 409
    assert TRANSITIONS["CLOSED"] == ()


def test_same_stage_is_rejected(client, seeded):
    fid = _fid(seeded)
    r = _move(client, fid, "NEW")
    assert r.status_code == 409 and r.json()["error"] == "no_op"


def test_transition_map_has_no_invented_backward_edges(client):
    assert "NEW" not in TRANSITIONS["ASSESSMENT"]
    assert "ASSESSMENT" not in TRANSITIONS["POTENTIAL"]
    assert "POTENTIAL" not in TRANSITIONS["NURTURING"]


# --------------------------------------------------------------------- notes
def test_notes_append_only_and_audited(client, seeded):
    fid = _fid(seeded)
    for text in ("first", "second"):
        r = client.post(f"/founders/{fid}/notes", json={"text": text, "actor": "piyush"})
        assert r.status_code == 200, r.text
    notes = client.get(f"/founders/{fid}").json()["workflow"]["notes"]
    assert [n["text"] for n in notes] == ["first", "second"]
    assert all(n["actor"] == "piyush" and n["at"] for n in notes)
    assert len([e for e in client.get(f"/audit/{fid}").json()["events"]
                if e["event"] == "NOTE"]) == 2


def test_note_requires_actor(client, seeded):
    fid = _fid(seeded)
    assert client.post(f"/founders/{fid}/notes", json={"text": "x"}).status_code == 422


# -------------------------------------------------- owner / next_action PATCH
def test_patch_workflow_changes_only_owner_and_next_action(client, seeded):
    fid = _fid(seeded)
    _move(client, fid, "ASSESSMENT")
    before = client.get(f"/founders/{fid}").json()["workflow"]
    r = client.patch(f"/founders/{fid}/workflow",
                     json={"actor": "piyush", "reason": "assigning",
                           "owner": "dana", "next_action": "intro call"})
    assert r.status_code == 200, r.text
    after = client.get(f"/founders/{fid}").json()["workflow"]
    assert after["owner"] == "dana" and after["next_action"] == "intro call"
    assert after["stage"] == before["stage"]
    assert after["notes"] == before["notes"]
    assert after["keep_warm_until"] == before["keep_warm_until"]
    fields = {e["field"] for e in client.get(f"/audit/{fid}").json()["events"]
              if e["event"] == "WORKFLOW"}
    assert fields == {"owner", "next_action"}


def test_patch_workflow_rejects_stage_and_requires_reason(client, seeded):
    fid = _fid(seeded)
    assert client.patch(f"/founders/{fid}/workflow",
                        json={"actor": "p", "reason": "r",
                              "stage": "DEAL"}).status_code == 422
    assert client.patch(f"/founders/{fid}/workflow",
                        json={"actor": "p", "owner": "dana"}).status_code == 422
    assert client.patch(f"/founders/{fid}/workflow",
                        json={"actor": "p", "reason": "r"}).status_code == 400


def test_add_months_is_deterministic_and_clamps():
    assert add_months(date(2026, 8, 19), 3) == date(2026, 11, 19)
    assert add_months(date(2026, 8, 31), 6) == date(2027, 2, 28)
    assert add_months(date(2026, 11, 30), 9) == date(2027, 8, 30)
