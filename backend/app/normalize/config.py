"""Config loading. Weights, tier lists and archetypes are CONFIG, NOT CODE
(PLAN §1) — nothing in this package hard-codes a threshold or a tier.

CP7 addition: the *effective* config is addressable as four plain dicts
(`sections()`), and `rubric_hash()` is the deterministic SHA-256 of exactly
those four sections. Nothing else enters the hash — no timestamps, no file
mtimes, no DB row ids — so "same effective config → same hash" holds across
processes, and any change that can alter an assessment (normalization tier
lists included, not merely weights) changes it.
"""

from __future__ import annotations

import copy
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"

#: The four sections that together constitute the effective rubric. Ordered
#: deterministically; the hash is taken over this exact structure.
SECTION_NAMES = ("weights", "institutions", "health", "archetypes")


def rubric_hash(sections: dict[str, Any]) -> str:
    """Deterministic SHA-256 over the complete effective config.

    `sort_keys=True` makes dict key ordering irrelevant; list order is preserved
    because list order is semantic (precedence lists). Only the four rubric
    sections are hashed, so persistence metadata can never leak in."""
    blob = json.dumps({name: sections[name] for name in SECTION_NAMES},
                      sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class Config:
    """The effective rubric: weights, institution tiers, health taxonomy and
    archetype rules.

    Every threshold, weight and tier list the system uses is CONFIG, not code,
    and reaches the assessor through this object. `version_hash()` over the four
    sections becomes `rubric_version`, which is what lets an assessment be
    attributed to the exact rubric that produced it."""

    def __init__(self, weights: dict, institutions: dict, health: dict, archetypes: dict):
        self.weights = weights
        self.institutions = institutions
        self.health = health
        self.archetypes = archetypes

    # convenience accessors used across the package
    @property
    def titles(self) -> dict[str, Any]:
        """Title/seniority taxonomy, including the founder-title patterns (A8)."""
        return self.weights["titles"]

    @property
    def fuzzy(self) -> dict[str, Any]:
        """Fuzzy-matching score floors for institution and company matching."""
        return self.weights["fuzzy"]

    @property
    def thresholds(self) -> dict[str, Any]:
        """The safety-policy thresholds. Read by `apply_policy`; never written."""
        return self.weights["thresholds"]

    def sections(self) -> dict[str, Any]:
        """The effective config as plain JSON-able data (a copy — callers may
        not mutate the loaded config through this)."""
        return copy.deepcopy({
            "weights": self.weights,
            "institutions": self.institutions,
            "health": self.health,
            "archetypes": self.archetypes,
        })

    @classmethod
    def from_sections(cls, sections: dict[str, Any]) -> "Config":
        """Build from persisted runtime sections — the path used at request time
        so a saved config change reaches the next assessment."""
        return cls(weights=sections["weights"], institutions=sections["institutions"],
                   health=sections["health"], archetypes=sections["archetypes"])

    def version_hash(self) -> str:
        """Stable hash of the whole rubric — becomes `rubric_version` on an
        assessment so a rescore is provably attributable to a config change."""
        return rubric_hash(self.sections())


def _load(path: Path) -> dict:
    """Load a YAML or JSON config file by extension."""
    with open(path) as fh:
        return yaml.safe_load(fh) if path.suffix in (".yaml", ".yml") else json.load(fh)


@lru_cache(maxsize=8)
def load_config(config_dir: str | None = None) -> Config:
    """The FROZEN default config from `backend/config/`. Cached.

    These files are the seed for the runtime config and are never rewritten by
    the application; `PUT /config` persists a separate runtime row instead."""
    d = Path(config_dir) if config_dir else CONFIG_DIR
    return Config(
        weights=_load(d / "weights.yaml"),
        institutions=_load(d / "tiers" / "institutions.json"),
        health=_load(d / "tiers" / "health_companies.json"),
        archetypes=_load(d / "archetypes.yaml"),
    )


def default_sections(config_dir: str | None = None) -> dict[str, Any]:
    """A fresh, mutable copy of the frozen on-disk defaults. The runtime config
    is *initialised* from these; `PUT /config` never writes the files back."""
    return load_config(config_dir).sections()
