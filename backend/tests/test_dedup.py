"""Conservative dedup — PLAN A6b.

The invariant that matters most: nothing is ever merged. A wrongly merged pair
destroys evidence, which is the failure this system exists to prevent.
"""

from app.models.canonical import DuplicateRelation, FlagCode
from app.models.raw import RawProfile
from app.normalize import normalize_corpus
from app.normalize.dedup import classify_pair, duplicate_flags, find_duplicates

SAME, HIGH, PROB, NEVER = (DuplicateRelation.SAME, DuplicateRelation.HIGH_CONFIDENCE,
                           DuplicateRelation.PROBABLE, DuplicateRelation.NEVER)


def p(pid, **kw) -> RawProfile:
    base = {"mdm_person_id": pid, "name_hash": None, "email_hash": None,
            "linkedin_hash": None, "public_profile_id_hash": None,
            "professional_emails_hashed": [], "experience": [], "education": []}
    base.update(kw)
    return RawProfile.model_validate(base)


def test_same_person_id_is_same():
    a, b = p("x", linkedin_hash="L1"), p("x", linkedin_hash="L2")
    assert classify_pair(a, b)[0] is SAME


def test_one_matching_strong_hash_is_probable():
    a = p("a", linkedin_hash="L", email_hash="E1")
    b = p("b", linkedin_hash="L", email_hash="E2")
    relation, matching, conflicting = classify_pair(a, b)
    assert relation is PROB
    assert matching == ["linkedin_hash"] and conflicting == ["email_hash"]


def test_two_matching_strong_hashes_is_high_confidence():
    a = p("a", linkedin_hash="L", email_hash="E")
    b = p("b", linkedin_hash="L", email_hash="E")
    assert classify_pair(a, b)[0] is HIGH


def test_weak_match_with_conflicting_strong_hashes_is_never():
    """Same name, different LinkedIn AND different email: two different people
    with the same name, or one person with irreconcilable records. Either way,
    never assert a duplicate and never merge."""
    a = p("a", name_hash="N", linkedin_hash="L1", email_hash="E1")
    b = p("b", name_hash="N", linkedin_hash="L2", email_hash="E2")
    relation, matching, conflicting = classify_pair(a, b)
    assert relation is NEVER
    assert set(conflicting) == {"linkedin_hash", "email_hash"}


def test_shared_professional_email_is_weak_not_strong():
    a = p("a", professional_emails_hashed=["pe"], linkedin_hash="L1")
    b = p("b", professional_emails_hashed=["pe"], linkedin_hash="L2")
    assert classify_pair(a, b)[0] is NEVER


def test_unrelated_profiles_have_no_link():
    a = p("a", linkedin_hash="L1", email_hash="E1")
    b = p("b", linkedin_hash="L2", email_hash="E2")
    assert classify_pair(a, b)[0] is None


def test_null_hashes_never_match():
    """Two profiles that are both missing the same hash are not thereby similar."""
    a, b = p("a", linkedin_hash=None, email_hash=None), p("b", linkedin_hash=None)
    assert classify_pair(a, b)[0] is None


def test_nothing_is_ever_merged():
    profiles = [p("a", linkedin_hash="L", email_hash="E", public_profile_id_hash="P"),
                p("b", linkedin_hash="L", email_hash="E", public_profile_id_hash="P")]
    links = find_duplicates(profiles)
    assert links["a"][0].relation is HIGH
    for person_links in links.values():
        for link in person_links:
            assert link.merged is False


def test_links_are_symmetric():
    profiles = [p("a", linkedin_hash="L"), p("b", linkedin_hash="L")]
    links = find_duplicates(profiles)
    assert links["a"][0].other_person_id == "b"
    assert links["b"][0].other_person_id == "a"


def test_probable_duplicate_produces_a_quality_flag_not_a_contradiction():
    profiles = [p("a", linkedin_hash="L"), p("b", linkedin_hash="L")]
    canon = normalize_corpus(profiles)
    quality = {f.code for f in canon[0].quality_flags}
    assert FlagCode.POSSIBLE_DUPLICATE in quality
    assert FlagCode.CONFLICTING_IDENTITY_HASHES not in canon[0].flag_codes()


def test_conflicting_identity_produces_a_contradiction():
    profiles = [p("a", name_hash="N", linkedin_hash="L1", email_hash="E1"),
                p("b", name_hash="N", linkedin_hash="L2", email_hash="E2")]
    canon = normalize_corpus(profiles)
    assert FlagCode.CONFLICTING_IDENTITY_HASHES in {f.code for f in canon[0].contradictions}
    assert FlagCode.POSSIBLE_DUPLICATE not in canon[0].flag_codes()


def test_both_members_of_a_probable_pair_remain_independently_assessable():
    """A6b: flag, do not merge. Both records keep their own roles."""
    a = p("a", linkedin_hash="L", experience=[{"position_title": "Founder & CEO",
                                               "date_from_year": 2020}])
    b = p("b", linkedin_hash="L", experience=[])
    canon = {c.person_id: c for c in normalize_corpus([a, b])}
    assert canon["a"].totals.explicit_founder_roles == 1
    assert canon["b"].roles == []
    assert canon["a"].duplicates[0].relation is PROB


def test_duplicate_flags_name_the_matching_hashes():

    links = find_duplicates([p("a", linkedin_hash="L"), p("b", linkedin_hash="L")])
    flags = duplicate_flags(links["a"])
    assert "linkedin_hash" in flags[0].detail
    assert flags[0].source_fields == ("linkedin_hash",)
