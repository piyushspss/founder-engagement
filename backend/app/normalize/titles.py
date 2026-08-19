"""Title classification — PLAN A8.

The single most important rule in the normalizer: **founder evidence comes only
from explicit founder titles.** CEO, President, Managing Director, Owner and
Partner are leadership evidence and nothing more. A title that merely hints at
founding ("Founding Member", "Founding Team") is POSSIBLE, never EXPLICIT, and
POSSIBLE is never scored as founder evidence (config `possible_credit: 0.0`).
"""

from __future__ import annotations

import re
from functools import lru_cache

from app.models.canonical import FounderTitleFlag

# "Founding <role>" where <role> is an actual company-leadership post reads as
# founding the company; "Founding Member"/"Founding Team" does not, on its own.
_POSSIBLE_PATTERNS = [
    r"(?i)\bfounding\s+(member|team|partner|advisor|contributor|employee)\b",
    r"(?i)\bco[- ]?founding\s+member\b",
]


@lru_cache(maxsize=4)
def _compiled(explicit: tuple[str, ...], leadership: tuple[str, ...]):
    """Compile and cache the title patterns. EXPLICIT founder patterns and
    LEADERSHIP patterns stay separate lists — that separation is what keeps a
    CEO title from ever being read as founder evidence (A8)."""
    return (
        [re.compile(p) for p in explicit],
        [re.compile(p) for p in leadership],
        [re.compile(p) for p in _POSSIBLE_PATTERNS],
    )


def classify_title(title: str | None, cfg) -> tuple[FounderTitleFlag, bool]:
    """Returns (founder_title_flag, is_leadership_title)."""
    if not title:
        return FounderTitleFlag.NONE, False

    explicit, leadership, possible = _compiled(
        tuple(cfg.titles["founder_explicit_patterns"]),
        tuple(cfg.titles["leadership_only_patterns"]),
    )

    is_leadership = any(p.search(title) for p in leadership)

    # Ambiguous phrasings are checked FIRST so that "Founding Member" cannot be
    # swallowed by the broad \bfounder\b / \bfounding\b patterns.
    if any(p.search(title) for p in possible):
        return FounderTitleFlag.POSSIBLE, is_leadership

    if any(p.search(title) for p in explicit):
        return FounderTitleFlag.EXPLICIT, is_leadership

    return FounderTitleFlag.NONE, is_leadership


_HEADLINE_FOUNDER = re.compile(r"(?i)\b(co[- ]?founder|founder|founding)\b")


def headline_suggests_founder(headline: str | None) -> bool:
    """A headline is self-reported and unverifiable against a company, so it can
    only ever raise POSSIBLE (A8), never EXPLICIT."""
    return bool(headline and _HEADLINE_FOUNDER.search(headline))
