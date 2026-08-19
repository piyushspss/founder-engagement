"""Raw profile -> CanonicalProfile.

Pure function of (raw profile, config). No I/O, no scoring, no assessment.

Every judgment the normalizer makes is recorded as a flag rather than folded
silently into the output, because confidence (PLAN §4.3) prices contradictions
and inferences, and the UI has to be able to show fact vs. guess.
"""

from __future__ import annotations

import re

from app.models.canonical import (CanonicalEducation, CanonicalProfile,
                                  CanonicalRole, CanonicalTotals, Flag,
                                  FlagCode, FlagKind, FounderTitleFlag,
                                  MonthYear, Ternary)
from app.models.raw import RawProfile
from app.normalize.config import Config, load_config
from app.normalize.dates import merge_intervals, months_between, parse_date
from app.normalize.education import classify_degree, match_institution
from app.normalize.health import classify_health
from app.normalize.titles import classify_title, headline_suggests_founder

# A stated total may legitimately disagree with the sum of roles by a rounding
# month or two; below this it is noise, not a contradiction.
TOTAL_TOLERANCE_MONTHS = 2

# A year-only date is anchored to mid-year, so it carries up to 6 months of
# error. An "overlap" smaller than that is an artefact of our own inference, not
# something the record says — see `_detect_overlaps`.
INFERRED_MONTH_UNCERTAINTY = 6

# "51-200 employees" / "10001+ employees" / "1-10 employees"
_SIZE_RANGE = re.compile(r"^\s*([\d,]+)\s*(?:-\s*([\d,]+)|\+)?\s*employees?\s*$", re.I)


def parse_size_range(text: str | None) -> tuple[int | None, int | None]:
    """Parse a supplied size band into (min, max). An open-ended band ('10001+')
    has no max. Unparseable input yields (None, None) — never a guess."""
    if not text:
        return None, None
    m = _SIZE_RANGE.match(text)
    if not m:
        return None, None
    lo = int(m.group(1).replace(",", ""))
    hi = int(m.group(2).replace(",", "")) if m.group(2) else None
    return lo, hi


def normalize(raw: RawProfile, cfg: Config | None = None,
              person_id: str | None = None) -> CanonicalProfile:
    """Raw supplied record → CanonicalProfile, with flags and provenance.

    Never invents a fact and never drops one. Anything the normalizer could not
    read becomes a QUALITY flag, anything the record says twice and differently
    becomes a CONTRADICTION flag, and any gap the normalizer filled with a
    judgment becomes an INFERENCE flag. All three are reported to the human and
    only ever cost CONFIDENCE — none is negative evidence about the founder.

    Pure: no clock, no I/O, no database. Dedup is deliberately NOT done here,
    because it is corpus-level (`normalize_corpus`)."""
    cfg = cfg or load_config()
    pid = person_id or raw.mdm_person_id or "unknown"
    flags: list[Flag] = []
    provenance: dict[str, list[str]] = {}

    roles, role_flags = _normalize_roles(raw, cfg, provenance)
    flags.extend(role_flags)

    education = _normalize_education(raw, cfg, provenance)
    if not education:
        flags.append(Flag(code=FlagCode.NO_EDUCATION, kind=FlagKind.QUALITY,
                          detail="no education entries recorded",
                          source_fields=("education",)))

    totals, total_flags = _compute_totals(raw, roles, provenance)
    flags.extend(total_flags)

    # A8: a headline claiming founder, with no explicit founder role, is POSSIBLE
    # only. It never becomes founder evidence; it costs confidence instead.
    if (headline_suggests_founder(raw.headline)
            and not any(r.founder_title_flag is FounderTitleFlag.EXPLICIT for r in roles)):
        flags.append(Flag(
            code=FlagCode.POSSIBLE_FOUNDER, kind=FlagKind.INFERENCE,
            detail=(f"headline {raw.headline!r} suggests founding, but no experience entry "
                    f"carries an explicit founder title — POSSIBLE only (A8)"),
            source_fields=("headline",),
        ))

    if raw.headline:
        provenance["headline"] = ["headline"]
    for field in ("location_city", "location_state", "location_country"):
        if getattr(raw, field):
            provenance[field] = [field]

    return CanonicalProfile(
        person_id=pid,
        headline=raw.headline,
        roles=roles,
        education=education,
        totals=totals,
        location_city=raw.location_city,
        location_state=raw.location_state,
        location_country=raw.location_country,
        flags=flags,
        provenance=provenance,
    )


# --------------------------------------------------------------------------
def _normalize_roles(raw: RawProfile, cfg: Config,
                     provenance: dict[str, list[str]]) -> tuple[list[CanonicalRole], list[Flag]]:
    """Normalize `experience[]` into chronologically ordered CanonicalRoles.

    Each role keeps its `raw_index` so provenance paths point back at the
    supplied array, and mutates `provenance` in place as it goes."""
    profile_flags: list[Flag] = []
    experiences = raw.experience or []
    if not experiences:
        profile_flags.append(Flag(
            code=FlagCode.NO_EXPERIENCE_HISTORY, kind=FlagKind.QUALITY,
            detail="experience history is absent — assessment rests on headline/education only",
            source_fields=("experience",)))
        return [], profile_flags

    built: list[tuple[MonthYear | None, int, CanonicalRole]] = []
    for raw_idx, exp in enumerate(experiences):
        src = f"experience[{raw_idx}]"
        role_flags: list[Flag] = []

        start, f = parse_date(exp.date_from, exp.date_from_year, exp.date_from_month,
                              source_prefix=src, kind="from")
        role_flags.extend(f)
        end, f = parse_date(exp.date_to, exp.date_to_year, exp.date_to_month,
                            source_prefix=src, kind="to")
        role_flags.extend(f)

        is_current, cur_flags = _resolve_currentness(exp, end, src)
        role_flags.extend(cur_flags)

        if start is None:
            role_flags.append(Flag(
                code=FlagCode.MISSING_DATES, kind=FlagKind.QUALITY,
                detail="no usable start date for this role",
                source_fields=(f"{src}.date_from", f"{src}.date_from_year")))

        duration = exp.duration_months
        if duration is None and start and end:
            duration = months_between(start, end)
            role_flags.append(Flag(
                code=FlagCode.INFERRED_DATE, kind=FlagKind.INFERENCE,
                detail="duration_months absent; derived from start and end dates",
                source_fields=(f"{src}.date_from", f"{src}.date_to")))

        title = exp.position_title or exp.title
        founder_flag, leadership = classify_title(title, cfg)
        health_flag, health_tier = classify_health(
            exp.company_industry, exp.company_categories_and_keywords, exp.company_name, cfg)

        if health_flag is Ternary.UNKNOWN:
            reason = (f"industry {exp.company_industry!r} is not in the starter taxonomy"
                      if exp.company_industry
                      else "no industry recorded")
            role_flags.append(Flag(
                code=FlagCode.UNKNOWN_INDUSTRY, kind=FlagKind.QUALITY,
                detail=(f"{reason} for {exp.company_name!r}; classified UNKNOWN — zero "
                        f"healthcare evidence, not non-healthcare, and no company/domain "
                        f"confidence coverage is claimed"),
                source_fields=(f"{src}.company_industry",
                               f"{src}.company_categories_and_keywords")))
        if exp.management_level is None:
            role_flags.append(Flag(
                code=FlagCode.MISSING_MANAGEMENT_LEVEL, kind=FlagKind.QUALITY,
                detail="management_level not recorded",
                source_fields=(f"{src}.management_level",)))
        if exp.company_size_range is None and exp.company_employees_count is None:
            role_flags.append(Flag(
                code=FlagCode.MISSING_COMPANY_METADATA, kind=FlagKind.QUALITY,
                detail="no company size recorded",
                source_fields=(f"{src}.company_size_range", f"{src}.company_employees_count")))

        size_min, size_max = parse_size_range(exp.company_size_range)
        # Canonical company_size is the EXACT count when supplied. The band is
        # preserved separately; the two are never averaged or reconciled.
        if (exp.company_employees_count is not None
                and (size_min is not None or size_max is not None)):
            below = size_min is not None and exp.company_employees_count < size_min
            above = size_max is not None and exp.company_employees_count > size_max
            if below or above:
                role_flags.append(Flag(
                    code=FlagCode.SIZE_RANGE_MISMATCH, kind=FlagKind.CONTRADICTION,
                    detail=(f"company_employees_count={exp.company_employees_count} falls outside "
                            f"the supplied company_size_range {exp.company_size_range!r}; the exact "
                            f"count is used as canonical company_size and the range is preserved"),
                    source_fields=(f"{src}.company_employees_count", f"{src}.company_size_range"),
                    value=exp.company_employees_count))

        company_age = None
        if exp.company_founded_year and start:
            company_age = max(0, start.year - exp.company_founded_year)

        role = CanonicalRole(
            index=-1, raw_index=raw_idx, title=title, company=exp.company_name,
            industry=exp.company_industry, start_date=start, end_date=end,
            is_current=is_current, duration_months=duration,
            management_level=exp.management_level,
            company_size=exp.company_employees_count,
            company_size_range=exp.company_size_range,
            company_size_range_min=size_min, company_size_range_max=size_max,
            company_age=company_age,
            health_flag=health_flag, health_tier=health_tier,
            founder_title_flag=founder_flag, leadership_title=leadership,
            department=exp.department,
            annual_revenue_usd=exp.company_annual_revenue_source_5,
            growth_pct=exp.company_employees_count_change_yearly_percentage,
            flags=role_flags,
        )
        built.append((start, raw_idx, role))

    # Canonical ordering is reverse-chronological (newest first), matching the
    # source's own order_in_profile convention. Undated roles sort last: they are
    # unplaceable, not oldest.
    ordered = sorted(built, key=lambda t: (t[0] is None, -(t[0].index if t[0] else 0), t[1]))
    roles = []
    for i, (_, _, role) in enumerate(ordered):
        role.index = i
        roles.append(role)
        provenance[f"roles[{i}]"] = [f"experience[{role.raw_index}]"]
        provenance[f"roles[{i}].title"] = [f"experience[{role.raw_index}].position_title"]
        provenance[f"roles[{i}].company"] = [f"experience[{role.raw_index}].company_name"]
        provenance[f"roles[{i}].company_size"] = [
            f"experience[{role.raw_index}].company_employees_count"]
        provenance[f"roles[{i}].company_size_range"] = [
            f"experience[{role.raw_index}].company_size_range"]

    # REORDERED is a claim about the SOURCE being wrong, so it may only be made
    # from roles we could actually place. A role with no date moves to the end of
    # the canonical ordering because it is unplaceable — reading that as "the
    # source was out of order" would turn missing data into a contradiction, and
    # contradictions cost confidence (PLAN §4.3). Judge dated roles only.
    dated = [r for r in roles if r.start_date is not None]
    raw_sequence = sorted(dated, key=lambda r: r.raw_index)
    if [r.raw_index for r in dated] != [r.raw_index for r in raw_sequence]:
        profile_flags.append(Flag(
            code=FlagCode.REORDERED, kind=FlagKind.QUALITY,
            detail=(f"experience[] was not in reverse-chronological order; dated roles "
                    f"reordered to raw indices {[r.raw_index for r in dated]}"),
            source_fields=tuple(f"experience[{r.raw_index}].date_from" for r in dated)))

    profile_flags.extend(_detect_overlaps(roles))
    return roles, profile_flags


def _resolve_currentness(exp, end: MonthYear | None, src: str) -> tuple[Ternary, list[Flag]]:
    """`is_current` and `active_experience` are independent and often disagree
    with `date_to`. Resolve, and flag the disagreement rather than picking a
    winner silently."""
    flags: list[Flag] = []
    claims_current = bool(exp.is_current) or bool(exp.active_experience)

    if end is not None and claims_current:
        flags.append(Flag(
            code=FlagCode.AMBIGUOUS_CURRENT, kind=FlagKind.CONTRADICTION,
            detail=(f"role claims to be current (is_current={exp.is_current}, "
                    f"active_experience={exp.active_experience}) but has end date {end}"),
            source_fields=(f"{src}.is_current", f"{src}.active_experience", f"{src}.date_to")))
        return Ternary.UNKNOWN, flags

    if end is not None:
        return Ternary.NO, flags

    if claims_current:
        if not exp.is_current and exp.active_experience:
            flags.append(Flag(
                code=FlagCode.INFERRED_CURRENT, kind=FlagKind.INFERENCE,
                detail="is_current is null; treated as current from active_experience and absent date_to",
                source_fields=(f"{src}.active_experience", f"{src}.date_to")))
        return Ternary.YES, flags

    # No end date and nothing claiming currentness: genuinely unknown.
    flags.append(Flag(
        code=FlagCode.AMBIGUOUS_CURRENT, kind=FlagKind.CONTRADICTION,
        detail="no end date and no currentness indicator — cannot tell if the role is ongoing",
        source_fields=(f"{src}.date_to", f"{src}.is_current", f"{src}.active_experience")))
    return Ternary.UNKNOWN, flags


def _detect_overlaps(roles: list[CanonicalRole]) -> list[Flag]:
    """Overlap is reported, not resolved. Concurrent roles are common and often
    legitimate (advisory work, a founder with a day job); the flag exists so
    confidence can price the ambiguity and a human can look."""
    spans = []
    for r in roles:
        if r.start_date is None:
            continue
        end_index = r.end_date.index if r.end_date else (
            r.start_date.index + (r.duration_months or 0))
        spans.append((r.start_date.index, max(end_index, r.start_date.index), r))

    flags = []
    # Sort on the interval only. Two roles can share identical start/end months
    # (duplicated provider rows, concurrent roles), and CanonicalRole is not
    # orderable — letting the tuple comparison fall through to it raises.
    spans.sort(key=lambda sp: (sp[0], sp[1]))
    for i in range(len(spans)):
        for j in range(i + 1, len(spans)):
            s1, e1, r1 = spans[i]
            s2, e2, r2 = spans[j]
            if s2 >= e1:
                break
            months = min(e1, e2) - s2
            # Do not let an inference of ours become a contradiction of theirs.
            uncertain = any(d is not None and d.inferred_month
                            for d in (r1.start_date, r1.end_date,
                                      r2.start_date, r2.end_date))
            floor = INFERRED_MONTH_UNCERTAINTY if uncertain else 1
            if months >= floor:
                flags.append(Flag(
                    code=FlagCode.OVERLAP, kind=FlagKind.CONTRADICTION,
                    detail=(f"roles overlap by {months} months: {r1.title!r} at {r1.company!r} "
                            f"and {r2.title!r} at {r2.company!r}"),
                    source_fields=(f"experience[{r1.raw_index}].date_from",
                                   f"experience[{r2.raw_index}].date_from"),
                    value=months))
    return flags


def _compute_totals(raw: RawProfile, roles: list[CanonicalRole],
                    provenance: dict[str, list[str]]) -> tuple[CanonicalTotals, list[Flag]]:
    """Total experience from the roles, reconciled against any STATED total.

    A material disagreement between the computed and stated totals is a
    CONTRADICTION flag: the record is reported as inconsistent rather than one
    side being silently preferred."""
    flags: list[Flag] = []
    sum_months = sum(r.duration_months or 0 for r in roles)

    spans = []
    for r in roles:
        if r.start_date is None:
            continue
        end_index = r.end_date.index if r.end_date else (
            r.start_date.index + (r.duration_months or 0))
        spans.append((r.start_date.index, max(end_index, r.start_date.index)))
    covered = sum(e - s for s, e in merge_intervals(spans))

    health_months = sum(r.duration_months or 0 for r in roles if r.health_flag is Ternary.YES)
    industries = {r.industry for r in roles if r.industry}
    dated = [r for r in roles if r.start_date]

    totals = CanonicalTotals(
        stated_total_months=raw.total_experience_duration_months,
        sum_role_months=sum_months if roles else None,
        covered_months=covered if roles else None,
        role_count=len(roles),
        health_months=health_months,
        distinct_industries=len(industries),
        explicit_founder_roles=sum(
            1 for r in roles if r.founder_title_flag is FounderTitleFlag.EXPLICIT),
        first_role_start=min((r.start_date for r in dated), key=lambda d: d.index, default=None),
        last_role_end=max((r.end_date for r in roles if r.end_date),
                          key=lambda d: d.index, default=None),
    )

    stated = raw.total_experience_duration_months
    if stated is None:
        flags.append(Flag(code=FlagCode.MISSING_TOTAL_EXPERIENCE, kind=FlagKind.QUALITY,
                          detail="total_experience_duration_months not recorded",
                          source_fields=("total_experience_duration_months",)))
    elif roles:
        # Overlapping roles make sum > elapsed time legitimately, so the stated
        # total is only a contradiction if it sits outside BOTH measures.
        lo = min(sum_months, covered) - TOTAL_TOLERANCE_MONTHS
        hi = max(sum_months, covered) + TOTAL_TOLERANCE_MONTHS
        if not (lo <= stated <= hi):
            delta = stated - sum_months
            flags.append(Flag(
                code=FlagCode.TOTAL_MISMATCH, kind=FlagKind.CONTRADICTION,
                detail=(f"stated total {stated} months is outside the range implied by the roles "
                        f"(sum {sum_months}, elapsed {covered}); delta vs sum = {delta:+d}"),
                source_fields=("total_experience_duration_months",
                               *(f"experience[{r.raw_index}].duration_months" for r in roles)),
                value=delta))
        provenance["totals.stated_total_months"] = ["total_experience_duration_months"]

    return totals, flags


def _normalize_education(raw: RawProfile, cfg: Config,
                         provenance: dict[str, list[str]]) -> list[CanonicalEducation]:
    """Normalize `education[]`: institution matching, tier lookup, degree parsing.

    An institution absent from the starter tier list resolves to
    `InstitutionTier.UNKNOWN`, which is a NEUTRAL assumption about an
    incomplete list — not a judgment about the school (A7)."""
    out = []
    for i, ed in enumerate(raw.education or []):
        name = ed.institution_name or ed.school_name
        canonical, tier, score, flags = match_institution(name, cfg)
        out.append(CanonicalEducation(
            index=i, raw_index=i, institution=name, institution_canonical=canonical,
            institution_tier=tier, match_score=score, degree_raw=ed.degree,
            degree_type=classify_degree(ed.degree, ed.field_of_study),
            field=ed.field_of_study, start_year=ed.date_from_year,
            end_year=ed.date_to_year, flags=flags))
        provenance[f"education[{i}].institution"] = [f"education[{i}].institution_name"]
        provenance[f"education[{i}].degree_type"] = [f"education[{i}].degree",
                                                     f"education[{i}].field_of_study"]
    return out


def normalize_corpus(profiles: list[RawProfile], cfg: Config | None = None) -> list[CanonicalProfile]:
    """Normalize a whole population and attach duplicate links. Dedup needs the
    corpus, so it cannot happen inside `normalize()` for a single record."""
    from app.normalize.dedup import duplicate_flags, find_duplicates

    cfg = cfg or load_config()
    canon = [normalize(p, cfg, person_id=p.mdm_person_id or f"idx:{i}")
             for i, p in enumerate(profiles)]
    links = find_duplicates(profiles)
    for c in canon:
        if c.person_id in links:
            c.duplicates = links[c.person_id]
            c.flags.extend(duplicate_flags(c.duplicates))
    return canon
