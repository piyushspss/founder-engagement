"""Provenance validation — the hard gate.

The model may not invent a source path, and it may not cite a path belonging to
someone else. Both are checked against a whitelist built from THIS founder's own
raw record, and a claim that fails is **discarded, never repaired**. Guessing
which path the model "meant" would turn a hallucination into evidence with a
plausible citation attached, which is worse than the hallucination.

A second, narrower check catches a claim that cites a real path but says
something the cited values do not contain: any literal the model puts in quotes
must actually appear in the values it cited. This is deliberately limited — a
validator can establish that a quoted literal is absent from the cited text; it
cannot establish that a paraphrase is true. Everything it can prove, it fails
closed on; everything it cannot, it leaves to the human reading the claim.
"""

from __future__ import annotations

import re
from typing import Any

from app.llm.types import (ALLOWED_CATEGORIES, ALLOWED_STRENGTHS, AICue,
                           AdapterMetadata, DiscardReason, DiscardedItem,
                           EvidenceItem, RawFinding, ai_signal)
from app.evidence.signal import Strength
from app.llm.prompt import WITHHELD_RAW_FIELDS

#: Literals inside single or double quotes are checked against the cited values.
_QUOTED = re.compile(r"[\"'“‘]([^\"'”’]{2,80})[\"'”’]")


def _is_empty(value: Any) -> bool:
    """A path holding this is not citable — an empty value grounds nothing."""
    return value is None or value == "" or value == [] or value == {}


def allowed_source_paths(raw: dict[str, Any]) -> dict[str, Any]:
    """Every citable path in this founder's raw record, mapped to its value.

    Only paths that EXIST and hold a non-empty value are citable: a path whose
    value is null is not evidence of anything, so citing it cannot ground a
    claim. Withheld identity fields are excluded — they were never sent, so the
    model has no business citing them."""
    out: dict[str, Any] = {}

    def walk(node: Any, path: str) -> None:
        """Depth-first walk building `path -> value` for non-empty leaves,
        skipping withheld identity fields and `_`-prefixed synthetic tags."""
        if isinstance(node, dict):
            for key, value in node.items():
                if key in WITHHELD_RAW_FIELDS or key.startswith("_"):
                    continue
                walk(value, f"{path}.{key}" if path else str(key))
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{path}[{i}]")
        elif not _is_empty(node):
            out[path] = node

    walk(raw, "")
    return out


def _values_text(paths: list[str], allowed: dict[str, Any]) -> str:
    """Lower-cased haystack of the cited values, for the quoted-literal check."""
    return " ‖ ".join(str(allowed[p]) for p in paths if p in allowed).lower()


def _grounding_failure(item: EvidenceItem, allowed: dict[str, Any]) -> str | None:
    """Quoted literals must appear in the cited values. Returns a reason string
    on failure, None when the check passes or cannot be applied."""
    haystack = _values_text(item.source_fields, allowed)
    for literal in _QUOTED.findall(item.claim):
        needle = literal.strip().lower()
        if needle and needle not in haystack:
            return (f"claim quotes {literal!r}, which does not appear in the value of "
                    f"any cited path")
    return None


def validate_finding(finding: RawFinding, allowed: dict[str, Any],
                     metadata: AdapterMetadata,
                     foreign_paths: dict[str, str] | None = None,
                     ) -> tuple[list[AICue], list[DiscardedItem]]:
    """Turn a raw model finding into accepted cues plus a discard report.

    `foreign_paths` maps a path that exists on ANOTHER founder to that founder's
    id, so a cross-profile citation is reported as such rather than as a generic
    unknown path — it is the more alarming failure and deserves its own name."""
    accepted: list[AICue] = []
    discarded: list[DiscardedItem] = []
    foreign_paths = foreign_paths or {}

    if finding.category not in ALLOWED_CATEGORIES:
        return [], [DiscardedItem(
            claim=f"category={finding.category}", source_fields=[],
            reason=DiscardReason.INVALID_CATEGORY,
            detail=f"category {finding.category!r} is not in the allowed vocabulary")]

    if finding.strength not in ALLOWED_STRENGTHS:
        return [], [DiscardedItem(
            claim=f"strength={finding.strength}", source_fields=[],
            reason=DiscardReason.INVALID_STRENGTH,
            detail=f"strength {finding.strength!r} is not one of {list(ALLOWED_STRENGTHS)}")]

    strength = Strength(finding.strength)

    for item in finding.evidence:
        bad: DiscardedItem | None = None
        for path in item.source_fields:
            if path in allowed:
                continue
            if path in foreign_paths:
                bad = DiscardedItem(
                    claim=item.claim, source_fields=list(item.source_fields),
                    reason=DiscardReason.FOREIGN_PROFILE_PATH,
                    detail=(f"{path!r} exists on founder {foreign_paths[path]}, not on "
                            f"this founder — cross-profile citation refused"))
                break
            bad = DiscardedItem(
                claim=item.claim, source_fields=list(item.source_fields),
                reason=DiscardReason.UNKNOWN_SOURCE_PATH,
                detail=(f"{path!r} does not exist on this founder, or holds no value; "
                        f"not repaired to a similar path"))
            break

        if bad is None:
            problem = _grounding_failure(item, allowed)
            if problem:
                bad = DiscardedItem(claim=item.claim,
                                    source_fields=list(item.source_fields),
                                    reason=DiscardReason.UNGROUNDED_LITERAL,
                                    detail=problem)

        if bad is not None:
            discarded.append(bad)
            continue

        accepted.append(AICue(
            category=finding.category, strength=strength, claim=item.claim,
            source_fields=tuple(item.source_fields),
            signal=ai_signal(finding.category, strength, item.claim,
                             tuple(item.source_fields)),
            metadata=metadata))

    # A finding that claimed an exceptional signal but grounded nothing is
    # reported as such — silence here would look like "the model found nothing".
    if finding.exceptional_signal and not accepted and not discarded:
        discarded.append(DiscardedItem(
            claim="(no evidence items supplied)", source_fields=[],
            reason=DiscardReason.NO_EVIDENCE_ITEMS,
            detail="exceptional_signal was true but the finding carried no evidence"))

    return accepted, discarded
