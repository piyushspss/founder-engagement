"""Degree-string variance and institution tier matching (A7)."""

import pytest

from app.models.canonical import DegreeType, FlagCode, InstitutionTier
from app.normalize.config import load_config
from app.normalize.education import classify_degree, match_institution

CFG = load_config()


@pytest.mark.parametrize("text,expected", [
    ("Bachelor of Science in Nursing", DegreeType.BSN),
    ("BSN", DegreeType.BSN),
    ("B.S.N., Nursing", DegreeType.BSN),
    ("Bachelor's degree, Nursing", DegreeType.BSN),
    ("Registered Nurse (RN)", DegreeType.RN),
    ("R.N.", DegreeType.RN),
    ("Doctor of Medicine (MD)", DegreeType.MD),
    ("M.D.", DegreeType.MD),
    ("Doctor of Osteopathic Medicine (DO)", DegreeType.DO),
    ("PhD, Bioinformatics", DegreeType.PhD),
    ("Ph.D. Genomics", DegreeType.PhD),
    ("Doctorate, Neuroscience", DegreeType.PhD),
    ("MBA", DegreeType.MBA),
    ("Master of Business Administration", DegreeType.MBA),
    ("Master of Science, Statistics", DegreeType.MS),
    ("MSc Computer Science", DegreeType.MS),
    ("Bachelor's degree, Computer Science", DegreeType.BS),
    ("BSc Economics", DegreeType.BS),
    ("Bachelor of Arts, Economics", DegreeType.BA),
    ("Certificate, Project Management", DegreeType.OTHER),
    (None, DegreeType.OTHER),
])
def test_degree_string_variance(text, expected):
    assert classify_degree(text) is expected


def test_doctoral_beats_masters_when_both_appear():
    assert classify_degree("PhD, Master of Science route") is DegreeType.PhD


@pytest.mark.parametrize("name,canonical,tier", [
    ("Harvard University", "Harvard University", InstitutionTier.TIER_1),
    ("MIT", "Massachusetts Institute of Technology", InstitutionTier.TIER_1),
    ("Wharton", "University of Pennsylvania", InstitutionTier.TIER_1),
    ("Cornell University", "Cornell University", InstitutionTier.TIER_2),
])
def test_exact_and_alias_matches(name, canonical, tier):
    got, got_tier, score, flags = match_institution(name, CFG)
    assert (got, got_tier, score) == (canonical, tier, 100.0)
    assert flags == [], "an exact/alias match is a fact, not an inference"


@pytest.mark.parametrize("variant,canonical", [
    ("M.I.T.", "Massachusetts Institute of Technology"),
    ("Massachusetts Inst. of Technology", "Massachusetts Institute of Technology"),
    ("Harvard Univ.", "Harvard University"),
    ("Carnegie-Mellon University", "Carnegie Mellon University"),
])
def test_fuzzy_variants_resolve_and_are_flagged_as_inference(variant, canonical):
    got, tier, score, flags = match_institution(variant, CFG)
    assert got == canonical and tier is not InstitutionTier.UNKNOWN
    assert [f.code for f in flags] == [FlagCode.FUZZY_INSTITUTION_MATCH]


@pytest.mark.parametrize("name", ["Cobalt Ridge University", "Sable Creek State University",
                                  "Larkspur College", "Some Community College"])
def test_unknown_institution_is_neutral_not_negative(name):
    """A7: an institution that isn't on the tier list is UNKNOWN. The canonical
    profile must not assert anything about it, positive or negative."""
    got, tier, score, flags = match_institution(name, CFG)
    assert got is None
    assert tier is InstitutionTier.UNKNOWN
    assert flags == []


def test_empty_institution():
    assert match_institution(None, CFG) == (None, InstitutionTier.UNKNOWN, None, [])
