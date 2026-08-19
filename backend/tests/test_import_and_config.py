"""Re-import over live human activity, queue filters, and the config contract."""

from __future__ import annotations

from sqlalchemy import inspect, select

from app.db.models import Decision, Founder, Workflow


def _rows(session, model):
    cols = [c.key for c in inspect(model).columns]
    key = (lambda r: r.id) if hasattr(model, "id") else (lambda r: r.founder_id)
    return [{c: getattr(r, c) for c in cols}
            for r in sorted(session.execute(select(model)).scalars().all(), key=key)]


# ------------------------------------------------- re-import after human work
def test_reimport_after_human_activity_preserves_workflow_byte_identically(
        client, session, seeded, sample_profiles):
    fid = seeded["founder_ids"][0]
    client.post(f"/founders/{fid}/decision",
                json={"disposition": "POTENTIAL", "actor": "piyush", "reason": "strong"})
    for stage, extra in (("ASSESSMENT", {}), ("POTENTIAL", {}), ("NURTURING", {}),
                         ("KEEP_WARM", {"months": 9})):
        assert client.post(f"/founders/{fid}/stage",
                           json={"stage": stage, "actor": "piyush", "reason": "move",
                                 **extra}).status_code == 200
    client.patch(f"/founders/{fid}/workflow",
                 json={"actor": "piyush", "reason": "assign", "owner": "dana",
                       "next_action": "schedule call"})
    client.post(f"/founders/{fid}/notes", json={"text": "met at conference",
                                                "actor": "piyush"})

    before_workflow = _rows(session, Workflow)
    before_decisions = _rows(session, Decision)
    before_version = session.get(Founder, fid).assessment_version

    r = client.post("/import", json={"profiles": sample_profiles, "source": "refresh"})
    assert r.status_code == 200
    assert r.json()["updated"] == len(sample_profiles)
    session.expire_all()

    assert _rows(session, Workflow) == before_workflow      # HARD GATE
    assert _rows(session, Decision) == before_decisions
    founder = session.get(Founder, fid)
    assert founder.assessment_version == before_version + 1  # machine refreshed
    assert founder.source == "refresh"


def test_reimport_does_not_manufacture_a_decision(client, session, sample_profiles):
    client.post("/import", json={"profiles": sample_profiles})
    client.post("/import", json={"profiles": sample_profiles})
    assert session.execute(select(Decision)).scalars().all() == []


def test_import_never_auto_merges(client, sample_profiles, raw_population):
    r = client.post("/import", json={"profiles": raw_population[:120]})
    body = r.json()
    dup = body["duplicate_report"]
    assert dup["auto_merged"] == 0
    assert body["created"] == 120                        # every record kept its own row
    assert all(link["merged"] is False for link in dup["links"])
    for pair in dup["never_merge_pairs"]:
        assert pair["relation"] == "NEVER" and pair["conflicting_hashes"]


# ------------------------------------------------------------- queue filters
def test_queue_filters(client, seeded):
    fid = seeded["founder_ids"][0]
    client.post(f"/founders/{fid}/stage",
                json={"stage": "ASSESSMENT", "actor": "p", "reason": "r"})
    client.patch(f"/founders/{fid}/workflow",
                 json={"actor": "p", "reason": "r", "owner": "dana"})
    all_rows = client.get("/queue", params={"limit": 1000}).json()["rows"]

    got = client.get("/queue", params={"attention": "PRIORITY_REVIEW", "limit": 1000}).json()
    assert got["total"] == sum(1 for r in all_rows if r["attention"] == "PRIORITY_REVIEW")
    assert all(r["attention"] == "PRIORITY_REVIEW" for r in got["rows"])

    got = client.get("/queue", params={"data_state": "NEEDS_INFORMATION",
                                       "limit": 1000}).json()
    assert all(r["data_state"] == "NEEDS_INFORMATION" for r in got["rows"])

    got = client.get("/queue", params={"stage": "ASSESSMENT"}).json()
    assert [r["founder_id"] for r in got["rows"]] == [fid]

    got = client.get("/queue", params={"owner": "dana"}).json()
    assert [r["founder_id"] for r in got["rows"]] == [fid]

    assert client.get("/queue", params={"due": True}).json()["total"] == 0
    assert client.get("/queue", params={"due": False, "limit": 1000}).json()["total"] == \
        len(all_rows)


def test_queue_due_filter_uses_keep_warm_until(client, seeded):
    fid = seeded["founder_ids"][0]
    for stage, extra in (("ASSESSMENT", {}), ("POTENTIAL", {}), ("NURTURING", {}),
                         ("KEEP_WARM", {"months": 3})):
        client.post(f"/founders/{fid}/stage",
                    json={"stage": stage, "actor": "p", "reason": "r", **extra})
    keep_warm_until = client.get(f"/founders/{fid}").json()["workflow"]["keep_warm_until"]
    assert client.get("/queue", params={"due": True}).json()["total"] == 0
    due = client.get("/queue", params={"due": True, "as_of": keep_warm_until}).json()
    assert [r["founder_id"] for r in due["rows"]] == [fid]
    # CP9: the time-derived obligation lives in workflow_reasons, NOT in the
    # machine why_surfaced list — the model did not change its mind.
    assert "Re-engagement due" in due["rows"][0]["workflow_reasons"]
    assert "Re-engagement due" not in due["rows"][0]["why_surfaced"]


def test_queue_multi_value_filters(client, seeded):
    r = client.get("/queue?attention=PRIORITY_REVIEW&attention=REVIEW&limit=1000").json()
    assert all(x["attention"] in ("PRIORITY_REVIEW", "REVIEW") for x in r["rows"])


# -------------------------------------------------------------------- config
def test_config_roundtrip(client):
    body = client.get("/config").json()
    assert set(body["config"]) == {"weights", "institutions", "health", "archetypes"}
    assert len(body["rubric_version"]) == 64


def test_config_rejects_unknown_and_invalid_fields(client):
    for patch, expect in (
        ({"nonsense": {}}, "unknown config section"),
        ({"weights": {"thresholds": {"made_up": 1}}}, "unknown field"),
        ({"weights": {"thresholds": {"priority_confidence": 5}}}, "outside allowed range"),
        ({"weights": {"thresholds": {"priority_broad": "high"}}}, "expected number"),
        ({"weights": {"signal_weights": {"leadership": -3}}}, "non-negative"),
        ({"institutions": {"tier_1": "Harvard"}}, "expected array"),
    ):
        r = client.put("/config", json={"config": patch})
        assert r.status_code == 422, (patch, r.text)
        assert any(expect in e for e in r.json()["errors"]), (patch, r.json())


def test_config_put_does_not_touch_frozen_files(client):
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    files = [root / "backend" / "config" / "weights.yaml",
             root / "backend" / "config" / "archetypes.yaml",
             root / "backend" / "config" / "tiers" / "institutions.json",
             root / "backend" / "config" / "tiers" / "health_companies.json"]
    before = {f: f.read_bytes() for f in files}
    client.put("/config", json={"config": {"weights": {"thresholds": {"priority_broad": 50}}}})
    assert {f: f.read_bytes() for f in files} == before


def test_config_accepts_tier_list_edit(client):
    r = client.put("/config", json={"config": {
        "institutions": {"tier_1": ["Harvard University", "Some New University"],
                         "aliases": {"SNU": "Some New University"}}}})
    assert r.status_code == 200, r.text
    assert "Some New University" in client.get("/config").json()["config"]["institutions"]["tier_1"]
