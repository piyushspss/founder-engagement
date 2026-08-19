"""Import → queue → detail → dashboard → audit. The transport layer works and
returns what CP8 will need."""

from __future__ import annotations

import io
import json


def test_import_creates_founders_and_reports_duplicates(client, sample_profiles):
    r = client.post("/import", json={"profiles": sample_profiles, "source": "unit",
                                     "funnel": "TEST"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["received"] == len(sample_profiles)
    assert body["created"] == len(sample_profiles)
    assert body["updated"] == 0
    dup = body["duplicate_report"]
    assert dup["auto_merged"] == 0                      # A6b: never merge
    assert "A6b" in dup["policy"]


def test_import_is_idempotent_on_identity(client, sample_profiles):
    client.post("/import", json={"profiles": sample_profiles})
    r = client.post("/import", json={"profiles": sample_profiles})
    body = r.json()
    assert body["created"] == 0
    assert body["updated"] == len(sample_profiles)
    ids = client.get("/founders", params={"limit": 1000}).json()["founder_ids"]
    assert len(ids) == len(sample_profiles)             # no identity duplication


def test_import_csv(client, sample_profiles):
    profile = sample_profiles[0]
    csv_text = (
        "mdm_person_id,headline,total_experience_duration_months,experience,education\n"
        f"\"csv-1\",\"{(profile.get('headline') or 'Founder').replace(chr(34), '')}\",120,"
        f"\"{json.dumps(profile.get('experience') or [], separators=(',', ':')).replace(chr(34), chr(34) * 2)}\","
        f"\"{json.dumps(profile.get('education') or [], separators=(',', ':')).replace(chr(34), chr(34) * 2)}\"\n")
    r = client.post("/import", files={"file": ("people.csv", io.BytesIO(csv_text.encode()),
                                               "text/csv")})
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 1
    detail = client.get("/founders/csv-1")
    assert detail.status_code == 200
    assert detail.json()["assessment"]["person_id"] == "csv-1"


def test_import_rejects_bad_payload(client):
    r = client.post("/import", json={"profiles": [{"experience": "not-a-list"}]})
    assert r.status_code == 422
    assert r.json()["error"] == "invalid_payload"


def test_queue_default_ordering(client, seeded):
    rows = client.get("/queue", params={"limit": 1000}).json()["rows"]
    rank = {"PRIORITY_REVIEW": 0, "REVIEW": 1, "ROUTINE": 2}
    keys = [(rank[r["attention"]], -r["confidence"], r["founder_id"]) for r in rows]
    assert keys == sorted(keys)


def test_queue_never_ranks_unknown_below_low(client, seeded):
    """Ordering must not read `potential` at all — UNKNOWN is a different answer
    from LOW, not a worse one (PLAN §4.5)."""
    rows = client.get("/queue", params={"limit": 1000}).json()["rows"]
    for a, b in zip(rows, rows[1:]):
        if a["attention"] == b["attention"] and a["confidence"] == b["confidence"]:
            assert a["founder_id"] < b["founder_id"]     # id, never potential


def test_founder_detail_sections_are_separated(client, seeded):
    fid = seeded["founder_ids"][0]
    body = client.get(f"/founders/{fid}").json()
    assert set(body) == {"founder_id", "facts", "assessment", "assessment_metadata",
                         "current_decision", "decision_history", "workflow", "duplicates"}
    assert body["current_decision"] is None              # import creates no decision
    assert body["workflow"]["stage"] == "NEW"
    assert "decision" not in body["assessment"]
    assert "stage" not in body["assessment"]
    meta = body["assessment_metadata"]
    assert meta["assessment_version"] == 1
    assert len(meta["rubric_version"]) == 64


def test_dashboard_shape(client, seeded):
    body = client.get("/dashboard").json()
    for key in ("stage_counts", "weekly_intake", "ageing_in_stage", "stuck",
                "re_engagement_due", "review_queue_size", "low_confidence_pct"):
        assert key in body
    assert body["founders"] == len(seeded["founder_ids"])
    assert body["stage_counts"]["NEW"] == body["founders"]
    assert body["human_decisions_recorded"] == 0


def test_audit_empty_after_import(client, seeded):
    fid = seeded["founder_ids"][0]
    assert client.get(f"/audit/{fid}").json()["events"] == []


def test_unknown_founder_404(client):
    assert client.get("/founders/nope").status_code == 404
    assert client.get("/audit/nope").status_code == 404
