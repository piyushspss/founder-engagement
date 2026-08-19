"""Deterministic exceptional-evidence detectors — PLAN §4.2.

Exceptional evidence is a SEPARATE path from `broad_score`: a single rare,
explicit fact must be able to raise attention even when the weighted average is
unremarkable (PLAN §4.2, §4.5 rule 1). That is exactly why these detectors are
the most dangerous code in the system, and why every one of them is written to
fail CLOSED.

Four rules govern this module:

* **Evidence-backed only.** A detector fires only when it can name the raw
  fields it read. There is no detector that concludes anything from *absence*,
  from prestige, or from a plausible narrative. Missing data produces no
  exceptional signal, never an exceptional signal.
* **Explicit only.** No inference. `exit_cue` reads literal acquisition/exit
  wording out of a supplied text field; it does not infer an exit from a company
  disappearing, a title changing, funding, growth or headcount. If the supplied
  schema carries no such wording, the detector correctly fires zero times.
* **Founder evidence stays A8.** CEO / President / Managing Director are
  leadership, never founding. `major_leadership_scope` exists precisely so that
  large-company leadership has somewhere legitimate to go WITHOUT leaking into
  founder evidence.
* **Not-fired is reported, not hidden.** Every evaluation returns a reason, so
  "why is this person not flagged?" is answerable from the same object as
  "why is this person flagged?".

`exceptional_signal` (the flag PLAN §4.5 rule 1 reads) = any STRONG detector, or
>= `exceptional.medium_count` MEDIUM detectors. Strengths per detector come from
`config/weights.yaml`, not from this file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.evidence.progression import (LEVEL_RANK, at_least,
                                      resolve_progression)
from app.evidence.signal import Signal, SignalType, Strength
from app.models.canonical import (CanonicalProfile, DegreeType,
                                  FounderTitleFlag, Ternary)

DETECTOR_NAMES = ["repeat_founder", "exit_cue", "rare_domain_expertise",
                  "exceptional_progression", "major_leadership_scope",
                  "exceptional_credential"]

# The value a fired detector reports. Exceptional detectors are threshold rules,
# not continuous scores: the product question is "did this rare thing happen",
# and reporting a fabricated gradient would imply a precision the rule does not
# have. STRONG/MEDIUM (from config) is what downstream policy reads.
_FIRED_VALUE = {Strength.STRONG: 1.0, Strength.MEDIUM: 0.6, Strength.WEAK: 0.3}

# A year-only date is anchored to mid-year and so carries up to 6 months of
# error (same constant the normalizer uses for overlaps). Added to a measured
# span before the window test, never subtracted.
INFERRED_MONTH_UNCERTAINTY_YEARS = 0.5


@dataclass
class ExceptionalEvidence:
    """The whole exceptional path for one profile."""

    flag: bool = False
    rule: str = ""
    signals: list[Signal] = field(default_factory=list)
    not_fired: dict[str, str] = field(default_factory=dict)

    @property
    def categories(self) -> list[str]:
        """Names of the detectors that fired."""
        return [s.name for s in self.signals]

    def by_strength(self) -> dict[str, list[str]]:
        """Fired detector names grouped by strength, for the UI cue table.

        Deliberately separate from `flag`: a MEDIUM cue can be shown without
        claiming the aggregate priority override fired (F-13)."""
        out: dict[str, list[str]] = {}
        for s in self.signals:
            out.setdefault(s.strength.value, []).append(s.name)
        return out

    def to_dict(self) -> dict:
        """JSON form. `not_fired` is included deliberately — "why is this person
        NOT flagged?" must be answerable from the same object as "why are they?"."""
        return {"flag": self.flag, "rule": self.rule,
                "signals": [s.model_dump(mode="json") for s in self.signals],
                "not_fired": self.not_fired}


def _strength(cfg, name: str) -> Strength:
    """The configured strength for one detector. Strengths are config, not code."""
    return Strength(cfg.weights["exceptional"]["detector_strengths"][name])


def _fire(cfg, name: str, sources, explanation: str) -> Signal:
    """Build the Signal for a fired detector.

    `sources` is mandatory: a detector that cannot name the raw fields it read
    has no business firing."""
    st = _strength(cfg, name)
    return Signal(name=name, value=_FIRED_VALUE[st], strength=st,
                  source_fields=tuple(sources), type=SignalType.DERIVED,
                  observed=True, explanation=explanation)


def _path(role, field_name: str) -> str:
    """Provenance path into the RAW record, using the pre-dedup raw index."""
    return f"experience[{role.raw_index}].{field_name}"


def _size_of(role) -> tuple[int | None, str | None]:
    """Same conservative rule the broad signals use: the exact count when
    supplied, otherwise the LOWER bound of a supplied band. A band's lower bound
    is a fact the record states; a midpoint would be a number we invented."""
    if role.company_size is not None:
        return role.company_size, _path(role, "company_employees_count")
    if role.company_size_range_min is not None:
        return role.company_size_range_min, _path(role, "company_size_range")
    return None, None


# --------------------------------------------------------------- repeat founder
def _founder_role_key(role) -> tuple:
    """Identity of a founder ROLE, for counting DISTINCT ones.

    The provider's arrays contain the same engagement more than once (re-pulls,
    title restatements, merged records). Counting rows would turn one founding
    into a "repeat founder", which is a factual claim about a person, so the key
    is deliberately coarse: the same company at the same start date is ONE
    founding no matter how many rows describe it, and undated rows at the same
    company collapse into one rather than multiplying."""
    company = (role.company or "").strip().lower() or None
    start = role.start_date.index if role.start_date else None
    if company is None:
        # No company to key on: fall back to the title, which at least stops an
        # identical repeated row from counting twice.
        return ("title", (role.title or "").strip().lower(), start)
    return ("company", company, start)


def repeat_founder(profile: CanonicalProfile, cfg) -> tuple[Signal | None, str]:
    """>= N DISTINCT EXPLICIT founder roles (A8). CEO/President/MD are not
    founder titles and cannot contribute here at any company size."""
    p = cfg.weights["exceptional"]
    need = p["repeat_founder_min_roles"]

    explicit = [r for r in profile.roles
                if r.founder_title_flag is FounderTitleFlag.EXPLICIT]
    if not explicit:
        possible = [r for r in profile.roles
                    if r.founder_title_flag is FounderTitleFlag.POSSIBLE]
        why = ("no EXPLICIT founder title on any role"
               + (f"; {len(possible)} POSSIBLE title(s) do not count (A8)" if possible else ""))
        return None, why

    distinct: dict[tuple, list] = {}
    for r in explicit:
        distinct.setdefault(_founder_role_key(r), []).append(r)
    n = len(distinct)
    if n < need:
        dupes = sum(len(v) - 1 for v in distinct.values())
        why = (f"{n} distinct explicit founder role(s) from {len(explicit)} row(s), "
               f"need {need}")
        if dupes:
            why += (f"; {dupes} row(s) collapsed as repeated representations of the "
                    f"same founding")
        return None, why

    sources = tuple(_path(r, "position_title") for r in explicit)
    detail = "; ".join(
        f"{(rs[0].title or '?')!r} @ {rs[0].company or '?'}"
        f"{' from ' + str(rs[0].start_date) if rs[0].start_date else ' (undated)'}"
        + (f" [{len(rs)} rows collapsed]" if len(rs) > 1 else "")
        for rs in distinct.values())
    return _fire(cfg, "repeat_founder", sources,
                 f"{n} distinct explicit founder roles (A8): {detail}."), ""


# --------------------------------------------------------------------- exit cue
def _kw_pattern(keyword: str) -> re.Pattern:
    """Word-boundary match. Substring matching would let the configured token
    'ipo' fire on 'Chipotle' or 'lipoprotein'."""
    return re.compile(r"(?<!\w)" + re.escape(keyword.lower()) + r"(?!\w)")


def exit_cue(profile: CanonicalProfile, cfg) -> tuple[Signal | None, str]:
    """Literal acquisition/exit wording in a supplied text field. NOTHING else.

    Explicitly NOT evidence of an exit, and deliberately not consulted: company
    growth, company size, funding rounds, a role ending, a title change, or a
    company vanishing from later roles. Each of those is a story we would be
    telling, not a fact the record states.

    The supplied schema carries no narrative/summary field, so the only text
    this can read is `headline` and `experience[].position_title`. On this data
    the honest expected outcome is zero fires."""
    keywords = cfg.weights["exceptional"]["exit_keywords"]
    pats = [(k, _kw_pattern(k)) for k in keywords]

    scanned = [("headline", profile.headline)]
    for r in profile.roles:
        scanned.append((_path(r, "position_title"), r.title))

    hits = [(p, text, k) for p, text in scanned if text
            for k, pat in pats if pat.search(text.lower())]
    if not hits:
        n = sum(1 for _, t in scanned if t)
        return None, (f"no configured exit keyword found in the {n} text field(s) this "
                      f"schema supplies (headline, position_title); no narrative field "
                      f"exists to read")
    detail = "; ".join(f"{k!r} in {p} ({text!r})" for p, text, k in hits)
    return _fire(cfg, "exit_cue", tuple(p for p, _, _ in hits),
                 f"Explicit exit/acquisition wording read verbatim: {detail}."), ""


# ------------------------------------------------------------ rare domain
def rare_domain_expertise(profile: CanonicalProfile, cfg) -> tuple[Signal | None, str]:
    """A config-listed rare specialty appearing verbatim in a supplied text
    field. The specialty list is an MVP assumption (config), not ground truth."""
    specialties = [s.lower() for s in cfg.weights["exceptional"]["rare_domain_specialties"]]

    scanned: list[tuple[str, str | None]] = [("headline", profile.headline)]
    for r in profile.roles:
        scanned += [(_path(r, "position_title"), r.title),
                    (_path(r, "department"), r.department),
                    (_path(r, "company_industry"), r.industry)]
    for e in profile.education:
        scanned.append((f"education[{e.raw_index}].field_of_study", e.field))

    hits = [(p, text, s) for p, text in scanned if text
            for s in specialties if s in text.lower()]
    if not hits:
        return None, (f"none of the {len(specialties)} configured rare specialties appear "
                      f"in any supplied title/department/industry/field-of-study/headline")
    detail = "; ".join(f"{s!r} in {p} ({text!r})" for p, text, s in hits)
    return _fire(cfg, "rare_domain_expertise", tuple(dict.fromkeys(p for p, _, _ in hits)),
                 f"Configured rare specialty matched verbatim: {detail}."), ""


# ---------------------------------------------------- exceptional progression
def exceptional_progression(profile: CanonicalProfile, cfg) -> tuple[Signal | None, str]:
    """Materially unusual ACCELERATION — not "the career went up".

    An ordinary promotion is positive trajectory and the broad `career_trajectory`
    signal (§4.1) already rewards it. This detector only fires when the pace
    clears one of the configured step/window rules, which are deliberately
    tighter than "some progression happened".

    Progression is read through `resolve_progression`, the SAME canonical
    resolution the broad signal uses (CP3 rule): the provider's levels are
    believed unless they claim a regression, in which case a same-family title
    promotion overrides them, and an unresolvable conflict asserts nothing. This
    detector holds no opinion of its own about seniority.

    Chronology gates, both conservative:
    * both endpoints need an observed start date — a missing or unmeasurable
      chronology can never trigger this;
    * where a start month was INFERRED by the normalizer rather than read, the
      inferred uncertainty is added to the measured span before it is tested
      against the window, so an inference of ours can never manufacture speed.
    """
    p = cfg.weights["exceptional"]
    rules = p["exceptional_progression_rules"]
    rule_txt = " or ".join(f">={r['min_steps']} steps in <={r['window_years']}y"
                           for r in rules)

    dated = [r for r in profile.roles
             if r.start_date and r.management_level in LEVEL_RANK]
    if len(dated) < 2:
        return None, (f"{len(dated)} dated+levelled role(s) — chronology insufficient to "
                      f"measure progression at all")

    dated.sort(key=lambda r: r.start_date.index)
    best = None          # (steps, years_effective, a, b, res)
    unresolved = 0
    for i, a in enumerate(dated):
        for b in dated[i + 1:]:
            res = resolve_progression(a, b)
            if not res.resolved:
                unresolved += 1
                continue
            span = (b.start_date.index - a.start_date.index) / 12
            # Do not let our own month inference create acceleration.
            if a.start_date.inferred_month or b.start_date.inferred_month:
                span += INFERRED_MONTH_UNCERTAINTY_YEARS
            if any(res.steps >= r["min_steps"] and span <= r["window_years"]
                   for r in rules):
                if best is None or res.steps > best[0]:
                    best = (res.steps, span, a, b, res)

    if best is None:
        return None, (f"no role pair meets the configured rule ({rule_txt}) on the "
                      f"CP3-resolved progression"
                      + (f"; {unresolved} pair(s) had an unresolvable level/title "
                         f"conflict and assert nothing" if unresolved else "")
                      + " — ordinary progression is not exceptional")

    steps, years, a, b, res = best
    return _fire(cfg, "exceptional_progression",
                 tuple(res.source_fields) + (_path(a, "date_from"), _path(b, "date_from")),
                 f"{res.explanation.rstrip('.')} in {years:.1f} years, against the "
                 f"configured rule ({rule_txt})."), ""


# ---------------------------------------------------- major leadership scope
def major_leadership_scope(profile: CanonicalProfile, cfg) -> tuple[Signal | None, str]:
    """A configured senior level (C-Level/VP/...) at a company whose SUPPLIED
    size meets the threshold.

    This never touches founder evidence: a CEO is a CEO here, at any size. And a
    missing company size cannot satisfy the threshold — the scope condition is
    about a number the record states, so no number means no fire."""
    p = cfg.weights["exceptional"]
    levels, need = p["major_leadership_levels"], p["major_leadership_min_employees"]

    senior = [r for r in profile.roles if r.management_level in levels]
    if not senior:
        return None, (f"no role at a configured major-leadership level "
                      f"({', '.join(levels)})")

    sized = [(s, path, r) for r in senior for s, path in [_size_of(r)] if s is not None]
    if not sized:
        return None, (f"{len(senior)} senior role(s) but none carries a company size — "
                      f"missing size cannot satisfy the >= {need} employee threshold")

    qualifying = [(s, path, r) for s, path, r in sized if s >= need]
    if not qualifying:
        best = max(sized, key=lambda t: t[0])
        return None, (f"largest sized senior role is {best[0]} employees at "
                      f"{best[2].company!r}, below the {need} threshold")

    size, path, role = max(qualifying, key=lambda t: t[0])
    founder_note = ("" if role.founder_title_flag is FounderTitleFlag.EXPLICIT else
                    " This is leadership evidence only — it does not make the person a founder (A8).")
    return _fire(cfg, "major_leadership_scope",
                 (_path(role, "management_level"), _path(role, "position_title"), path),
                 f"{role.management_level} ({role.title!r}) at {role.company!r}, "
                 f"{size} employees >= configured {need}.{founder_note}"), ""


# ---------------------------------------------------- exceptional credential
def exceptional_credential(profile: CanonicalProfile, cfg) -> tuple[Signal | None, str]:
    """A config-listed terminal credential (MD / PhD / DO).

    Two things this is NOT. It is not an institution-prestige rule: an elite
    school with an ordinary degree contributes nothing here, and the tier list
    is not consulted at all. And it is not a seniority rule: the degree must be
    recorded on an education entry."""
    p = cfg.weights["exceptional"]
    wanted = {d.upper() for d in p["exceptional_credential_degrees"]}

    hits = [e for e in profile.education if e.degree_type.value.upper() in wanted]
    if not hits:
        if not profile.education:
            return None, "no education recorded — absence is not a credential"
        got = sorted({e.degree_type.value for e in profile.education})
        tiers = sorted({e.institution_tier.value for e in profile.education})
        return None, (f"degrees present {got} include none of the configured "
                      f"{sorted(wanted)}; institution tier {tiers} is deliberately not "
                      f"consulted by this detector")

    sources = tuple(f"education[{e.raw_index}].degree" for e in hits)
    fields = [e.field for e in hits if e.field]
    field_note = f" Field(s): {', '.join(fields)}." if fields else " No field_of_study supplied."
    return _fire(cfg, "exceptional_credential", sources,
                 f"Configured terminal credential(s) "
                 f"{', '.join(e.degree_type.value for e in hits)} read from the education "
                 f"entries.{field_note}"), ""


DETECTORS = {
    "repeat_founder": repeat_founder,
    "exit_cue": exit_cue,
    "rare_domain_expertise": rare_domain_expertise,
    "exceptional_progression": exceptional_progression,
    "major_leadership_scope": major_leadership_scope,
    "exceptional_credential": exceptional_credential,
}


def detect_exceptional(profile: CanonicalProfile, cfg) -> ExceptionalEvidence:
    """Run every detector. Fires are Signals with provenance; non-fires keep
    their reason so the UI can answer 'why not?' as well as 'why?'."""
    out = ExceptionalEvidence()
    for name in DETECTOR_NAMES:
        signal, why = DETECTORS[name](profile, cfg)
        if signal is not None:
            out.signals.append(signal)
        else:
            out.not_fired[name] = why

    medium_count = cfg.weights["exceptional"]["medium_count"]
    strong = [s.name for s in out.signals if s.strength is Strength.STRONG]
    medium = [s.name for s in out.signals if s.strength is Strength.MEDIUM]
    if strong:
        out.flag, out.rule = True, f"STRONG detector fired: {', '.join(strong)}"
    elif len(medium) >= medium_count:
        out.flag = True
        out.rule = f"{len(medium)} MEDIUM detectors (>= {medium_count}): {', '.join(medium)}"
    else:
        out.flag = False
        out.rule = (f"no STRONG detector and {len(medium)} MEDIUM (< {medium_count}) — "
                    f"not exceptional")
    return out
