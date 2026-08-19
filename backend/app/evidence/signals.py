"""Deterministic signals — PLAN §4.1.

Each function is a pure function of (CanonicalProfile, Config) returning one
Signal. Normalizations (caps, log scaling, saturating curves, unknown = neutral)
come from `config/weights.yaml` — no threshold is hard-coded here.

Two rules govern every signal in this file:

* **Unknown is neutral, never negative.** When the inputs a signal needs are
  absent, the signal returns its configured `unknown_neutral` value with
  `observed=False` and strength NONE. Removing a field can never push a signal
  below that value (enforced by property tests).
* **Provenance is mandatory.** Any signal with a non-neutral value names the raw
  JSON paths it was computed from.
"""

from __future__ import annotations

import math

from app.evidence.progression import LEVEL_RANK, resolve_progression
from app.evidence.signal import Signal, SignalType, Strength, strength_for
from app.models.canonical import (CanonicalProfile, DegreeType, FounderTitleFlag,
                                  InstitutionTier, Ternary)

SIGNAL_NAMES = ["founder_evidence", "healthcare_depth", "leadership",
                "career_trajectory", "education_signal", "operating_environment", "other"]

# LEVEL_RANK (the coarse step ladder) and the CP3 conflict rule now live in
# app.evidence.progression, so this signal and the exceptional_progression
# detector resolve a career the same way. Re-exported for existing importers.


def _log_scale(value: float, cap: float) -> float:
    """Saturating log curve: 0 at 0, 1.0 at `cap`, diminishing returns between."""
    if value <= 0 or cap <= 0:
        return 0.0
    return min(1.0, math.log1p(value) / math.log1p(cap))


def _clamp(x: float) -> float:
    """Constrain a signal value to the 0–1 band every signal is defined on."""
    return max(0.0, min(1.0, x))


def _path(role, field: str) -> str:
    """Provenance path into the RAW record, using the pre-dedup raw index."""
    return f"experience[{role.raw_index}].{field}"


def _size_of(role) -> tuple[int | None, str | None]:
    """Company size actually consumed by the signals, with the raw path it came
    from. The exact count wins when supplied (CP2 cleanup); otherwise the lower
    bound of the supplied band is used, which is conservative and never invents a
    midpoint."""
    if role.company_size is not None:
        return role.company_size, _path(role, "company_employees_count")
    if role.company_size_range_min is not None:
        return role.company_size_range_min, _path(role, "company_size_range")
    return None, None


# ---------------------------------------------------------------- 25 · founder
def founder_evidence(profile: CanonicalProfile, cfg) -> Signal:
    """A8: EXPLICIT founder titles only. POSSIBLE earns `possible_credit`, which
    is 0.0 in config — a suspicion is not evidence.

    Founder evidence requires explicit FOUNDER-TITLE evidence. CEO, President
    and Managing Director are LEADERSHIP, not founding, and are scored by
    `leadership()` / `major_leadership_scope` instead; letting them leak in here
    would silently redefine what the product means by "founder".

    No explicit title returns `unknown_neutral` with `observed=False` — the
    absence of a founder title is neutral for this signal and reduces
    confidence, never a negative score."""
    p = cfg.weights["signal_params"]["founder_evidence"]
    neutral = p["unknown_neutral"]

    explicit = [r for r in profile.roles if r.founder_title_flag is FounderTitleFlag.EXPLICIT]
    possible = [r for r in profile.roles if r.founder_title_flag is FounderTitleFlag.POSSIBLE]

    if not explicit:
        if possible:
            value = _clamp(neutral + p["possible_credit"])
            return Signal(
                name="founder_evidence", value=value,
                strength=strength_for(value, observed=p["possible_credit"] > 0),
                source_fields=tuple(_path(r, "position_title") for r in possible),
                type=SignalType.DERIVED, observed=p["possible_credit"] > 0,
                explanation=(f"{len(possible)} role(s) carry an ambiguous founding title "
                             f"(POSSIBLE). A8 scores POSSIBLE at {p['possible_credit']} — "
                             f"suspected founding is not founder evidence."))
        return Signal(
            name="founder_evidence", value=neutral, strength=Strength.NONE,
            source_fields=(), type=SignalType.DERIVED, observed=False,
            explanation=("No explicit founder title observed in any role. This records "
                         "absence of evidence, not evidence of absence."))

    tenure = sum(r.duration_months or 0 for r in explicit)
    bonus = p["tenure_bonus_max"] * min(1.0, tenure / p["tenure_bonus_full_months"])
    value = _clamp(p["base_explicit"] + bonus)
    sources = tuple(_path(r, "position_title") for r in explicit) + tuple(
        _path(r, "duration_months") for r in explicit if r.duration_months)
    return Signal(
        name="founder_evidence", value=value, strength=strength_for(value, True),
        source_fields=sources, type=SignalType.DERIVED, observed=True,
        explanation=(f"{len(explicit)} explicit founder role(s) "
                     f"({', '.join(r.title or '?' for r in explicit)}), {tenure} months of "
                     f"founder tenure: base {p['base_explicit']} + capped tenure bonus {bonus:.2f}."))


# ------------------------------------------------------------- 20 · healthcare
def healthcare_depth(profile: CanonicalProfile, cfg) -> Signal:
    """Depth of healthcare experience: log-scaled health role-months, plus a
    flat bonus for a tier-listed health employer.

    Roles whose industry is unreadable are `Ternary.UNKNOWN` and count as
    NEITHER health nor non-health — an unclassifiable industry is missing data,
    not a finding that the person worked outside healthcare. Their paths are
    still cited so a reviewer can see what could not be read."""
    p = cfg.weights["signal_params"]["healthcare_depth"]
    health_roles = [r for r in profile.roles if r.health_flag is Ternary.YES]
    unknown_roles = [r for r in profile.roles if r.health_flag is Ternary.UNKNOWN]

    if not health_roles:
        note = ""
        if unknown_roles:
            note = (f" {len(unknown_roles)} role(s) have no usable industry and are "
                    f"UNKNOWN — counted as neither health nor non-health.")
        return Signal(
            name="healthcare_depth", value=p["unknown_neutral"], strength=Strength.NONE,
            source_fields=tuple(_path(r, "company_industry") for r in unknown_roles),
            type=SignalType.DERIVED, observed=False,
            explanation=f"No healthcare experience observed.{note}")

    months = sum(r.duration_months or 0 for r in health_roles)
    base = _log_scale(months, p["log_scale_cap_months"])
    tiered = [r for r in health_roles if r.health_tier]
    bonus = p["tier_bonus_max"] if tiered else 0.0
    value = _clamp(base + bonus)

    sources = tuple(_path(r, "company_industry") for r in health_roles) + tuple(
        _path(r, "duration_months") for r in health_roles if r.duration_months)
    tier_note = (f" +{bonus:.2f} for tiered health employer "
                 f"({', '.join(r.company or '?' for r in tiered)})." if tiered else "")
    return Signal(
        name="healthcare_depth", value=value, strength=strength_for(value, True),
        source_fields=sources, type=SignalType.DERIVED, observed=True,
        explanation=(f"{months} months across {len(health_roles)} healthcare role(s), "
                     f"log-scaled against a {p['log_scale_cap_months']}-month cap → "
                     f"{base:.2f}.{tier_note}"))


# ------------------------------------------------------------- 15 · leadership
def leadership(profile: CanonicalProfile, cfg) -> Signal:
    """Seniority reached, from `management_level` scored against config.

    Levels outside the configured taxonomy are UNRATED, not zero-rated: an
    unrecognised level is something we cannot read, so it lowers coverage (and
    therefore confidence) rather than asserting low seniority. This signal is
    leadership evidence ONLY and never contributes founder evidence."""
    p = cfg.weights["signal_params"]["leadership"]
    scores = p["level_scores"]
    rated = [(scores[r.management_level], r) for r in profile.roles
             if r.management_level and r.management_level in scores]
    unrated = [r for r in profile.roles if r.management_level and r.management_level not in scores]

    if not rated:
        note = (f" Level(s) {sorted({r.management_level for r in unrated})} are not in the "
                f"configured taxonomy and are treated as unknown."
                if unrated else " No management_level recorded on any role.")
        return Signal(
            name="leadership", value=p["unknown_neutral"], strength=Strength.NONE,
            source_fields=tuple(_path(r, "management_level") for r in profile.roles),
            type=SignalType.DERIVED, observed=False,
            explanation=f"Leadership level not observable.{note}")

    best_score, best_role = max(rated, key=lambda t: t[0])
    size, size_path = _size_of(best_role)
    bonus = 0.0
    if size:
        bonus = p["scope_bonus_max"] * min(1.0, size / p["scope_full_employees"])
    value = _clamp(best_score + bonus)

    sources = [_path(best_role, "management_level")]
    if size_path:
        sources.append(size_path)
    scope = (f" Scope bonus +{bonus:.2f} from {size} employees at {best_role.company!r}."
             if size else " No company size available for a scope bonus (neutral).")
    return Signal(
        name="leadership", value=value, strength=strength_for(value, True),
        source_fields=tuple(sources), type=SignalType.DERIVED, observed=True,
        explanation=(f"Highest management level held: {best_role.management_level} "
                     f"({best_score}) as {best_role.title!r}.{scope}"))


# ------------------------------------------------------ 15 · career trajectory
def career_trajectory(profile: CanonicalProfile, cfg) -> Signal:
    """Slope of level progression over time. Unobservable trajectory returns the
    configured neutral — a flat career and an unmeasurable one are different
    things, and only the first is evidence."""
    p = cfg.weights["signal_params"]["career_trajectory"]
    neutral = p["unknown_neutral"]

    dated = [r for r in profile.roles
             if r.start_date and r.management_level in LEVEL_RANK]
    if len(dated) < p["min_roles"]:
        return Signal(
            name="career_trajectory", value=neutral, strength=Strength.NONE,
            source_fields=tuple(_path(r, "management_level") for r in profile.roles),
            type=SignalType.DERIVED, observed=False,
            explanation=(f"Fewer than {p['min_roles']} dated, levelled roles — trajectory "
                         f"cannot be measured. Unmeasurable is not flat."))

    dated.sort(key=lambda r: r.start_date.index)
    first, last = dated[0], dated[-1]
    years = (last.start_date.index - first.start_date.index) / 12
    if years <= 0:
        return Signal(
            name="career_trajectory", value=neutral, strength=Strength.NONE,
            source_fields=(_path(first, "date_from"), _path(last, "date_from")),
            type=SignalType.DERIVED, observed=False,
            explanation="All levelled roles start in the same month — no time base to measure over.")

    # The one canonical resolution (CP3 rule, now shared with §4.2).
    res = resolve_progression(first, last)
    if not res.resolved:
        return Signal(
            name="career_trajectory", value=neutral, strength=Strength.NONE,
            source_fields=res.source_fields, type=SignalType.DERIVED, observed=False,
            explanation=res.explanation)

    jumps = res.steps
    sources = list(res.source_fields) + [_path(first, "date_from"), _path(last, "date_from")]
    basis = res.explanation.rstrip(".")

    slope = jumps / years
    value = _clamp(slope / p["slope_cap_levels_per_year"])
    return Signal(
        name="career_trajectory", value=value, strength=strength_for(value, True),
        source_fields=tuple(sources), type=SignalType.DERIVED, observed=True,
        explanation=(f"{basis} over {years:.1f} years = {slope:.2f} levels/yr, "
                     f"against a {p['slope_cap_levels_per_year']}/yr cap."))


# -------------------------------------------------------------- 10 · education
def education_signal(profile: CanonicalProfile, cfg) -> Signal:
    """A7 + A9: an institution not on the tier list is UNKNOWN and contributes
    ZERO positive evidence — not a penalty, and not a reward for being unknown.
    A recognised credential still counts: `max(institution_score, degree_score)`
    means an MD from an unlisted school scores on the MD."""
    p = cfg.weights["signal_params"]["education_signal"]
    tiers, degrees = p["institution_tier_scores"], p["degree_scores"]

    if not profile.education:
        return Signal(
            name="education_signal", value=p["unknown_neutral"], strength=Strength.NONE,
            source_fields=("education",), type=SignalType.DERIVED, observed=False,
            explanation="No education recorded — scored at the neutral default, not penalised.")

    best_value, best_entry, best_kind = -1.0, None, ""
    any_observed = False
    for e in profile.education:
        inst_score = tiers.get(e.institution_tier.value, tiers["unknown"])
        deg_score = degrees.get(e.degree_type.value, degrees.get("OTHER", 0.3))
        observed = (e.institution_tier is not InstitutionTier.UNKNOWN
                    or e.degree_type is not DegreeType.OTHER)
        any_observed = any_observed or observed
        value = max(inst_score, deg_score)
        if value > best_value:
            best_value, best_entry = value, e
            best_kind = "institution tier" if inst_score >= deg_score else "degree"

    sources = [f"education[{best_entry.raw_index}].institution_name",
               f"education[{best_entry.raw_index}].degree"]
    tier_txt = (best_entry.institution_canonical or best_entry.institution or "?")
    if best_entry.institution_tier is InstitutionTier.UNKNOWN:
        tier_txt += (" (not on the tier list → UNKNOWN, contributes no positive evidence "
                     "and no penalty)")
    return Signal(
        name="education_signal", value=_clamp(best_value),
        strength=strength_for(best_value, any_observed),
        source_fields=tuple(sources), type=SignalType.DERIVED, observed=any_observed,
        explanation=(f"Best of {len(profile.education)} entries, driven by {best_kind}: "
                     f"{best_entry.degree_type.value} at {tier_txt} → {best_value:.2f}."))


# --------------------------------------------------- 10 · operating environment
def operating_environment(profile: CanonicalProfile, cfg) -> Signal:
    """Scale of the largest environment the person has operated in.

    Uses the exact headcount when supplied, otherwise the LOWER bound of a
    supplied band (never an invented midpoint). Roles with no size at all are
    skipped rather than treated as small — unknown scale is neutral."""
    p = cfg.weights["signal_params"]["operating_environment"]
    best_value, best_role, best_size, best_path = -1.0, None, None, None
    for r in profile.roles:
        size, path = _size_of(r)
        if size is None:
            continue
        v = _log_scale(size, p["log_scale_cap_employees"])
        if v > best_value:
            best_value, best_role, best_size, best_path = v, r, size, path

    if best_role is None:
        return Signal(
            name="operating_environment", value=p["unknown_neutral"], strength=Strength.NONE,
            source_fields=tuple(_path(r, "company_employees_count") for r in profile.roles),
            type=SignalType.DERIVED, observed=False,
            explanation="No company size recorded on any role — neutral, not penalised.")

    sources = [best_path]
    growth_bonus = revenue_bonus = 0.0
    if best_role.growth_pct is not None and best_role.growth_pct > 0:
        growth_bonus = p["growth_bonus_max"] * min(1.0, best_role.growth_pct / p["growth_full_pct"])
        sources.append(_path(best_role, "company_employees_count_change_yearly_percentage"))
    if best_role.annual_revenue_usd:
        revenue_bonus = p["revenue_bonus_max"] * min(
            1.0, best_role.annual_revenue_usd / p["revenue_full_usd"])
        sources.append(_path(best_role, "company_annual_revenue_source_5"))

    value = _clamp(best_value + growth_bonus + revenue_bonus)
    return Signal(
        name="operating_environment", value=value, strength=strength_for(value, True),
        source_fields=tuple(sources), type=SignalType.DERIVED, observed=True,
        explanation=(f"Largest environment operated in: {best_size} employees at "
                     f"{best_role.company!r} → {best_value:.2f}; growth +{growth_bonus:.2f}, "
                     f"revenue +{revenue_bonus:.2f}."))


# ------------------------------------------------------------------- 5 · other
def other(profile: CanonicalProfile, cfg) -> Signal:
    """Breadth of industries plus total experience on a saturating curve."""
    p = cfg.weights["signal_params"]["other"]
    t = profile.totals

    months = t.covered_months or t.sum_role_months or t.stated_total_months
    if not profile.roles and not months:
        return Signal(
            name="other", value=p["unknown_neutral"], strength=Strength.NONE,
            source_fields=("experience", "total_experience_duration_months"),
            type=SignalType.DERIVED, observed=False,
            explanation="No experience history or total to measure breadth or tenure from.")

    breadth = min(1.0, t.distinct_industries / p["breadth_full_industries"])
    years = (months or 0) / 12
    # Saturating: linear up to `lo` years, then flat. Beyond `hi` there is no
    # further credit — 25 years of experience is not 3x better than 20.
    lo = p["tenure_saturation_start_years"]
    tenure = 0.0 if years <= 0 else min(1.0, years / lo)
    value = _clamp(0.5 * breadth + 0.5 * tenure)

    sources = tuple(_path(r, "company_industry") for r in profile.roles if r.industry) or (
        "experience",)
    return Signal(
        name="other", value=value, strength=strength_for(value, True),
        source_fields=sources + ("total_experience_duration_months",),
        type=SignalType.DERIVED, observed=True,
        explanation=(f"{t.distinct_industries} distinct industries → breadth {breadth:.2f}; "
                     f"{years:.1f} years of measured experience → tenure {tenure:.2f} "
                     f"(saturating from {lo}y)."))


SIGNAL_FUNCTIONS = {
    "founder_evidence": founder_evidence,
    "healthcare_depth": healthcare_depth,
    "leadership": leadership,
    "career_trajectory": career_trajectory,
    "education_signal": education_signal,
    "operating_environment": operating_environment,
    "other": other,
}


def compute_signals(profile: CanonicalProfile, cfg) -> list[Signal]:
    """All seven signals, always in `SIGNAL_NAMES` order.

    The list is fixed-length whatever the profile contains: a signal with no
    inputs returns its neutral value with `observed=False` rather than being
    omitted, so a missing field can never silently drop out of the weighted
    average and change the denominator."""
    return [SIGNAL_FUNCTIONS[name](profile, cfg) for name in SIGNAL_NAMES]


def broad_score(signals: list[Signal], cfg) -> float:
    """PLAN §4.1: broad_score = Σ w_i · s_i, weights summing to 100 → 0–100."""
    weights = cfg.weights["signal_weights"]
    return round(sum(weights[s.name] * s.value for s in signals), 2)
