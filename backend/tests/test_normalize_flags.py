"""Quality flags, contradictions and inferences produced by the normalizer."""

import pytest

from app.models.canonical import FlagCode, FounderTitleFlag, Ternary
from app.models.raw import RawProfile
from app.normalize import normalize


def profile(**kw) -> RawProfile:
    base = {"mdm_person_id": "p1", "headline": "Test",
            "experience": [], "education": [],
            "total_experience_duration_months": None}
    base.update(kw)
    return RawProfile.model_validate(base)


def role(**kw) -> dict:
    base = {"position_title": "Product Manager", "company_name": "Acme Health",
            "company_industry": "Hospital & Health Care", "management_level": "Manager",
            "company_size_range": "51-200 employees", "company_employees_count": 120,
            "date_from": "01/2020", "date_from_year": 2020, "date_from_month": 1,
            "date_to": "01/2022", "date_to_year": 2022, "date_to_month": 1,
            "duration_months": 24, "is_current": None, "active_experience": None}
    base.update(kw)
    return base


def codes(c):
    return {f.code for f in c._all_flags()}


# ---------------------------------------------------------------- currentness
def test_current_role_from_is_current():
    c = normalize(profile(experience=[role(date_to=None, date_to_year=None,
                                           date_to_month=None, is_current=1)]))
    assert c.roles[0].is_current is Ternary.YES
    assert FlagCode.AMBIGUOUS_CURRENT not in codes(c)


def test_current_inferred_from_active_experience_is_flagged():
    """date_to null + active_experience truthy + is_current null -> current, but
    that is a judgment and must be visible."""
    c = normalize(profile(experience=[role(date_to=None, date_to_year=None,
                                           date_to_month=None, is_current=None,
                                           active_experience=1)]))
    assert c.roles[0].is_current is Ternary.YES
    assert FlagCode.INFERRED_CURRENT in codes(c)


def test_no_end_date_and_no_indicator_is_ambiguous():
    c = normalize(profile(experience=[role(date_to=None, date_to_year=None,
                                           date_to_month=None)]))
    assert c.roles[0].is_current is Ternary.UNKNOWN
    assert FlagCode.AMBIGUOUS_CURRENT in codes(c)


def test_claims_current_but_has_end_date_is_a_contradiction():
    c = normalize(profile(experience=[role(is_current=1)]))
    assert c.roles[0].is_current is Ternary.UNKNOWN
    contradiction = next(f for f in c.contradictions if f.code == FlagCode.AMBIGUOUS_CURRENT)
    assert "end date" in contradiction.detail


def test_past_role_is_not_current():
    c = normalize(profile(experience=[role()]))
    assert c.roles[0].is_current is Ternary.NO


# -------------------------------------------------------------------- ordering
def test_roles_are_reordered_reverse_chronologically_and_flagged():
    older = role(date_from="01/2010", date_from_year=2010, date_to="01/2014",
                 date_to_year=2014, position_title="Old")
    newer = role(date_from="01/2018", date_from_year=2018, date_to="01/2022",
                 date_to_year=2022, position_title="New")
    c = normalize(profile(experience=[older, newer]))
    assert [r.title for r in c.roles] == ["New", "Old"]
    assert FlagCode.REORDERED in codes(c)


def test_already_ordered_profile_is_not_flagged_reordered():
    newer = role(date_from="01/2018", date_from_year=2018, position_title="New")
    older = role(date_from="01/2010", date_from_year=2010, date_to="01/2014",
                 date_to_year=2014, position_title="Old")
    c = normalize(profile(experience=[newer, older]))
    assert FlagCode.REORDERED not in codes(c)


def test_undated_roles_sort_last_not_oldest():
    dated = role(date_from="01/2018", date_from_year=2018, position_title="Dated")
    undated = role(date_from=None, date_from_year=None, date_from_month=None,
                   position_title="Undated")
    c = normalize(profile(experience=[undated, dated]))
    assert [r.title for r in c.roles] == ["Dated", "Undated"]


# --------------------------------------------------------------------- overlap
def test_overlapping_roles_are_detected():
    a = role(date_from="01/2018", date_from_year=2018, date_to="01/2022",
             date_to_year=2022, position_title="A")
    b = role(date_from="01/2020", date_from_year=2020, date_to="01/2023",
             date_to_year=2023, position_title="B")
    c = normalize(profile(experience=[a, b]))
    overlap = next(f for f in c.contradictions if f.code == FlagCode.OVERLAP)
    assert overlap.value == 24


def test_adjacent_roles_do_not_overlap():
    a = role(date_from="01/2018", date_from_year=2018, date_to="01/2020", date_to_year=2020)
    b = role(date_from="01/2020", date_from_year=2020, date_to="01/2022", date_to_year=2022)
    c = normalize(profile(experience=[a, b]))
    assert FlagCode.OVERLAP not in codes(c)


# --------------------------------------------------------------- total mismatch
def test_total_mismatch_is_flagged_with_delta():
    c = normalize(profile(experience=[role(duration_months=24)],
                          total_experience_duration_months=90))
    flag = next(f for f in c.contradictions if f.code == FlagCode.TOTAL_MISMATCH)
    assert flag.value == 66


def test_matching_total_is_not_flagged():
    c = normalize(profile(experience=[role(duration_months=24)],
                          total_experience_duration_months=24))
    assert FlagCode.TOTAL_MISMATCH not in codes(c)


def test_overlapping_roles_do_not_produce_a_false_total_mismatch():
    """With concurrent roles the sum of durations exceeds elapsed time by
    construction. Flagging that as a contradiction would penalise a founder
    twice for one piece of messiness."""
    a = role(date_from="01/2018", date_from_year=2018, date_to="01/2022",
             date_to_year=2022, duration_months=48)
    b = role(date_from="01/2020", date_from_year=2020, date_to="01/2022",
             date_to_year=2022, duration_months=24)
    c = normalize(profile(experience=[a, b], total_experience_duration_months=48))
    assert FlagCode.TOTAL_MISMATCH not in codes(c)
    assert FlagCode.OVERLAP in codes(c)


def test_missing_total_is_a_quality_flag_not_a_contradiction():
    c = normalize(profile(experience=[role()], total_experience_duration_months=None))
    assert FlagCode.MISSING_TOTAL_EXPERIENCE in {f.code for f in c.quality_flags}
    assert FlagCode.TOTAL_MISMATCH not in codes(c)


# --------------------------------------------------------------------- coverage
def test_empty_experience_history_is_flagged():
    c = normalize(profile(experience=[]))
    assert FlagCode.NO_EXPERIENCE_HISTORY in {f.code for f in c.quality_flags}
    assert c.roles == []


def test_missing_industry_is_unknown_not_non_health():
    """The single most important neutrality rule: absence of an industry must
    not be read as 'not healthcare'."""
    c = normalize(profile(experience=[role(company_industry=None,
                                           company_categories_and_keywords=[],
                                           company_name="Northwind Widgets")]))
    assert c.roles[0].health_flag is Ternary.UNKNOWN
    assert FlagCode.UNKNOWN_INDUSTRY in {f.code for f in c.quality_flags}
    assert c.totals.health_months == 0


def test_non_health_industry_is_no_not_unknown():
    c = normalize(profile(experience=[role(company_industry="Computer Software")]))
    assert c.roles[0].health_flag is Ternary.NO


def test_health_keywords_rescue_a_missing_industry():
    c = normalize(profile(experience=[role(
        company_industry=None, company_categories_and_keywords=["digital health"])]))
    assert c.roles[0].health_flag is Ternary.YES


def test_missing_company_size_and_level_are_quality_flags():
    c = normalize(profile(experience=[role(company_size_range=None,
                                           company_employees_count=None,
                                           management_level=None)]))
    q = {f.code for f in c.quality_flags}
    assert FlagCode.MISSING_COMPANY_METADATA in q
    assert FlagCode.MISSING_MANAGEMENT_LEVEL in q


# ------------------------------------------------------------------ A8 founder
def test_explicit_founder_role_counted_in_totals():
    c = normalize(profile(experience=[role(position_title="Co-Founder & CEO"),
                                      role(position_title="Founder & CTO",
                                           date_from="01/2014", date_from_year=2014,
                                           date_to="01/2018", date_to_year=2018)]))
    assert c.totals.explicit_founder_roles == 2


def test_ceo_headline_founder_claim_is_possible_only():
    c = normalize(profile(headline="Founder & CEO, Digital Health",
                          experience=[role(position_title="Chief Executive Officer")]))
    assert c.totals.explicit_founder_roles == 0
    assert c.roles[0].founder_title_flag is FounderTitleFlag.NONE
    assert c.roles[0].leadership_title is True
    assert FlagCode.POSSIBLE_FOUNDER in {f.code for f in c.inferences}


def test_explicit_founder_role_suppresses_the_possible_flag():
    c = normalize(profile(headline="Founder & CEO",
                          experience=[role(position_title="Founder & CEO")]))
    assert FlagCode.POSSIBLE_FOUNDER not in codes(c)


# ------------------------------------------------------------------ provenance
def test_every_flag_carries_source_fields():
    a = role(date_from="01/2018", date_from_year=2018, date_to="01/2022",
             date_to_year=2022, is_current=1)
    b = role(date_from="01/2020", date_from_year=2020, company_industry=None,
             management_level=None)
    c = normalize(profile(experience=[a, b], total_experience_duration_months=999))
    assert c._all_flags()
    for f in c._all_flags():
        assert f.source_fields, f"{f.code} has no provenance"


def test_provenance_maps_canonical_paths_to_raw_paths():
    c = normalize(profile(experience=[role()],
                          education=[{"institution_name": "MIT", "degree": "BS"}]))
    assert c.provenance["roles[0].title"] == ["experience[0].position_title"]
    assert c.provenance["education[0].institution"] == ["education[0].institution_name"]


def test_completely_empty_profile_normalizes():
    c = normalize(RawProfile.model_validate({}))
    assert c.person_id == "unknown"
    assert FlagCode.NO_EXPERIENCE_HISTORY in {f.code for f in c.quality_flags}
    assert FlagCode.NO_EDUCATION in {f.code for f in c.quality_flags}


def test_undated_role_alone_does_not_trigger_reordered():
    """A role we cannot place moves to the end of the canonical ordering. That is
    a gap in the data, not the source contradicting itself — and REORDERED is a
    contradiction that costs confidence."""
    undated = role(date_from=None, date_from_year=None, date_from_month=None,
                   position_title="Undated")
    newer = role(date_from="01/2020", date_from_year=2020, position_title="A")
    older = role(date_from="01/2012", date_from_year=2012, date_to="01/2016",
                 date_to_year=2016, position_title="B")
    c = normalize(profile(experience=[undated, newer, older]))
    assert [r.title for r in c.roles] == ["A", "B", "Undated"]
    assert FlagCode.REORDERED not in codes(c)


def test_dated_roles_out_of_order_still_trigger_reordered_when_undated_present():
    undated = role(date_from=None, date_from_year=None, date_from_month=None,
                   position_title="Undated")
    older = role(date_from="01/2012", date_from_year=2012, date_to="01/2016",
                 date_to_year=2016, position_title="B")
    newer = role(date_from="01/2020", date_from_year=2020, position_title="A")
    c = normalize(profile(experience=[undated, older, newer]))
    assert FlagCode.REORDERED in codes(c)


def test_inferred_month_does_not_manufacture_an_overlap():
    """A year-only date is anchored to mid-year and carries +/-6 months of error.
    A 'gap' or 'overlap' smaller than that is our inference talking, not the
    record — and OVERLAP is a contradiction that costs confidence."""
    a = role(date_from=None, date_from_year=2020, date_from_month=None,
             date_to="01/2024", date_to_year=2024, date_to_month=1)
    b = role(date_from="01/2016", date_from_year=2016, date_from_month=1,
             date_to=None, date_to_year=2020, date_to_month=10)  # ends 10/2020
    c = normalize(profile(experience=[a, b]))
    assert FlagCode.INFERRED_DATE in codes(c)
    assert FlagCode.OVERLAP not in codes(c)


def test_large_overlap_is_still_reported_despite_an_inferred_month():
    a = role(date_from=None, date_from_year=2018, date_from_month=None,
             date_to="01/2024", date_to_year=2024, date_to_month=1)
    b = role(date_from="01/2014", date_from_year=2014, date_from_month=1,
             date_to=None, date_to_year=2022, date_to_month=1)
    c = normalize(profile(experience=[a, b]))
    assert FlagCode.OVERLAP in codes(c)


# ------------------------------------------------------- company size (CP2 cleanup)
def test_size_range_mismatch_is_a_contradiction():
    """The supplied sample itself does this: '51-200 employees' alongside an exact
    count of 1400."""
    c = normalize(profile(experience=[role(company_size_range="51-200 employees",
                                           company_employees_count=1400)]))
    flag = next(f for f in c.contradictions if f.code == FlagCode.SIZE_RANGE_MISMATCH)
    assert flag.value == 1400
    assert set(flag.source_fields) == {"experience[0].company_employees_count",
                                       "experience[0].company_size_range"}


def test_exact_count_is_canonical_and_the_range_is_preserved():
    c = normalize(profile(experience=[role(company_size_range="51-200 employees",
                                           company_employees_count=1400)]))
    r = c.roles[0]
    assert r.company_size == 1400                      # exact count is canonical
    assert r.company_size_range == "51-200 employees"  # band preserved verbatim
    assert (r.company_size_range_min, r.company_size_range_max) == (51, 200)


def test_no_midpoint_or_repair_is_invented():
    """Explicitly forbidden: averaging the two, or silently picking the midpoint."""
    c = normalize(profile(experience=[role(company_size_range="51-200 employees",
                                           company_employees_count=1400)]))
    assert c.roles[0].company_size not in (125, 725, 800)


def test_consistent_count_and_range_produce_no_flag():
    c = normalize(profile(experience=[role(company_size_range="51-200 employees",
                                           company_employees_count=120)]))
    assert FlagCode.SIZE_RANGE_MISMATCH not in codes(c)


def test_open_ended_range_has_no_upper_bound():
    c = normalize(profile(experience=[role(company_size_range="10001+ employees",
                                           company_employees_count=45000)]))
    assert FlagCode.SIZE_RANGE_MISMATCH not in codes(c)
    assert c.roles[0].company_size_range_max is None


def test_count_below_range_is_also_a_mismatch():
    c = normalize(profile(experience=[role(company_size_range="1001-5000 employees",
                                           company_employees_count=40)]))
    assert FlagCode.SIZE_RANGE_MISMATCH in codes(c)


def test_reordered_is_a_quality_flag_not_a_contradiction():
    """Provider array ordering is a formatting artefact the normalizer repairs
    from internally-consistent dates. It must not cost confidence."""
    older = role(date_from="01/2010", date_from_year=2010, date_to="01/2014",
                 date_to_year=2014, position_title="Old")
    newer = role(date_from="01/2018", date_from_year=2018, date_to="01/2022",
                 date_to_year=2022, position_title="New")
    c = normalize(profile(experience=[older, newer]))
    assert FlagCode.REORDERED in {f.code for f in c.quality_flags}
    assert FlagCode.REORDERED not in {f.code for f in c.contradictions}
