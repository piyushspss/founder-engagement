"""Title-derived seniority, used ONLY to resolve a conflict between the
provider's `management_level` and the role titles themselves.

Why this exists: the provider's taxonomy conflates individual-contributor
seniority with people management, so it ranks `Manager` above `Senior`. A real
promotion from "Product Manager" to "Senior Product Manager" therefore reads as
a one-level regression. Asserting regression there is a factual error about the
founder, so the trajectory signal needs a narrow, conservative guard.

Deliberate limits:

* it can only be consulted when the provider levels indicate a REGRESSION —
  it never inflates an already-upward trajectory;
* it only applies when the two roles are the same job family, judged by the
  title tokens that remain after seniority modifiers are removed;
* it never infers founder status, and `founder`/`co-founder` is not a seniority
  modifier here;
* when the title and the provider level conflict and cannot be resolved
  conservatively, the caller reports NO trajectory evidence rather than
  asserting a regression.
"""

from __future__ import annotations

import re

# Ordered seniority modifiers. Rank 1 is a plain, unmodified title.
MODIFIER_RANKS: dict[str, int] = {
    "intern": 0, "trainee": 0, "apprentice": 0, "junior": 0, "jr": 0,
    "assistant": 0, "associate": 0, "entry": 0,
    # rank 1 == no modifier
    "senior": 2, "sr": 2, "snr": 2,
    "staff": 3, "lead": 3, "leader": 3,
    "principal": 4, "distinguished": 4, "master": 4,
    "head": 5, "director": 5, "chair": 5,
    "vp": 6, "vice": 6, "svp": 6, "evp": 6,
    "chief": 7, "president": 7, "ceo": 7, "cto": 7, "coo": 7, "cfo": 7,
    "cmo": 7, "cpo": 7, "cio": 7,
}
BASE_RANK = 1

# Words carrying no job-family meaning.
_STOPWORDS = {
    "of", "the", "and", "for", "a", "an", "to", "at", "in", "on", "&",
    "global", "regional", "national", "international", "group", "corporate",
    "deputy", "acting", "interim", "i", "ii", "iii", "iv", "v",
    "officer", "president", "vice", "chief", "executive",
}
_SPLIT = re.compile(r"[^a-z0-9]+")


def _tokens(title: str) -> list[str]:
    """Lower-cased alphanumeric tokens of a title."""
    return [t for t in _SPLIT.split(title.lower()) if t]


def seniority_rank(title: str | None) -> int | None:
    """Highest seniority modifier present in the title. None if untitled."""
    if not title or not title.strip():
        return None
    ranks = [MODIFIER_RANKS[t] for t in _tokens(title) if t in MODIFIER_RANKS]
    return max(ranks) if ranks else BASE_RANK


def family_tokens(title: str | None) -> frozenset[str]:
    """The job-family tokens: what is left after seniority modifiers and
    stopwords are removed. 'Senior Product Manager' -> {product, manager}."""
    if not title:
        return frozenset()
    return frozenset(t for t in _tokens(title)
                     if t not in MODIFIER_RANKS and t not in _STOPWORDS)


def same_family(a: str | None, b: str | None) -> bool:
    """Conservative: the family tokens must be identical, or one must be a
    non-empty subset of the other ('Software Engineer' vs 'Engineer'). Anything
    looser would start calling unrelated job changes promotions."""
    fa, fb = family_tokens(a), family_tokens(b)
    if not fa or not fb:
        return False
    return fa == fb or fa <= fb or fb <= fa


def title_progression(first_title: str | None, last_title: str | None) -> int | None:
    """Seniority steps from `first_title` to `last_title`, or None when the two
    roles are not comparable (different job families, or a missing title)."""
    if not same_family(first_title, last_title):
        return None
    a, b = seniority_rank(first_title), seniority_rank(last_title)
    if a is None or b is None:
        return None
    return b - a
