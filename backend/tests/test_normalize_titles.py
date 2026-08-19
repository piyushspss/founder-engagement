"""PLAN A8 — founder evidence comes from EXPLICIT titles only.

These are the tests that stop the system inferring 'founder' from seniority.
"""

import pytest

from app.models.canonical import FounderTitleFlag
from app.normalize.config import load_config
from app.normalize.titles import classify_title, headline_suggests_founder

CFG = load_config()
E, P, N = FounderTitleFlag.EXPLICIT, FounderTitleFlag.POSSIBLE, FounderTitleFlag.NONE


@pytest.mark.parametrize("title", [
    "Founder", "Co-Founder", "Cofounder", "Co Founder", "Founder & CEO",
    "Co-Founder & CTO", "Founding CEO", "Founding CTO", "Founding Engineer",
    "Founder and Chief Executive Officer",
])
def test_explicit_founder_titles(title):
    assert classify_title(title, CFG)[0] is E


@pytest.mark.parametrize("title", [
    "Chief Executive Officer", "CEO", "President", "Managing Director",
    "Owner", "Partner", "Chief Medical Officer", "VP of Engineering",
    "Senior Product Manager", "Registered Nurse",
])
def test_leadership_and_ic_titles_are_never_founder_evidence(title):
    assert classify_title(title, CFG)[0] is N


@pytest.mark.parametrize("title,leadership", [
    ("Chief Executive Officer", True), ("CEO", True), ("President", True),
    ("Managing Director", True), ("Owner", True), ("Partner", True),
    ("Senior Product Manager", False), ("Registered Nurse", False),
])
def test_leadership_titles_are_recognised_as_leadership(title, leadership):
    assert classify_title(title, CFG)[1] is leadership


@pytest.mark.parametrize("title", ["Founding Member", "Founding Team Member",
                                   "Founding Advisor", "Founding Employee"])
def test_ambiguous_founding_phrases_are_possible_not_explicit(title):
    """'Founding Member' of anything is suspected, not confirmed, company
    founding — A8 requires POSSIBLE, and POSSIBLE is never scored."""
    assert classify_title(title, CFG)[0] is P


def test_founder_ceo_is_both_founder_and_leadership():
    flag, leadership = classify_title("Founder & CEO", CFG)
    assert flag is E and leadership is True


def test_empty_title():
    assert classify_title(None, CFG) == (N, False)
    assert classify_title("", CFG) == (N, False)


@pytest.mark.parametrize("headline,expected", [
    ("Founder & CEO, Digital Health", True),
    ("Co-Founder | Health Tech", True),
    ("Chief Executive Officer", False),
    ("Product Manager, Health Technology", False),
    (None, False),
])
def test_headline_founder_detection(headline, expected):
    assert headline_suggests_founder(headline) is expected
