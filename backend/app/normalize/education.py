"""Degree-string normalization and institution tier matching.

Degrees arrive in a dozen spellings of the same credential ("BSN", "B.S.N.,
Nursing", "Bachelor of Science in Nursing"). Institutions arrive as aliases and
abbreviations ("MIT", "M.I.T.", "Massachusetts Inst. of Technology").

A7 governs the institution side: an institution that does not match the tier
lists is UNKNOWN, and UNKNOWN is neutral — never a penalty.
"""

from __future__ import annotations

import re

from rapidfuzz import fuzz, process

from app.models.canonical import (DegreeType, Flag, FlagCode, FlagKind,
                                  InstitutionTier)

# Order matters: the most specific credential must win. BSN before BS, doctoral
# before master's, "MD" only as a standalone token so "MDiv"/"Mdse" cannot match.
_DEGREE_PATTERNS: list[tuple[DegreeType, str]] = [
    (DegreeType.PhD, r"(?i)\b(ph\.?\s?d\.?|doctor\s+of\s+philosophy|doctorate)\b"),
    (DegreeType.MD, r"(?i)(\bm\.?\s?d\.?\b|doctor\s+of\s+medicine)"),
    (DegreeType.DO, r"(?i)(\bd\.?\s?o\.?\b|doctor\s+of\s+osteopathic)"),
    (DegreeType.MBA, r"(?i)(\bm\.?\s?b\.?\s?a\.?\b|master\s+of\s+business)"),
    (DegreeType.BSN, r"(?i)(\bb\.?\s?s\.?\s?n\.?\b|bachelor\s+of\s+science\s+in\s+nursing"
                     r"|bachelor'?s?\s+degree,?\s+nursing)"),
    (DegreeType.RN, r"(?i)(\br\.?\s?n\.?\b|registered\s+nurse)"),
    (DegreeType.MS, r"(?i)(\bm\.?\s?s\.?(c\.?)?\b|master\s+of\s+science|master'?s?\s+degree)"),
    (DegreeType.BA, r"(?i)(\bb\.?\s?a\.?\b|bachelor\s+of\s+arts)"),
    (DegreeType.BS, r"(?i)(\bb\.?\s?s\.?(c\.?)?\b|bachelor\s+of\s+science|bachelor'?s?\s*(degree)?)"),
]
_COMPILED = [(t, re.compile(p)) for t, p in _DEGREE_PATTERNS]


def classify_degree(degree: str | None, field_of_study: str | None = None) -> DegreeType:
    """Map a free-text degree string to a canonical type. Unrecognised -> OTHER,
    which is a neutral bucket, not a low one."""
    text = " ".join(x for x in (degree, field_of_study) if x)
    if not text.strip():
        return DegreeType.OTHER
    for dtype, pattern in _COMPILED:
        if pattern.search(text):
            # "Bachelor's degree, Nursing" is a BSN, not a generic BS.
            if dtype in (DegreeType.BS, DegreeType.BA) and re.search(r"(?i)nursing", text):
                return DegreeType.BSN
            return dtype
    return DegreeType.OTHER


def _normalise_name(name: str) -> str:
    """Punctuation/abbreviation clean-up before matching ("Univ." → "university")."""
    n = re.sub(r"[.’']", "", name)
    n = re.sub(r"(?i)\b(univ)\b\.?", "university", n)
    n = re.sub(r"(?i)\binst\b\.?", "institute", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def match_institution(name: str | None, cfg) -> tuple[str | None, InstitutionTier, float | None, list[Flag]]:
    """Returns (canonical_name, tier, score, flags).

    Exact and alias matches are exact facts. A fuzzy match is a judgment, so it
    carries FUZZY_INSTITUTION_MATCH and costs confidence downstream. A score
    below the configured floor resolves to UNKNOWN — deliberately neutral (A7),
    never negative.
    """
    flags: list[Flag] = []
    if not name or not name.strip():
        return None, InstitutionTier.UNKNOWN, None, flags

    inst = cfg.institutions
    tier1, tier2 = inst["tier_1"], inst["tier_2"]
    aliases: dict[str, str] = inst.get("aliases", {})

    def tier_of(canonical: str) -> InstitutionTier:
        """Tier for a canonical name; absent from both lists is UNKNOWN, which
        is neutral (A7) and not a judgment about the institution."""
        if canonical in tier1:
            return InstitutionTier.TIER_1
        if canonical in tier2:
            return InstitutionTier.TIER_2
        return InstitutionTier.UNKNOWN

    if name in aliases:
        canonical = aliases[name]
        return canonical, tier_of(canonical), 100.0, flags
    if name in tier1 or name in tier2:
        return name, tier_of(name), 100.0, flags

    norm = _normalise_name(name)
    candidates: dict[str, str] = {}
    for canonical in tier1 + tier2:
        candidates[_normalise_name(canonical)] = canonical
    for alias, canonical in aliases.items():
        candidates[_normalise_name(alias)] = canonical

    hit = process.extractOne(norm, list(candidates), scorer=fuzz.WRatio)
    if not hit:
        return None, InstitutionTier.UNKNOWN, None, flags

    matched_norm, score, _ = hit
    floor = cfg.fuzzy["institution_min_score"]
    if score < floor:
        # Unknown institution. NOT a penalty — see A7.
        return None, InstitutionTier.UNKNOWN, float(score), flags

    canonical = candidates[matched_norm]
    flags.append(Flag(
        code=FlagCode.FUZZY_INSTITUTION_MATCH,
        kind=FlagKind.INFERENCE,
        detail=f"'{name}' resolved to '{canonical}' by fuzzy match (score {score:.0f})",
        source_fields=("institution_name",),
        value=round(float(score), 1),
    ))
    return canonical, tier_of(canonical), float(score), flags
