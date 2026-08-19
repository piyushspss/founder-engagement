"""CP6 regression freeze — RUNBOOK CP7 §13.

Persistence must not have altered the frozen default model. These assertions are
about the DEFAULT config only; the runtime/effective config machinery must be
invisible to them."""

from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "data" / "golden" / "cases.yaml"
PROFILES = ROOT / "data" / "golden" / "profiles.json"

FROZEN = {
    CASES: "6e128c9d1cdebfa77d7273cdced5df48305b5836460c4824aae8ae906232d8cf",
    PROFILES: "8de59bea693eb00eceea6d4cc894f685089808bc5be8f94b1ce4127cce7d3c96",
}


def test_golden_artefacts_are_unchanged():
    for path, digest in FROZEN.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, path.name


def test_default_config_still_drives_the_frozen_model():
    """A founder assessed through the persistence layer under the default
    effective config must equal the same founder assessed directly."""
    import json

    from app.assessment import assess
    from app.models.raw import RawProfile
    from app.normalize import load_config, normalize_corpus

    cfg = load_config()
    entries = json.loads(PROFILES.read_text())[:10]
    raws = [RawProfile.model_validate(e["profile"]) for e in entries]
    direct = [assess(p, cfg) for p in normalize_corpus(raws, cfg)]

    from app.normalize.config import Config, default_sections
    runtime = Config.from_sections(default_sections())
    through_runtime = [assess(p, runtime) for p in normalize_corpus(raws, runtime)]

    assert [a.to_dict() for a in direct] == [a.to_dict() for a in through_runtime]
