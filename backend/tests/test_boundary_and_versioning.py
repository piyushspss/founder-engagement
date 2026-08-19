"""The machine/human boundary, and the version metadata that makes an assessment
attributable to a rubric.

These are the tests that would fail if someone "helpfully" wired
`recommended_action` to a stage move."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from sqlalchemy import inspect, select

from app.assessment.model import Assessment
from app.db.models import Decision, Founder, Workflow
from app.normalize.config import default_sections, rubric_hash

ROOT = Path(__file__).resolve().parents[2]


# ------------------------------------------------------------------ boundary
def test_assessment_model_has_no_decision_or_stage():
    fields = set(Assessment.model_fields)
    assert "decision" not in fields and "stage" not in fields
    blob = json.dumps(Assessment.model_json_schema())
    assert '"decision"' not in blob and '"stage"' not in blob


def test_assessment_json_never_contains_human_fields(client, seeded):
    for fid in seeded["founder_ids"]:
        a = client.get(f"/founders/{fid}").json()["assessment"]
        blob = json.dumps(a)
        assert '"decision"' not in blob and '"stage"' not in blob
        assert '"owner"' not in blob and '"keep_warm_until"' not in blob


def test_founders_table_holds_no_human_columns():
    cols = {c.key for c in inspect(Founder).columns}
    assert not cols & {"stage", "decision", "disposition", "owner", "next_action",
                       "keep_warm_until", "notes"}


def test_import_creates_no_decision(client, session, seeded):
    assert session.execute(select(Decision)).scalars().all() == []
    assert all(w.stage == "NEW" for w in session.execute(select(Workflow)).scalars())


def test_config_update_creates_no_decision_and_no_stage_move(client, session, seeded):
    client.put("/config", json={"config": {"weights": {"thresholds": {"routine_broad": 35}}}})
    session.expire_all()
    assert session.execute(select(Decision)).scalars().all() == []
    assert all(w.stage == "NEW" for w in session.execute(select(Workflow)).scalars())


def test_rescore_cannot_mutate_an_existing_stage(client, session, seeded):
    fid = seeded["founder_ids"][0]
    client.post(f"/founders/{fid}/stage",
                json={"stage": "ASSESSMENT", "actor": "piyush", "reason": "triage"})
    client.post("/rescore", json={})
    session.expire_all()
    wf = session.get(Workflow, fid)
    assert wf.stage == "ASSESSMENT"


def test_import_of_existing_founder_cannot_mutate_stage(client, session, seeded,
                                                        sample_profiles):
    fid = seeded["founder_ids"][0]
    client.post(f"/founders/{fid}/stage",
                json={"stage": "ASSESSMENT", "actor": "piyush", "reason": "triage"})
    client.post("/import", json={"profiles": sample_profiles})
    session.expire_all()
    assert session.get(Workflow, fid).stage == "ASSESSMENT"


def test_neutral_new_is_a_creation_default_not_a_recommendation(client, seeded):
    """Every founder starts NEW regardless of what the machine concluded."""
    rows = client.get("/queue", params={"limit": 1000}).json()["rows"]
    assert {r["stage"] for r in rows} == {"NEW"}
    assert len({r["attention"] for r in rows}) > 1
    assert all(r["current_decision"] is None for r in rows)


def test_no_endpoint_accepts_machine_authored_decision(client, seeded):
    """`recommended_action` is not a permission slip. There is no route that
    turns a machine dimension into a disposition or a stage."""
    fid = seeded["founder_ids"][0]
    assert client.post(f"/founders/{fid}/decision",
                       json={"disposition": "POTENTIAL", "actor": "machine",
                             "reason": "auto", "source": "assessment"}).status_code == 422
    assert client.post("/rescore",
                       json={"actor": "x", "reason": "y",
                             "stage": "DEAL"}).status_code == 422
    assert client.post("/import",
                       json={"profiles": [], "stage": "DEAL"}).status_code == 422


def test_only_human_endpoints_write_human_tables():
    """Static guarantee: no machine module imports the human mutation helpers."""
    for module in ("services/pipeline.py", "services/assessment_service.py",
                   "services/config_service.py"):
        text = (ROOT / "backend" / "app" / module).read_text()
        assert "record_decision" not in text
        assert "change_stage" not in text
        assert "Decision(" not in text


# ---------------------------------------------------------------- versioning
def test_rubric_hash_is_stable_across_processes():
    code = ("import sys; sys.path.insert(0, %r);"
            "from app.normalize.config import load_config;"
            "print(load_config().version_hash())" % str(ROOT / "backend"))
    runs = {subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                           check=True).stdout.strip() for _ in range(2)}
    assert len(runs) == 1
    assert runs.pop() == rubric_hash(default_sections())


def test_rubric_hash_ignores_key_ordering():
    sections = default_sections()
    reordered = json.loads(json.dumps(sections))
    reordered["weights"] = dict(reversed(list(reordered["weights"].items())))
    reordered["weights"]["thresholds"] = dict(
        reversed(list(reordered["weights"]["thresholds"].items())))
    assert rubric_hash(reordered) == rubric_hash(sections)


def test_relevant_config_change_changes_hash():
    base = rubric_hash(default_sections())
    for patch in (
        lambda s: s["weights"]["thresholds"].__setitem__("priority_broad", 64),
        lambda s: s["weights"]["signal_weights"].__setitem__("leadership", 16),
        lambda s: s["institutions"]["tier_1"].append("Some New University"),
        lambda s: s["health"]["health_industries"].append("Veterinary"),
        lambda s: s["archetypes"]["primary_precedence"].append("Clinical Expert"),
    ):
        sections = default_sections()
        patch(sections)
        assert rubric_hash(sections) != base


def test_unrelated_timestamps_do_not_enter_the_hash(client, session):
    """The hash covers the four rubric sections and nothing else — not the row's
    updated_at, not who changed it, not when."""
    from app.db.models import RuntimeConfig, utcnow
    from app.services.config_service import get_runtime_row
    row = get_runtime_row(session)
    before = row.rubric_version
    row.updated_at = utcnow()
    row.updated_by = "someone else"
    session.commit()
    assert rubric_hash(row.sections_json) == before
    assert client.get("/config").json()["rubric_version"] == before


def test_hash_is_sha256_hex():
    h = rubric_hash(default_sections())
    assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)


def test_assessment_version_starts_at_one_and_increments(client, session, sample_profiles):
    client.post("/import", json={"profiles": sample_profiles[:3]})
    session.expire_all()
    assert {f.assessment_version for f in session.execute(select(Founder)).scalars()} == {1}

    client.post("/import", json={"profiles": sample_profiles[:3]})
    session.expire_all()
    assert {f.assessment_version for f in session.execute(select(Founder)).scalars()} == {2}

    client.post("/rescore", json={})
    session.expire_all()
    assert {f.assessment_version for f in session.execute(select(Founder)).scalars()} == {3}


def test_failed_reassessment_does_not_increment(client, session, seeded, monkeypatch):
    before = {f.id: (f.assessment_version, f.assessed_at)
              for f in session.execute(select(Founder)).scalars()}
    import app.services.pipeline as pipeline
    monkeypatch.setattr(pipeline, "evaluate_corpus",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    try:
        client.post("/rescore", json={})
    except RuntimeError:
        pass
    session.expire_all()
    after = {f.id: (f.assessment_version, f.assessed_at)
             for f in session.execute(select(Founder)).scalars()}
    assert after == before


def test_assessed_at_updates_only_on_successful_assessment(client, session, seeded):
    fid = seeded["founder_ids"][0]
    before = session.get(Founder, fid).assessed_at
    client.post(f"/founders/{fid}/decision",
                json={"disposition": "POTENTIAL", "actor": "p", "reason": "r"})
    client.post(f"/founders/{fid}/notes", json={"text": "n", "actor": "p"})
    client.put("/config", json={"config": {"weights": {"thresholds": {"routine_broad": 38}}}})
    session.expire_all()
    assert session.get(Founder, fid).assessed_at == before      # no assessment happened

    client.post("/rescore", json={})
    session.expire_all()
    assert session.get(Founder, fid).assessed_at >= before
    assert session.get(Founder, fid).assessment_version == 2
