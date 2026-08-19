"""Rescore is a MACHINE act. The hard gate: every decision and workflow row is
byte/value identical across a rescore, including one that changes the rubric.

The snapshots below are taken at the DATABASE level (every column of every row),
not through the API, so a change that the API happens not to expose would still
be caught."""

from __future__ import annotations

import pytest
from sqlalchemy import inspect, select

from app.db.models import Decision, Founder, Workflow


def snapshot(session, model):
    """Every column of every row, ordered — the literal 'byte-identical' claim."""
    cols = [c.key for c in inspect(model).columns]
    rows = session.execute(select(model)).scalars().all()
    key = (lambda r: r.id) if hasattr(model, "id") else (lambda r: r.founder_id)
    return [{c: getattr(r, c) for c in cols} for r in sorted(rows, key=key)]


def human_snapshot(session):
    return {"decisions": snapshot(session, Decision), "workflow": snapshot(session, Workflow)}


def machine_snapshot(session):
    return {f.id: {"assessment_version": f.assessment_version, "assessed_at": f.assessed_at,
                   "rubric_version": f.rubric_version, "assessment": f.assessment_json,
                   "canonical": f.canonical_json}
            for f in session.execute(select(Founder)).scalars()}


@pytest.fixture()
def with_human_activity(client, seeded):
    """Give three founders real human history so there is something to protect."""
    ids = seeded["founder_ids"][:3]
    for i, fid in enumerate(ids):
        client.post(f"/founders/{fid}/decision",
                    json={"disposition": "POTENTIAL", "actor": "piyush", "reason": "strong"})
        client.post(f"/founders/{fid}/stage",
                    json={"stage": "ASSESSMENT", "actor": "piyush", "reason": "triage"})
        if i == 0:
            client.post(f"/founders/{fid}/stage",
                        json={"stage": "POTENTIAL", "actor": "piyush", "reason": "promising"})
            client.post(f"/founders/{fid}/stage",
                        json={"stage": "NURTURING", "actor": "piyush", "reason": "warm intro"})
            client.post(f"/founders/{fid}/stage",
                        json={"stage": "KEEP_WARM", "actor": "piyush", "reason": "too early",
                              "months": 6})
        client.post(f"/founders/{fid}/notes", json={"text": f"note {i}", "actor": "piyush"})
        client.patch(f"/founders/{fid}/workflow",
                     json={"actor": "piyush", "reason": "assign", "owner": "dana",
                           "next_action": "email"})
    return ids


def test_A_rescore_unchanged_config(client, session, with_human_activity):
    before_human = human_snapshot(session)
    before_machine = machine_snapshot(session)

    r = client.post("/rescore", json={"actor": "piyush", "reason": "no config change"})
    assert r.status_code == 200, r.text
    session.expire_all()

    after_human = human_snapshot(session)
    after_machine = machine_snapshot(session)

    assert after_human == before_human                       # HARD GATE
    for fid, after in after_machine.items():
        before = before_machine[fid]
        assert after["assessment_version"] == before["assessment_version"] + 1
        assert after["assessed_at"] >= before["assessed_at"]
        assert after["rubric_version"] == before["rubric_version"]   # config unchanged
        assert after["assessment"] == before["assessment"]           # semantics unchanged


def test_B_config_change_then_rescore(client, session, with_human_activity):
    before_human = human_snapshot(session)
    before_machine = machine_snapshot(session)
    before_hash = client.get("/config").json()["rubric_version"]

    put = client.put("/config", json={"actor": "piyush", "config": {
        "weights": {"thresholds": {"priority_broad": 45}}}})
    assert put.status_code == 200, put.text
    assert put.json()["rescored"] is False
    new_hash = put.json()["rubric_version"]
    assert new_hash != before_hash

    # PUT alone changed no founder.
    session.expire_all()
    assert machine_snapshot(session) == before_machine
    assert human_snapshot(session) == before_human

    r = client.post("/rescore", json={"actor": "piyush", "reason": "threshold change"})
    assert r.status_code == 200, r.text
    session.expire_all()

    after_machine = machine_snapshot(session)
    assert human_snapshot(session) == before_human            # HARD GATE
    assert all(a["rubric_version"] == new_hash for a in after_machine.values())
    assert any(a["assessment"] != before_machine[fid]["assessment"]
               for fid, a in after_machine.items()), "lowering priority_broad must move someone"
    assert all(a["assessment_version"] == before_machine[fid]["assessment_version"] + 1
               for fid, a in after_machine.items())


def test_tier_list_change_reaches_normalization(client, session, seeded):
    """A tier-list edit is a NORMALIZATION change, not merely a scoring one. This
    is why rescore re-runs from stored raw instead of the canonical snapshot."""
    before = {f.id: f.canonical_json for f in session.execute(select(Founder)).scalars()}
    companies = [role.get("company") for cj in before.values()
                 for role in cj["roles"] if role.get("company")]
    assert companies, "fixture needs at least one named employer"

    client.put("/config", json={"config": {"health": {"tier_1": [companies[0]]}}})
    client.post("/rescore", json={})
    session.expire_all()
    after = {f.id: f.canonical_json for f in session.execute(select(Founder)).scalars()}
    assert after != before


def test_rescore_writes_audit_and_no_decision(client, session, with_human_activity):
    fid = with_human_activity[0]
    client.post("/rescore", json={"actor": "piyush", "reason": "weekly"})
    events = client.get(f"/audit/{fid}").json()["events"]
    rescores = [e for e in events if e["event"] == "RESCORE"]
    assert len(rescores) == 1
    assert rescores[0]["field"] == "assessment"
    assert rescores[0]["reason"] == "weekly"
    # no new decision event was manufactured
    assert len(client.get(f"/founders/{fid}").json()["decision_history"]) == 1


def test_failed_rescore_mutates_nothing(client, session, with_human_activity, monkeypatch):
    """A mid-rescore failure must leave BOTH machine and human state untouched:
    the whole rescore is one transaction."""
    before_human = human_snapshot(session)
    before_machine = machine_snapshot(session)

    import app.services.pipeline as pipeline
    real = pipeline.evaluate_corpus
    calls = {"n": 0}

    def boom(*a, **kw):
        calls["n"] += 1
        raise RuntimeError("assessment engine exploded")

    monkeypatch.setattr(pipeline, "evaluate_corpus", boom)
    with pytest.raises(RuntimeError):
        client.post("/rescore", json={})
    monkeypatch.setattr(pipeline, "evaluate_corpus", real)

    session.expire_all()
    assert calls["n"] == 1
    assert human_snapshot(session) == before_human
    assert machine_snapshot(session) == before_machine        # no version bump


def test_every_successful_rescore_audits_every_founder(client, session, seeded):
    """CP7 carry-forward item 5, made explicit: a system RESCORE event per
    founder per successful rescore — no founder silently re-derived."""
    from app.db.models import AuditLog
    ids = seeded["founder_ids"]

    for round_number in (1, 2):
        client.post("/rescore", json={"actor": "system", "reason": f"round {round_number}"})
        session.expire_all()
        rows = session.execute(select(AuditLog).where(AuditLog.event == "RESCORE")).scalars()
        per_founder = {}
        for row in rows:
            per_founder[row.founder_id] = per_founder.get(row.founder_id, 0) + 1
        assert set(per_founder) == set(ids)
        assert set(per_founder.values()) == {round_number}

    events = client.get(f"/audit/{ids[0]}").json()["events"]
    rescores = [e for e in events if e["event"] == "RESCORE"]
    assert [e["actor"] for e in rescores] == ["system", "system"]
    assert all(e["field"] == "assessment" for e in rescores)
    # A RESCORE event never claims a workflow or decision change.
    assert not [e for e in events if e["event"] == "RESCORE"
                and e["field"] in ("stage", "decision", "owner", "notes")]


def test_failed_rescore_writes_no_audit(client, session, seeded, monkeypatch):
    import app.services.pipeline as pipeline
    monkeypatch.setattr(pipeline, "evaluate_corpus",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    try:
        client.post("/rescore", json={})
    except RuntimeError:
        pass
    session.expire_all()
    from app.db.models import AuditLog
    assert session.execute(select(AuditLog)).scalars().all() == []
