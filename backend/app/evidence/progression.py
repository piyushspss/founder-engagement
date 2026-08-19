"""Canonical management-level progression — the SINGLE resolution used by both
the broad `career_trajectory` signal (§4.1) and the `exceptional_progression`
detector (§4.2).

This module exists because the two paths must never disagree about which way a
career went. Before CP4-R1 they each read the provider's `management_level`
independently, and the supplied PM record showed the cost: the broad signal
resolved `Product Manager → Senior Product Manager` as a same-family **+1
promotion**, while the exceptional detector was separately reading the provider
levels and seeing **-1**. Same person, same two rows, two different claims.

There are two distinct things here, and conflating them is the trap:

* **Ordering** — is level A above level B? That is `MANAGEMENT_ORDER`, derived
  from the leadership `level_scores` in config, which is where CP3 fixed the
  relative standing of every level (notably `Lead` 0.42 < `Manager` 0.45).
  Every "at least this senior" gate must use this.
* **Magnitude** — how many steps is it from A to B? That is `LEVEL_RANK`, a
  coarse ladder. It is a *coarsening* of the ordering above: it may tie two
  levels the ordering separates, but it never inverts them (proved by test).
  Only step-counting may use it.

The resolution rule itself is CP3's, unchanged and re-stated in one place: the
provider's levels are believed, EXCEPT that a provider-reported regression is
re-read against the role titles, because the provider taxonomy conflates IC
seniority with people management and so reports real same-family promotions as
regressions. An unresolvable conflict yields `steps = None` — no claim at all —
rather than a regression we are not entitled to assert.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.evidence.titles_seniority import title_progression

# Coarse step ladder — MAGNITUDE ONLY (see module docstring). Never use this to
# answer "is A more senior than B"; use `at_least` / MANAGEMENT_ORDER for that.
LEVEL_RANK = {"Training": 0, "Unpaid": 0, "Entry": 1, "Specialist": 2, "Senior": 3,
              "Lead": 4, "Manager": 4, "Head": 5, "Director": 5, "VP": 6,
              "Partner": 6, "Owner": 6, "C-Level": 7, "CXO": 7}

# How a resolved step was arrived at.
PROVIDER = "provider_levels"
TITLE_OVERRIDE = "title_override"        # provider said regression; titles say promotion
PROVIDER_CORROBORATED = "provider_corroborated"
UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class ResolvedProgression:
    """Progression between two roles, after the CP3 conflict rule.

    `steps is None` means the evidence conflicts and could not be resolved
    conservatively. That is NOT zero and NOT a regression — it is the absence of
    a claim, and every consumer must treat it that way."""

    steps: int | None
    provider_steps: int | None
    basis: str
    source_fields: tuple[str, ...]
    explanation: str

    @property
    def resolved(self) -> bool:
        """False when the ladder could not read both endpoints. Unresolved is the
        ABSENCE of a progression claim — never zero steps, never a regression."""
        return self.steps is not None


def management_order(cfg) -> dict[str, float]:
    """The canonical ORDERING of management levels: the leadership
    `level_scores` from config. One source, so scoring and archetype gates can
    never drift apart."""
    return cfg.weights["signal_params"]["leadership"]["level_scores"]


def at_least(level: str | None, floor: str, cfg) -> bool:
    """Is `level` at least as senior as `floor`, on the canonical ordering?
    An unknown level is not evidence of seniority, so it never satisfies a gate."""
    order = management_order(cfg)
    if not level or level not in order or floor not in order:
        return False
    return order[level] >= order[floor]


def _path(role, field_name: str) -> str:
    """Provenance path into the RAW record, using the pre-dedup raw index."""
    return f"experience[{role.raw_index}].{field_name}"


def resolve_progression(first, last) -> ResolvedProgression:
    """CP3's conflict rule, in one place. `first` and `last` are CanonicalRoles
    in chronological order; both must carry a level this ladder knows."""
    a, b = first.management_level, last.management_level
    if a not in LEVEL_RANK or b not in LEVEL_RANK:
        return ResolvedProgression(
            steps=None, provider_steps=None, basis=UNRESOLVED,
            source_fields=(_path(first, "management_level"), _path(last, "management_level")),
            explanation=(f"management_level {a!r} → {b!r} is not in the known taxonomy — "
                         f"progression not measurable."))

    provider_steps = LEVEL_RANK[b] - LEVEL_RANK[a]
    level_paths = (_path(first, "management_level"), _path(last, "management_level"))
    title_paths = (_path(first, "position_title"), _path(last, "position_title"))

    if provider_steps >= 0:
        return ResolvedProgression(
            steps=provider_steps, provider_steps=provider_steps, basis=PROVIDER,
            source_fields=level_paths,
            explanation=f"{a} → {b} ({provider_steps:+d} levels).")

    # Provider says the career went backwards. CP3: re-read against the titles,
    # and only for a same-family move.
    title_steps = title_progression(first.title, last.title)
    if title_steps is None:
        return ResolvedProgression(
            steps=None, provider_steps=provider_steps, basis=UNRESOLVED,
            source_fields=level_paths + title_paths,
            explanation=(f"Provider levels imply a regression ({a} → {b}, "
                         f"{provider_steps:+d}) but the roles ({first.title!r} → "
                         f"{last.title!r}) are not the same job family, so the conflict "
                         f"cannot be resolved conservatively. No progression asserted."))
    if title_steps > 0:
        return ResolvedProgression(
            steps=title_steps, provider_steps=provider_steps, basis=TITLE_OVERRIDE,
            source_fields=title_paths,
            explanation=(f"{first.title!r} → {last.title!r} ({title_steps:+d} seniority "
                         f"steps; provider management_level said {provider_steps:+d}, "
                         f"overridden as a same-family promotion)."))
    return ResolvedProgression(
        steps=provider_steps, provider_steps=provider_steps, basis=PROVIDER_CORROBORATED,
        source_fields=level_paths + title_paths,
        explanation=(f"{a} → {b} ({provider_steps:+d} levels), corroborated by the titles "
                     f"({first.title!r} → {last.title!r}, {title_steps:+d} seniority steps)."))
