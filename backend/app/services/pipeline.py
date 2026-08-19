"""Import and rescore — the two machine entry points that write founder rows.

Both run the same pipeline (raw → normalize → dedup → assess → persist) over the
WHOLE stored corpus, because duplicate detection is corpus-level: a newly
imported record can make an already-stored founder a probable duplicate, and a
founder's duplicate flags feed their confidence.

Both are transactional. A failure anywhere aborts the entire unit of work, so a
partially-rescored database cannot exist — and human state is never in the write
set to begin with.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Founder, utcnow
from app.models.raw import RawProfile
from app.normalize.config import Config
from app.services.assessment_service import (Evaluated, audit_rescore,
                                             create_founder, evaluate_corpus,
                                             load_all_founders,
                                             stable_person_id,
                                             write_assessment)

#: CSV columns whose cell is a JSON document rather than a scalar.
CSV_JSON_COLUMNS = ("experience", "education", "professional_emails_hashed")
CSV_INT_COLUMNS = ("total_experience_duration_months",)


class ImportError_(ValueError):
    """Rejected import payload. Carries every per-record error, not just the first,
    so one bad row does not hide the other nine."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors[:5]))


# ------------------------------------------------------------------- parsing
def parse_json(payload: Any) -> list[RawProfile]:
    """Parse a JSON import payload into validated RawProfiles.

    Accepts a bare array, or an object wrapping one under `profiles`/`records`,
    or a single profile object. Validation is all-or-nothing: any invalid record
    rejects the whole payload rather than silently importing the good ones."""
    if isinstance(payload, dict):
        payload = payload.get("profiles", payload.get("records", [payload]))
    if not isinstance(payload, list):
        raise ImportError_(["payload: expected a JSON array of profiles"])
    out, errors = [], []
    for i, item in enumerate(payload):
        try:
            out.append(RawProfile.model_validate(item))
        except Exception as exc:                       # pydantic ValidationError
            errors.append(f"record[{i}]: {exc}")
    if errors:
        raise ImportError_(errors)
    return out


def parse_csv(text: str) -> list[RawProfile]:
    """Flat CSV: one row per founder. Nested `experience` / `education` /
    `professional_emails_hashed` cells carry JSON. Empty cells are absent, never
    empty strings — absence must stay representable (A5)."""
    reader = csv.DictReader(io.StringIO(text))
    rows, errors = [], []
    for i, row in enumerate(reader):
        clean: dict[str, Any] = {}
        for key, value in row.items():
            if key is None or value is None or value.strip() == "":
                continue
            key = key.strip()
            if key in CSV_JSON_COLUMNS:
                try:
                    clean[key] = json.loads(value)
                except json.JSONDecodeError as exc:
                    errors.append(f"row[{i}].{key}: invalid JSON ({exc.msg})")
                    continue
            elif key in CSV_INT_COLUMNS:
                try:
                    clean[key] = int(float(value))
                except ValueError:
                    errors.append(f"row[{i}].{key}: expected a number, got {value!r}")
            else:
                clean[key] = value
        try:
            rows.append(RawProfile.model_validate(clean))
        except Exception as exc:
            errors.append(f"row[{i}]: {exc}")
    if errors:
        raise ImportError_(errors)
    return rows


# -------------------------------------------------------------------- report
@dataclass
class ImportReport:
    """What an import did. `refreshed_by_dedup` counts already-stored founders
    whose assessment moved because the NEW records changed their duplicate
    flags — corpus-level dedup means an import can legitimately alter founders
    that were not in the payload."""

    received: int = 0
    created: int = 0
    updated: int = 0
    refreshed_by_dedup: int = 0
    duplicate_links: list[dict[str, Any]] = field(default_factory=list)
    duplicate_counts: dict[str, int] = field(default_factory=dict)
    never_merge_pairs: list[dict[str, Any]] = field(default_factory=list)
    founder_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """JSON form. `auto_merged` is hard-coded 0: duplicates are FLAGGED for a
        human, never merged (A6b), and the field exists to say so explicitly."""
        return {
            "received": self.received, "created": self.created, "updated": self.updated,
            "refreshed_by_dedup": self.refreshed_by_dedup,
            "founder_ids": self.founder_ids,
            "duplicate_report": {
                "counts_by_relation": self.duplicate_counts,
                "links": self.duplicate_links,
                "never_merge_pairs": self.never_merge_pairs,
                "auto_merged": 0,
                "policy": "A6b — duplicates are FLAGGED, never merged. Conflicting "
                          "strong hashes are classified NEVER and are not duplicates.",
            },
        }


def _corpus(session: Session, incoming: list[RawProfile],
            incoming_ids: list[str]) -> tuple[list[RawProfile], list[str], dict[str, Founder]]:
    """Stored ∪ incoming, with incoming winning for ids present in both."""
    stored = {f.id: f for f in load_all_founders(session)}
    replaced = set(incoming_ids)
    raws: list[RawProfile] = []
    ids: list[str] = []
    for fid, founder in stored.items():
        if fid in replaced:
            continue
        raws.append(RawProfile.model_validate(founder.raw_json))
        ids.append(fid)
    raws.extend(incoming)
    ids.extend(incoming_ids)
    return raws, ids, stored


def import_profiles(session: Session, raws: list[RawProfile], cfg: Config, *,
                    source: str | None = None, funnel: str | None = None) -> ImportReport:
    """Normalize, dedup, assess and persist `raws` across the WHOLE stored corpus.

    Writes machine-owned columns only. An imported founder gets NO human
    decision and sits at the neutral `NEW` creation default, which is a
    starting point rather than a machine recommendation. Transactional with the
    caller's session."""
    report = ImportReport(received=len(raws))
    ids = [stable_person_id(r, i) for i, r in enumerate(raws)]

    # A duplicate mdm_person_id inside one payload is the SAME founder (A6b);
    # the last record wins and it counts as one import, not two.
    dedup_incoming: dict[str, RawProfile] = {}
    for pid, raw in zip(ids, raws):
        dedup_incoming[pid] = raw
    incoming_ids = list(dedup_incoming)
    incoming = [dedup_incoming[i] for i in incoming_ids]

    corpus_raws, corpus_ids, stored = _corpus(session, incoming, incoming_ids)
    evaluated = {ev.person_id: ev for ev in evaluate_corpus(corpus_raws, corpus_ids, cfg)}

    incoming_set = set(incoming_ids)
    for pid in incoming_ids:
        ev = evaluated[pid]
        founder = stored.get(pid)
        if founder is None:
            create_founder(session, ev, source=source, funnel=funnel)
            report.created += 1
        else:
            # Refresh machine state ONLY. decisions / workflow rows are not in
            # this statement's write set, at any depth.
            if source:
                founder.source = source
            if funnel:
                founder.funnel = funnel
            write_assessment(founder, ev, first=False)
            report.updated += 1
        report.founder_ids.append(pid)

    # A stored founder untouched by this payload can still have gained a
    # duplicate link because of it; that changes their machine assessment.
    for pid, founder in stored.items():
        if pid in incoming_set:
            continue
        ev = evaluated.get(pid)
        if ev is None:
            continue
        new_assessment = ev.assessment.to_dict()
        if (ev.duplicates != (founder.duplicate_flags or [])
                or new_assessment != founder.assessment_json):
            write_assessment(founder, ev, first=False)
            report.refreshed_by_dedup += 1

    _fill_duplicate_report(report, [evaluated[i] for i in incoming_ids])
    session.flush()
    return report


def _fill_duplicate_report(report: ImportReport, evaluated: list[Evaluated]) -> None:
    """Summarise duplicate links onto the report, calling out NEVER pairs.

    NEVER means conflicting strong identity hashes — the pair is reported as
    explicitly not-a-duplicate, which is a different claim from "unrelated"."""
    counts: dict[str, int] = {}
    for ev in evaluated:
        for link in ev.duplicates:
            counts[link["relation"]] = counts.get(link["relation"], 0) + 1
            entry = {"founder_id": ev.person_id, **link}
            report.duplicate_links.append(entry)
            if link["relation"] == "NEVER":
                report.never_merge_pairs.append(entry)
    report.duplicate_counts = counts


# ------------------------------------------------------------------- rescore
@dataclass
class RescoreReport:
    """What a rescore did. `human_state_touched` is hard-coded False in
    `to_dict()` because human state is not in the write set at all — the claim
    is structural, and `test_rescore_integrity.py` proves it independently.

    F-18: `changed_assessment` counts REWRITTEN records, not moved conclusions —
    a re-serialised identical assessment can still count."""

    founders: int = 0
    rubric_version: str = ""
    changed_assessment: int = 0
    canonical_changed: int = 0
    failures: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """JSON form for `POST /rescore`."""
        return {"founders_rescored": self.founders, "rubric_version": self.rubric_version,
                "assessments_changed": self.changed_assessment,
                "canonical_profiles_changed": self.canonical_changed,
                "human_state_touched": False, "failures": self.failures}


def rescore_all(session: Session, cfg: Config, *, actor: str = "system",
                reason: str | None = None) -> RescoreReport:
    """Re-run the whole pipeline from stored RAW under the effective config.

    Machine-owned data only: decision, stage, owner, next_action, notes and the
    audit history are neither read nor written here, so a rescore can change the
    MACHINE ASSESSMENT ONLY. Re-runs from stored RAW rather than from the stored
    canonical profile, because tier lists change NORMALIZATION and not merely
    scoring.

    If anything raises, the caller's transaction rolls back and nothing —
    machine or human — is left half-written; `assessment_version` therefore
    increments only on a fully successful rescore."""
    founders = load_all_founders(session)
    report = RescoreReport(founders=len(founders))
    if not founders:
        report.rubric_version = cfg.version_hash()
        return report

    raws = [RawProfile.model_validate(f.raw_json) for f in founders]
    ids = [f.id for f in founders]
    evaluated = {ev.person_id: ev for ev in evaluate_corpus(raws, ids, cfg)}

    for founder in founders:
        ev = evaluated[founder.id]
        before_rubric = founder.rubric_version
        before_assessment = founder.assessment_json
        before_canonical = founder.canonical_json
        new_assessment = ev.assessment.to_dict()
        new_canonical = ev.canonical.model_dump(mode="json")
        if new_assessment != before_assessment:
            report.changed_assessment += 1
        if new_canonical != before_canonical:
            report.canonical_changed += 1
        write_assessment(founder, ev, first=False)
        audit_rescore(session, founder, actor, before_rubric, founder.rubric_version, reason)

    report.rubric_version = cfg.version_hash()
    session.flush()
    return report


def machine_state_fingerprint(founder: Founder) -> dict[str, Any]:
    """Machine-owned fields only, for before/after purity comparisons in tests
    and scripts. Deliberately excludes every human-owned field."""
    return {"assessment_version": founder.assessment_version,
            "assessed_at": founder.assessed_at.isoformat(),
            "rubric_version": founder.rubric_version,
            "attention": founder.attention, "confidence": founder.confidence,
            "potential": founder.assessment_json.get("potential"),
            "data_state": founder.data_state}


def touch(founder: Founder) -> None:
    """Stamp `updated_at` in UTC."""
    founder.updated_at = utcnow()
