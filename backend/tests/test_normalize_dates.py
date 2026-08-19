"""Date parsing and interval maths."""

from app.normalize.dates import (INFERRED_MONTH, merge_intervals,
                                 months_between, parse_date)
from app.models.canonical import FlagCode, MonthYear


def _codes(flags):
    return [f.code for f in flags]


def test_prefers_decomposed_integers():
    d, flags = parse_date("03/2023", 2023, 3, source_prefix="experience[0]", kind="from")
    assert (d.year, d.month) == (2023, 3) and not flags


def test_falls_back_to_string_when_integers_missing():
    d, flags = parse_date("07/2019", None, None, source_prefix="experience[0]", kind="from")
    assert (d.year, d.month) == (2019, 7) and not flags


def test_year_only_is_usable_but_flagged_as_inference():
    d, flags = parse_date(None, 2018, None, source_prefix="experience[0]", kind="from")
    assert (d.year, d.month) == (2018, INFERRED_MONTH)
    assert d.inferred_month is True
    assert _codes(flags) == [FlagCode.INFERRED_DATE]


def test_missing_year_yields_no_date_and_no_guess():
    """A missing date must stay missing. Defaulting to 'today' would invent
    tenure out of nothing."""
    d, flags = parse_date(None, None, 5, source_prefix="experience[0]", kind="from")
    assert d is None and flags == []


def test_bare_year_string_parses():
    d, flags = parse_date("2021", None, None, source_prefix="e", kind="to")
    assert d.year == 2021 and d.inferred_month is True


def test_out_of_range_month_is_treated_as_missing():
    d, flags = parse_date(None, 2020, 13, source_prefix="e", kind="from")
    assert d.month == INFERRED_MONTH and _codes(flags) == [FlagCode.INFERRED_DATE]


def test_source_fields_are_recorded_on_inference():
    _, flags = parse_date(None, 2018, None, source_prefix="experience[2]", kind="from")
    assert "experience[2].date_from_year" in flags[0].source_fields


def test_months_between_is_never_negative():
    a, b = MonthYear(year=2020, month=1), MonthYear(year=2019, month=1)
    assert months_between(a, b) == 0
    assert months_between(b, a) == 12


def test_merge_intervals_unions_overlaps():
    assert merge_intervals([(0, 10), (5, 20), (30, 40)]) == [(0, 20), (30, 40)]
    assert merge_intervals([]) == []
    assert merge_intervals([(0, 5), (5, 9)]) == [(0, 9)]
