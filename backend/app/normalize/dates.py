"""Date normalization.

The raw schema carries dates twice — as a "MM/YYYY" string and as decomposed
year/month integers — and the two disagree or go missing independently. Rules:

* prefer the decomposed integers, fall back to the string;
* a year with no month is usable: fill the month and record INFERRED_DATE, so
  confidence pays for the guess rather than the guess being invisible;
* no year at all -> None. A missing date is missing, never "today".
"""

from __future__ import annotations

import re

from app.models.canonical import Flag, FlagCode, FlagKind, MonthYear

_MMYYYY = re.compile(r"^\s*(\d{1,2})\s*/\s*(\d{4})\s*$")
_YYYY = re.compile(r"^\s*(\d{4})\s*$")

# A year with no month is anchored to July: mid-year minimises the expected
# error against a uniformly-distributed true month (max 6 months either way).
INFERRED_MONTH = 7


def parse_date(
    date_str: str | None,
    year: int | None,
    month: int | None,
    *,
    source_prefix: str,
    kind: str,
) -> tuple[MonthYear | None, list[Flag]]:
    """Returns (date, flags). `kind` is 'from' or 'to', used in flag detail."""
    flags: list[Flag] = []
    y, m = year, month
    src: list[str] = []

    if y is not None:
        src.append(f"{source_prefix}.date_{kind}_year")
    if m is not None:
        src.append(f"{source_prefix}.date_{kind}_month")

    if (y is None or m is None) and date_str:
        if match := _MMYYYY.match(date_str):
            sm, sy = int(match.group(1)), int(match.group(2))
            if y is None:
                y = sy
            if m is None and 1 <= sm <= 12:
                m = sm
            src.append(f"{source_prefix}.date_{kind}")
        elif match := _YYYY.match(date_str):
            if y is None:
                y = int(match.group(1))
            src.append(f"{source_prefix}.date_{kind}")

    if y is None:
        return None, flags

    if m is None or not (1 <= m <= 12):
        flags.append(Flag(
            code=FlagCode.INFERRED_DATE,
            kind=FlagKind.INFERENCE,
            detail=f"month missing for date_{kind}; anchored to {INFERRED_MONTH:02d}/{y}",
            source_fields=tuple(src) or (f"{source_prefix}.date_{kind}_year",),
        ))
        return MonthYear(year=y, month=INFERRED_MONTH, inferred_month=True), flags

    return MonthYear(year=y, month=m), flags


def months_between(start: MonthYear, end: MonthYear) -> int:
    """Inclusive month span, floored at 0. A reversed pair yields 0 rather than a
    negative duration — the contradiction is flagged elsewhere, not scored."""
    return max(0, end.index - start.index)


def merge_intervals(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Union of [start, end) month-index intervals, so overlapping roles are not
    double-counted when measuring how much career a profile actually covers."""
    if not spans:
        return []
    spans = sorted(spans)
    out = [list(spans[0])]
    for s, e in spans[1:]:
        if s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [(a, b) for a, b in out]
