#!/usr/bin/env python3
"""Probe: does removing data ever move a founder from REVIEW/PRIORITY_REVIEW to
ROUTINE? Reports both classes of ablation separately (CP5 requirement L)."""
from __future__ import annotations
import copy, json, sys
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.assessment import assess
from app.models.raw import RawProfile, load_profiles
from app.normalize import load_config, normalize
from app.policy import Attention

CFG = load_config()

# Fields that FEED the §4.3 decision-relevant coverage model (removing them
# lowers coverage -> lowers confidence).
COVERAGE_FIELDS = {"experience", "position_title", "date_from", "date_from_year",
                   "date_from_month", "is_current", "active_experience",
                   "company_industry", "education", "total_experience_duration_months",
                   "location_country", "location_city"}
# Fields that carry POSITIVE EVIDENCE ONLY (they move broad_score, but no
# coverage component reads them).
EVIDENCE_ONLY_FIELDS = {"management_level", "company_employees_count", "company_size_range",
                        "company_employees_count_change_yearly_percentage",
                        "duration_months", "date_to", "date_to_year", "department"}


def strip(raw: dict, field: str) -> dict:
    """Return `raw` with `field` blanked everywhere it appears (profile, roles,
    education). Never mutates the input."""
    d = copy.deepcopy(raw)
    if field in ("experience", "education"):
        d[field] = []
        return d
    if field in d:
        d[field] = None
    for key in ("experience", "education"):
        for row in d.get(key) or []:
            if field in row:
                row[field] = None
    return d


def a_of(raw):
    """Assess one raw dict end to end (normalize → assess)."""
    return assess(normalize(RawProfile.model_validate(raw), CFG), CFG)


def main(paths):
    """Report attention transitions under single-field ablation.

    The two field classes are tallied separately on purpose: coverage-feeding
    fields should lower confidence, evidence-only fields should lower the score
    without lowering confidence, and NEITHER may produce a REVIEW/PRIORITY →
    ROUTINE transition."""
    rows = []
    for path in paths:
        for prof in load_profiles(path):
            raw = prof.model_dump(mode="json", exclude_none=False)
            rows.append(raw)
    print(f"{len(rows)} profiles probed\n")
    tallies = Counter()
    violations = {"coverage": [], "evidence_only": []}
    for raw in rows:
        base = a_of(raw)
        if base.attention is Attention.ROUTINE:
            continue
        for field in sorted(COVERAGE_FIELDS | EVIDENCE_ONLY_FIELDS):
            after = a_of(strip(raw, field))
            cls = "coverage" if field in COVERAGE_FIELDS else "evidence_only"
            key = (cls, base.attention.value, after.attention.value)
            tallies[key] += 1
            if after.attention is Attention.ROUTINE:
                violations[cls].append(
                    dict(person=raw.get("mdm_person_id", "?")[:8], field=field,
                         before=f"{base.attention.value} broad={base.broad_score} "
                                f"conf={base.confidence} cov={base.confidence_breakdown.coverage}",
                         after=f"{after.attention.value} broad={after.broad_score} "
                               f"conf={after.confidence} cov={after.confidence_breakdown.coverage}"))
    print("transitions (class, before -> after): count")
    for k, v in sorted(tallies.items()):
        print(f"  {k}: {v}")
    for cls, v in violations.items():
        print(f"\n{cls}: {len(v)} ablation(s) landed on ROUTINE")
        for x in v[:12]:
            print(f"  {x['person']} strip {x['field']}\n     before {x['before']}\n     after  {x['after']}")


if __name__ == "__main__":
    main(sys.argv[1:] or ["data/raw/sample.json"])
