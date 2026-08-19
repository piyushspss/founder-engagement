"""Healthcare classification of an employer.

THREE-valued by design, and the third value carries real weight:

    YES     — recognised as healthcare by the configured taxonomy
    NO      — recognised as clearly non-healthcare by the configured taxonomy
    UNKNOWN — absent, or present but not recognised by the starter taxonomy

The `UNKNOWN` bucket exists because the taxonomy in
`config/tiers/health_companies.json` is an explicit MVP assumption, not
Redesign's list. Asserting "not healthcare" about an industry string we simply
do not know would claim a classification we did not make, and would then earn
full company/domain confidence coverage for a guess.

UNKNOWN yields **zero** healthcare evidence — identical to NO — and never
negative evidence. The difference between NO and UNKNOWN is entirely a
confidence question: NO means we classified it, UNKNOWN means we could not.
"""

from __future__ import annotations

from rapidfuzz import fuzz, process

from app.models.canonical import Ternary


def classify_health(industry: str | None, keywords: list[str] | None,
                    company_name: str | None, cfg) -> tuple[Ternary, str | None]:
    """Returns (health_flag, health_tier)."""
    health = cfg.health
    tier = _company_tier(company_name, health, cfg)
    if tier:  # a named tier-list health employer is health regardless of industry text
        return Ternary.YES, tier

    health_set = {i.lower() for i in health["health_industries"]}
    non_health_set = {i.lower() for i in health.get("non_health_industries", [])}
    kw = [k.lower() for k in health["health_keywords"]]

    if industry and industry.strip():
        text = industry.strip().lower()
        if text in health_set or any(k in text for k in kw):
            return Ternary.YES, None
        if text in non_health_set:
            return Ternary.NO, None
        # Present, but our starter taxonomy does not recognise it. That is an
        # unknown, not a "no".
        return Ternary.UNKNOWN, None

    # No industry recorded. Category keywords are a weaker but usable signal.
    for cat in keywords or []:
        if cat and (cat.lower() in health_set or any(k in cat.lower() for k in kw)):
            return Ternary.YES, None

    return Ternary.UNKNOWN, None


def _company_tier(company_name: str | None, health: dict, cfg) -> str | None:
    """Health-employer tier by exact then fuzzy match, or None if not listed.

    None means "not on our starter list", never "not a health company" — the
    caller treats it as neutral."""
    if not company_name:
        return None
    for tier in ("tier_1", "tier_2"):
        names = health[tier]
        if company_name in names:
            return tier
        hit = process.extractOne(company_name, names, scorer=fuzz.WRatio)
        if hit and hit[1] >= cfg.fuzzy["company_min_score"]:
            return tier
    return None
