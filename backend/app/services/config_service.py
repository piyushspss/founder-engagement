"""Effective (runtime) configuration — RUNBOOK CP7 §2.

Two hard rules encoded here:

1. **The repository's frozen config files are never rewritten.** `GET/PUT
   /config` read and write a persisted *runtime* representation that is
   initialised from those files. The frozen defaults stay byte-identical, which
   is what lets CP6's default-model regression be re-run at any time.
2. **`PUT /config` does not rescore.** It changes what the next assessment will
   use and nothing else. `POST /rescore` is the explicit, auditable act.

Validation is shape-conformance against the frozen defaults: a submitted key
must exist in the default at the same path, and a submitted leaf must have the
default's type. That gives a typed schema for a config whose shape is itself
config, without hand-transcribing 200 keys into Pydantic models and letting the
two drift apart.
"""

from __future__ import annotations

import copy
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import RuntimeConfig, utcnow
from app.normalize.config import (SECTION_NAMES, Config, default_sections,
                                  rubric_hash)


class ConfigValidationError(ValueError):
    """Rejected config patch. Carries every field error; nothing was persisted."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


#: Paths whose dict keys are open-ended data rather than a fixed schema.
FREEFORM_MAPS = {("institutions", "aliases")}

#: Numeric leaves with a meaningful domain. Anything outside it is rejected
#: rather than silently producing an un-runnable rubric.
RANGES: dict[tuple[str, ...], tuple[float, float]] = {
    ("weights", "thresholds", "priority_broad"): (0, 100),
    ("weights", "thresholds", "routine_broad"): (0, 100),
    ("weights", "thresholds", "low_confidence_floor_broad"): (0, 100),
    ("weights", "thresholds", "priority_confidence"): (0.0, 1.0),
    ("weights", "confidence", "contradiction_penalty_cap"): (0.0, 1.0),
    ("weights", "confidence", "inference_penalty_cap"): (0.0, 1.0),
    ("weights", "fuzzy", "institution_min_score"): (0, 100),
    ("weights", "fuzzy", "company_min_score"): (0, 100),
}


# ---------------------------------------------------------------- validation
def _type_name(v: Any) -> str:
    """Type name for an error message."""
    return type(v).__name__


def _numeric(v: Any) -> bool:
    """True for int/float but NOT bool — bool is an int in Python and a boolean
    arriving where a weight belongs is a mistake, not a 0/1."""
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _validate_node(default: Any, given: Any, path: tuple[str, ...],
                   errors: list[str]) -> None:
    """Recursively check a patch node against the DEFAULT shape.

    The defaults are the schema: an unknown key, a changed type or a numeric
    outside `RANGES` is rejected rather than silently producing an un-runnable
    rubric. Errors accumulate so one request reports every problem."""
    dotted = ".".join(path)
    if isinstance(default, dict):
        if not isinstance(given, dict):
            errors.append(f"{dotted}: expected object, got {_type_name(given)}")
            return
        freeform = path in FREEFORM_MAPS
        for key, value in given.items():
            if not freeform and key not in default:
                errors.append(f"{dotted + '.' if dotted else ''}{key}: unknown field")
                continue
            _validate_node(default.get(key, value if freeform else None), value,
                           path + (str(key),), errors)
        return

    if isinstance(default, list):
        if not isinstance(given, list):
            errors.append(f"{dotted}: expected array, got {_type_name(given)}")
            return
        proto = default[0] if default else None
        for i, item in enumerate(given):
            if isinstance(proto, dict):
                if not isinstance(item, dict):
                    errors.append(f"{dotted}[{i}]: expected object")
                    continue
                allowed = {k for d in default if isinstance(d, dict) for k in d}
                for key in item:
                    if key not in allowed:
                        errors.append(f"{dotted}[{i}].{key}: unknown field")
            elif proto is not None and not isinstance(item, type(proto)):
                if not (_numeric(proto) and _numeric(item)):
                    errors.append(f"{dotted}[{i}]: expected {_type_name(proto)}, "
                                  f"got {_type_name(item)}")
        return

    # ---- leaf ----
    if isinstance(default, bool) or isinstance(given, bool):
        if not (isinstance(default, bool) and isinstance(given, bool)):
            errors.append(f"{dotted}: expected {_type_name(default)}, got {_type_name(given)}")
            return
    elif _numeric(default):
        if not _numeric(given):
            errors.append(f"{dotted}: expected number, got {_type_name(given)}")
            return
        lo, hi = RANGES.get(path, (None, None))
        if lo is not None and not (lo <= given <= hi):
            errors.append(f"{dotted}: {given} outside allowed range [{lo}, {hi}]")
    elif isinstance(default, str):
        if not isinstance(given, str):
            errors.append(f"{dotted}: expected string, got {_type_name(given)}")
    elif default is None:
        pass


def validate_patch(patch: dict[str, Any], base: dict[str, Any] | None = None) -> None:
    """Validate a (possibly partial) config payload against the frozen shape.

    Shape first, then cross-field sanity on the MERGED result — the merge base is
    the current effective config, because a partial patch is only meaningful
    against what it is being applied to."""
    errors: list[str] = []
    if not isinstance(patch, dict):
        raise ConfigValidationError(["config: expected an object"])
    if not patch:
        raise ConfigValidationError(["config: empty payload"])
    defaults = default_sections()
    for section, value in patch.items():
        if section not in SECTION_NAMES:
            errors.append(f"{section}: unknown config section "
                          f"(allowed: {', '.join(SECTION_NAMES)})")
            continue
        _validate_node(defaults[section], value, (section,), errors)

    if errors:                       # shape must hold before values can be compared
        raise ConfigValidationError(errors)

    merged = deep_merge(base or defaults, patch)
    th = merged["weights"]["thresholds"]
    if th["routine_broad"] > th["priority_broad"]:
        errors.append("weights.thresholds: routine_broad must not exceed priority_broad")
    for name, weight in merged["weights"]["signal_weights"].items():
        if not _numeric(weight) or weight < 0:
            errors.append(f"weights.signal_weights.{name}: must be a non-negative number")
    if errors:
        raise ConfigValidationError(errors)


def deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Dicts merge key-wise; lists and scalars are replaced wholesale (a tier
    list is a value, not an accumulator)."""
    out = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


# ---------------------------------------------------------------- persistence
def get_runtime_row(session: Session) -> RuntimeConfig:
    """The single persisted runtime-config row, created from the frozen
    defaults on first access. The files under `backend/config/` are the seed and
    are never rewritten."""
    row = session.execute(select(RuntimeConfig).where(RuntimeConfig.id == 1)).scalar_one_or_none()
    if row is None:
        sections = default_sections()
        row = RuntimeConfig(id=1, sections_json=sections, rubric_version=rubric_hash(sections),
                            updated_at=utcnow(), updated_by=None)
        session.add(row)
        session.flush()
    return row


def effective_sections(session: Session) -> dict[str, Any]:
    """A deep COPY of the effective sections — callers must not be able to
    mutate the persisted config by editing what they were handed."""
    return copy.deepcopy(get_runtime_row(session).sections_json)


def effective_config(session: Session) -> Config:
    """The Config object every assessment in this process must be built with."""
    return Config.from_sections(effective_sections(session))


def apply_patch(session: Session, patch: dict[str, Any], actor: str | None) -> RuntimeConfig:
    """Validate and persist a config patch. Does NOT rescore and does NOT touch
    human state.

    Objects deep-merge, lists are replaced wholesale. Changing config alters
    what the NEXT assessment uses; `POST /rescore` is the separate, explicit act
    that re-evaluates existing founders, which is why a founder can legitimately
    show a stored `rubric_version` that differs from the effective one."""
    row = get_runtime_row(session)
    validate_patch(patch, base=row.sections_json)
    merged = deep_merge(row.sections_json, patch)
    row.sections_json = merged
    row.rubric_version = rubric_hash(merged)
    row.updated_at = utcnow()
    row.updated_by = actor
    session.flush()
    return row


def reset_to_defaults(session: Session) -> RuntimeConfig:
    """Restore the frozen defaults. Like `apply_patch`, does not rescore."""
    row = get_runtime_row(session)
    sections = default_sections()
    row.sections_json = sections
    row.rubric_version = rubric_hash(sections)
    row.updated_at = utcnow()
    session.flush()
    return row
