"""Normalizer run against the real sample and the synthetic population."""

from pathlib import Path

import pytest

from app.models.canonical import FlagCode, FounderTitleFlag, Ternary
from app.models.raw import load_profiles
from app.normalize import normalize, normalize_corpus

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "data" / "raw" / "sample.json"
LOAD = ROOT / "data" / "synthetic" / "load_800.json"


@pytest.fixture(scope="module")
def sample():
    return [normalize(p) for p in load_profiles(str(SAMPLE))]


def test_sample_pm_record(sample):
    """Gate: PM shows Product roles across mixed industries."""
    pm = sample[0]
    assert [r.department for r in pm.roles] == ["Product", "Product"]
    assert pm.totals.distinct_industries == 2
    assert pm.roles[0].health_flag is Ternary.YES        # Hospital & Health Care
    assert pm.roles[1].health_flag is Ternary.NO         # Computer Software
    assert pm.totals.explicit_founder_roles == 0
    assert pm.contradictions == []


def test_sample_rn_record(sample):
    """Gate: RN -> Clinical Ops Lead shows two health roles and no founder flag."""
    rn = sample[1]
    assert len(rn.roles) == 2
    assert all(r.health_flag is Ternary.YES for r in rn.roles)
    assert rn.totals.health_months == 132
    assert rn.totals.explicit_founder_roles == 0
    assert all(r.founder_title_flag is FounderTitleFlag.NONE for r in rn.roles)


def test_sample_rn_total_mismatch_is_detected(sample):
    """The provided dataset itself contains a contradiction: the RN record states
    112 months of experience against 132 months of roles."""
    flag = next(f for f in sample[1].contradictions if f.code == FlagCode.TOTAL_MISMATCH)
    assert flag.value == -20


@pytest.mark.skipif(not LOAD.exists(), reason="run `make data` first")
def test_load_population_normalizes_without_error():
    canon = normalize_corpus(load_profiles(str(LOAD)))
    assert len(canon) == 800
    for c in canon:
        for f in c._all_flags():
            assert f.source_fields, f"{c.person_id}: {f.code} lacks provenance"


@pytest.mark.skipif(not LOAD.exists(), reason="run `make data` first")
def test_injected_messiness_is_actually_detected():
    """Cross-check the detectors against the generator's own labels. This is the
    only place the two are compared; the generator does not see the normalizer."""
    raws = load_profiles(str(LOAD))
    canon = normalize_corpus(raws)
    by_id = {c.person_id: c for c in canon}

    # tag -> the flag codes that legitimately express it. AMBIGUOUS_CURRENT has
    # two branches (an outright contradiction, or a current-ness we inferred);
    # MISSING_DATES likewise (unusable, or year-only and inferred).
    pairs = [("NO_EXPERIENCE_HISTORY", {FlagCode.NO_EXPERIENCE_HISTORY}),
             ("NO_EDUCATION", {FlagCode.NO_EDUCATION}),
             ("OVERLAPPING_ROLES", {FlagCode.OVERLAP}),
             ("MISSING_COMPANY_METADATA", {FlagCode.MISSING_COMPANY_METADATA}),
             ("MISSING_MANAGEMENT_LEVEL", {FlagCode.MISSING_MANAGEMENT_LEVEL}),
             ("MISSING_DATES", {FlagCode.MISSING_DATES, FlagCode.INFERRED_DATE}),
             ("AMBIGUOUS_CURRENT", {FlagCode.AMBIGUOUS_CURRENT, FlagCode.INFERRED_CURRENT})]
    for tag, codes in pairs:
        tagged = [r for r in raws if tag in (r.synthetic.messiness if r.synthetic else [])]
        assert tagged, f"no records tagged {tag}"
        hits = sum(1 for r in tagged if by_id[r.mdm_person_id].flag_codes() & codes)
        assert hits == len(tagged), f"{tag}: detector fired on {hits}/{len(tagged)}"


@pytest.mark.skipif(not LOAD.exists(), reason="run `make data` first")
def test_detectors_do_not_fire_on_untagged_records():
    """The inverse check, and the more important one: a contradiction invented
    where the generator injected none is a contradiction charged to a founder for
    free. Confidence pays for every flag, so false positives are not harmless."""
    raws = load_profiles(str(LOAD))
    by_id = {c.person_id: c for c in normalize_corpus(raws)}
    pairs = [("OVERLAPPING_ROLES", {FlagCode.OVERLAP}),
             ("OUT_OF_ORDER", {FlagCode.REORDERED}),
             ("TOTAL_MISMATCH", {FlagCode.TOTAL_MISMATCH}),
             ("AMBIGUOUS_CURRENT", {FlagCode.AMBIGUOUS_CURRENT, FlagCode.INFERRED_CURRENT}),
             ("MISSING_COMPANY_METADATA", {FlagCode.MISSING_COMPANY_METADATA}),
             ("NO_EXPERIENCE_HISTORY", {FlagCode.NO_EXPERIENCE_HISTORY})]
    for tag, codes in pairs:
        untagged = [r for r in raws
                    if tag not in (r.synthetic.messiness if r.synthetic else [])]
        fired = [r.mdm_person_id for r in untagged
                 if by_id[r.mdm_person_id].flag_codes() & codes]
        assert not fired, f"{tag}: fired on {len(fired)} untagged records, e.g. {fired[:3]}"


@pytest.mark.skipif(not LOAD.exists(), reason="run `make data` first")
def test_no_duplicate_pair_is_ever_merged():
    canon = normalize_corpus(load_profiles(str(LOAD)))
    linked = [c for c in canon if c.duplicates]
    assert linked, "the load population is supposed to contain duplicate pairs"
    for c in linked:
        assert all(link.merged is False for link in c.duplicates)


@pytest.mark.skipif(not LOAD.exists(), reason="run `make data` first")
def test_generator_duplicate_kinds_map_to_expected_relations():
    from app.models.canonical import DuplicateRelation

    raws = load_profiles(str(LOAD))
    canon = {c.person_id: c for c in normalize_corpus(raws)}
    expected = {"matching_one": DuplicateRelation.PROBABLE,
                "matching_multi": DuplicateRelation.HIGH_CONFIDENCE,
                "conflicting": DuplicateRelation.NEVER}
    checked = 0
    for r in raws:
        kind = (r.synthetic.model_extra or {}).get("duplicate_kind") if r.synthetic else None
        if not kind:
            continue
        base = (r.synthetic.model_extra or {}).get("duplicate_of")
        link = next(l for l in canon[r.mdm_person_id].duplicates
                    if l.other_person_id == base)
        assert link.relation is expected[kind], f"{kind} -> {link.relation}"
        checked += 1
    assert checked == 40
