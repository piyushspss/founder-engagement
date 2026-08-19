"""Checkpoint 1 gate: the raw schema models must load real and synthetic data
with zero validation errors and must not silently drop fields."""

import json
import sys
from pathlib import Path

import pytest

from app.models.raw import RawProfile, load_profiles

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "data" / "raw" / "sample.json"
LOAD = ROOT / "data" / "synthetic" / "load_800.json"


def test_sample_loads_without_errors():
    profiles = load_profiles(str(SAMPLE))
    assert len(profiles) == 2
    assert all(p.mdm_person_id for p in profiles)


def test_sample_is_not_tagged_synthetic():
    for p in load_profiles(str(SAMPLE)):
        assert p.synthetic is None
        assert p.is_synthetic is False


@pytest.mark.skipif(not LOAD.exists(), reason="run `make data` first")
def test_load_population_loads_without_errors():
    profiles = load_profiles(str(LOAD))
    assert len(profiles) == 800
    assert all(p.is_synthetic for p in profiles), "every generated record must be tagged"
    assert all(p.synthetic.source == "load" for p in profiles)


def test_no_unknown_fields_are_absorbed_into_extra():
    """extra='allow' is a safety net, not a hiding place: the declared models
    should already cover every key present in the sample."""
    for p in load_profiles(str(SAMPLE)):
        assert not p.model_extra
        for e in p.experience or []:
            assert not e.model_extra
        for ed in p.education or []:
            assert not ed.model_extra


def test_all_fields_are_optional():
    """A completely empty profile must parse: absence is never an import error."""
    p = RawProfile.model_validate({})
    assert p.mdm_person_id is None
    assert p.experience is None


def test_roundtrip_preserves_keys():
    raw = json.load(open(SAMPLE))[0]
    assert set(RawProfile.model_validate(raw).raw_dict()) == set(raw)


@pytest.mark.skipif(not LOAD.exists(), reason="run `make data` first")
def test_synthetic_messiness_tags_are_truthful():
    """`_synthetic.messiness` must describe the record it sits on, otherwise the
    demo population misrepresents itself."""
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from gen_load_population import check_tags_are_truthful

    check_tags_are_truthful(json.load(open(LOAD)))


@pytest.mark.skipif(not LOAD.exists(), reason="run `make data` first")
def test_generator_is_deterministic():
    """Same seed -> same population. The demo and any distribution numbers in the
    write-up must be reproducible."""
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".json") as tmp:
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "gen_load_population.py"),
             "--n", "60", "--seed", "1234", "--out", tmp.name],
            check=True, capture_output=True,
        )
        first = json.load(open(tmp.name))
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "gen_load_population.py"),
             "--n", "60", "--seed", "1234", "--out", tmp.name],
            check=True, capture_output=True,
        )
        assert json.load(open(tmp.name)) == first
