"""Canonical (normalized) founder profile — docs/PLAN.md v2.1 §5.

The canonical profile is the single input to every downstream stage. It is
derived purely from the raw profile plus config; it holds no scores, no
assessment and no human state.

Three principles baked into the shape of this model:

* **Absence is representable and neutral.** Every derived field can be UNKNOWN.
  UNKNOWN never means "no" (PLAN §1, §4.3) — `health_flag=UNKNOWN` is not
  `NON_HEALTH`, and `founder_title_flag=NONE` records that no explicit founder
  title was observed, not that the person is not a founder.
* **Judgment is separated from observation.** Anything the normalizer *inferred*
  rather than *read* is recorded as an INFERENCE flag, so confidence can be
  penalised for it downstream and the UI can show fact vs. guess.
* **Everything is traceable.** `provenance` maps canonical field paths back to
  the raw JSON paths they came from.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FlagKind(str, Enum):
    """What a flag *is*, which decides how confidence treats it (PLAN §4.3)."""

    QUALITY = "QUALITY"            # an observation about coverage/shape of the data
    CONTRADICTION = "CONTRADICTION"  # the record disagrees with itself
    INFERENCE = "INFERENCE"        # the normalizer filled a gap with a judgment


class Ternary(str, Enum):
    """Three-valued flag. `UNKNOWN` is a genuine third state — "we could not
    read this" — and must never be collapsed into `NO`."""

    YES = "YES"
    NO = "NO"
    UNKNOWN = "UNKNOWN"


class FounderTitleFlag(str, Enum):
    """Whether a role carries founder-title evidence (A8).

    Only `EXPLICIT` is founder evidence. CEO / President / Managing Director
    produce `NONE` here and are scored as LEADERSHIP instead."""

    EXPLICIT = "EXPLICIT"  # A8: an unambiguous founder title was read from the role
    POSSIBLE = "POSSIBLE"  # suspected but unconfirmed — never counted as founder evidence
    NONE = "NONE"          # no founder title observed (NOT "is not a founder")


class DegreeType(str, Enum):
    """Recognised credential types. `OTHER` means unparsed, not lesser."""

    MD = "MD"
    DO = "DO"
    PhD = "PhD"
    MBA = "MBA"
    RN = "RN"
    BSN = "BSN"
    BS = "BS"
    BA = "BA"
    MS = "MS"
    OTHER = "OTHER"


class InstitutionTier(str, Enum):
    """Starter tier list. A7: `UNKNOWN` is a NEUTRAL ASSUMPTION about a list we
    know to be incomplete — never negative evidence about the institution or
    the person, and deliberately not a confidence input."""

    TIER_1 = "tier_1"
    TIER_2 = "tier_2"
    UNKNOWN = "unknown"  # A7: unknown is NEUTRAL, never negative


class DuplicateRelation(str, Enum):
    """Strength of a duplicate link. A6b: duplicates are FLAGGED, never merged.
    `NEVER` records conflicting strong hashes — an explicit not-a-duplicate."""

    SAME = "SAME"                      # same mdm_person_id
    HIGH_CONFIDENCE = "HIGH_CONFIDENCE"  # >=2 matching strong hashes
    PROBABLE = "PROBABLE"              # exactly 1 matching strong hash
    NEVER = "NEVER"                    # weak match, strong hashes disagree -> never merge,
                                       # reason recorded as CONFLICTING_IDENTITY_HASHES


class Flag(BaseModel):
    """A single observation about data quality. `code` is stable and is what
    config/weights.yaml keys its penalties on."""

    model_config = ConfigDict(frozen=True)

    code: str
    kind: FlagKind
    detail: str
    source_fields: tuple[str, ...] = ()
    value: float | int | str | None = None  # e.g. the delta on TOTAL_MISMATCH


class MonthYear(BaseModel):
    """A month-precision date. `inferred_month=True` marks a month the
    normalizer supplied for a year-only source, which costs confidence."""

    model_config = ConfigDict(frozen=True)

    year: int
    month: int
    inferred_month: bool = False

    @property
    def index(self) -> int:
        """Months since year 0 — comparable and subtractable."""
        return self.year * 12 + (self.month - 1)

    def __str__(self) -> str:
        """MM/YYYY."""
        return f"{self.month:02d}/{self.year}"


class CanonicalRole(BaseModel):
    """One normalized role. Keeps BOTH indices: `index` is the chronological
    position, `raw_index` the position in the source `experience[]` array, so
    every provenance path points back at the record the user supplied."""

    index: int                       # position in the canonical (chronological) ordering
    raw_index: int                   # position in the raw experience[] array
    title: str | None = None
    company: str | None = None
    industry: str | None = None

    start_date: MonthYear | None = None
    end_date: MonthYear | None = None
    is_current: Ternary = Ternary.UNKNOWN
    duration_months: int | None = None

    management_level: str | None = None
    company_size: int | None = None          # canonical: the EXACT employee count when supplied
    company_size_range: str | None = None    # the supplied range, preserved verbatim
    company_size_range_min: int | None = None
    company_size_range_max: int | None = None
    company_age: int | None = None

    health_flag: Ternary = Ternary.UNKNOWN
    health_tier: str | None = None   # tier_1 / tier_2 if a tiered health employer matched
    founder_title_flag: FounderTitleFlag = FounderTitleFlag.NONE
    leadership_title: bool = False   # CEO/President/MD etc — leadership evidence ONLY (A8)

    department: str | None = None
    annual_revenue_usd: float | None = None
    growth_pct: float | None = None

    flags: list[Flag] = Field(default_factory=list)


class CanonicalEducation(BaseModel):
    """One normalized education entry. An unmatched institution keeps its raw
    name and resolves to `InstitutionTier.UNKNOWN` — readable but unlisted."""

    index: int
    raw_index: int
    institution: str | None = None
    institution_canonical: str | None = None  # tier-list name a fuzzy/alias match resolved to
    institution_tier: InstitutionTier = InstitutionTier.UNKNOWN
    match_score: float | None = None
    degree_raw: str | None = None
    degree_type: DegreeType = DegreeType.OTHER
    field: str | None = None
    start_year: int | None = None
    end_year: int | None = None
    flags: list[Flag] = Field(default_factory=list)


class CanonicalTotals(BaseModel):
    """Experience totals. Keeps the COMPUTED and the STATED figures apart so a
    disagreement between them can be reported rather than silently resolved."""

    stated_total_months: int | None = None   # as claimed by the source
    sum_role_months: int | None = None       # sum of role durations
    covered_months: int | None = None        # union of role intervals (overlap-aware)
    role_count: int = 0
    health_months: int = 0
    distinct_industries: int = 0
    explicit_founder_roles: int = 0
    first_role_start: MonthYear | None = None
    last_role_end: MonthYear | None = None


class DuplicateLink(BaseModel):
    """A flagged relationship to another record. Never an executed merge."""

    other_person_id: str
    relation: DuplicateRelation
    matching_hashes: list[str] = Field(default_factory=list)
    conflicting_hashes: list[str] = Field(default_factory=list)
    merged: bool = False  # ALWAYS False in the MVP — A6b forbids auto-merge


class CanonicalProfile(BaseModel):
    """The normalized founder — the single input every deterministic signal,
    detector and archetype rule reads.

    Carries its own flags and `provenance` map, so every downstream claim can
    name the raw fields behind it. Contains no score, no dimension, no
    disposition and no stage."""

    person_id: str
    headline: str | None = None
    roles: list[CanonicalRole] = Field(default_factory=list)
    education: list[CanonicalEducation] = Field(default_factory=list)
    totals: CanonicalTotals = Field(default_factory=CanonicalTotals)

    location_city: str | None = None
    location_state: str | None = None
    location_country: str | None = None

    flags: list[Flag] = Field(default_factory=list)
    duplicates: list[DuplicateLink] = Field(default_factory=list)
    provenance: dict[str, list[str]] = Field(default_factory=dict)

    # ---- filtered views (the runbook's quality_flags[] / contradictions[]) ----
    def _all_flags(self) -> list[Flag]:
        """Every flag on the profile and on its roles and education entries."""
        out = list(self.flags)
        for r in self.roles:
            out.extend(r.flags)
        for e in self.education:
            out.extend(e.flags)
        return out

    @property
    def quality_flags(self) -> list[Flag]:
        """Observations about coverage/shape. Reported, never scored negatively."""
        return [f for f in self._all_flags() if f.kind is FlagKind.QUALITY]

    @property
    def contradictions(self) -> list[Flag]:
        """Places the record disagrees with itself; charged against confidence."""
        return [f for f in self._all_flags() if f.kind is FlagKind.CONTRADICTION]

    @property
    def inferences(self) -> list[Flag]:
        """Gaps the normalizer filled with a judgment; charged against confidence
        so a filled gap is never mistaken for a supplied fact."""
        return [f for f in self._all_flags() if f.kind is FlagKind.INFERENCE]

    def flag_codes(self) -> set[str]:
        """The set of flag codes present, for tests and quick membership checks."""
        return {f.code for f in self._all_flags()}

    def to_dict(self) -> dict[str, Any]:
        """JSON form with the three filtered flag views expanded alongside the
        raw `flags` list, so consumers need not re-partition them."""
        d = self.model_dump(mode="json")
        d["quality_flags"] = [f.model_dump(mode="json") for f in self.quality_flags]
        d["contradictions"] = [f.model_dump(mode="json") for f in self.contradictions]
        d["inferences"] = [f.model_dump(mode="json") for f in self.inferences]
        return d


# --------------------------------------------------------------------------
# Flag codes. Kept here so config, normalizer, tests and UI share one vocabulary.
# --------------------------------------------------------------------------
class FlagCode:
    """Flag code constants. Codes are stable strings: they appear in stored
    assessments, in confidence penalty tables in config, and in tests."""

    # CONTRADICTION — the record disagrees with itself
    TOTAL_MISMATCH = "TOTAL_MISMATCH"
    OVERLAP = "OVERLAP"
    AMBIGUOUS_CURRENT = "AMBIGUOUS_CURRENT"
    CONFLICTING_IDENTITY_HASHES = "CONFLICTING_IDENTITY_HASHES"
    SIZE_RANGE_MISMATCH = "SIZE_RANGE_MISMATCH"

    # INFERENCE — the normalizer filled a gap
    INFERRED_DATE = "INFERRED_DATE"
    INFERRED_CURRENT = "INFERRED_CURRENT"
    POSSIBLE_FOUNDER = "POSSIBLE_FOUNDER"
    FUZZY_INSTITUTION_MATCH = "FUZZY_INSTITUTION_MATCH"

    # QUALITY — coverage observations, never contradictions
    NO_EXPERIENCE_HISTORY = "NO_EXPERIENCE_HISTORY"
    NO_EDUCATION = "NO_EDUCATION"
    MISSING_DATES = "MISSING_DATES"
    MISSING_MANAGEMENT_LEVEL = "MISSING_MANAGEMENT_LEVEL"
    MISSING_COMPANY_METADATA = "MISSING_COMPANY_METADATA"
    MISSING_TOTAL_EXPERIENCE = "MISSING_TOTAL_EXPERIENCE"
    UNKNOWN_INDUSTRY = "UNKNOWN_INDUSTRY"
    POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"
    # Source-array ordering is a provider formatting artefact that the normalizer
    # repairs deterministically. It is not the record contradicting itself, so it
    # carries no confidence penalty. Genuine chronology conflicts stay CONTRADICTION.
    REORDERED = "REORDERED"
