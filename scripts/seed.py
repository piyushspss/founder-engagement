#!/usr/bin/env python3
"""Seed the SQLite database from the assessed load population — RUNBOOK CP7 §14.

The seed runs the REAL pipeline (raw → normalize → dedup → assess → persist)
over `data/synthetic/load_800.json` rather than inserting the stored assessment
JSON. Two reasons:

* the stored assessments must be attributable to the *effective* rubric, and a
  blind insert would stamp them with a hash that never produced them;
* running the pipeline lets the seed CROSS-CHECK its output against the frozen
  `load_800_assessed.json` from CP5/CP6, which is a free regression test of the
  persistence path against the frozen machine model.

The seed creates NO human decisions and moves NO stage. Every founder lands in
the neutral `NEW` workflow state, which is a creation default, not a machine
recommendation.

`--intake-weeks` spreads `created_at` deterministically over the recent past so
the dashboard's weekly-intake series has something to show. These are SYNTHETIC
intake timestamps on a SYNTHETIC population; they are persisted (the dashboard
never fabricates), and real imports stamp real arrival times.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.db.base import init_db, session_scope                        # noqa: E402
from app.db.models import AuditLog, Decision, Founder, Workflow, utcnow  # noqa: E402
from app.models.raw import RawProfile                                 # noqa: E402
from app.services.config_service import effective_config              # noqa: E402
from app.services.pipeline import import_profiles                     # noqa: E402

RAW_PATH = ROOT / "data" / "synthetic" / "load_800.json"
ASSESSED_PATH = ROOT / "data" / "synthetic" / "load_800_assessed.json"
COMPARE_FIELDS = ("broad_score", "confidence", "potential", "attention", "data_state",
                  "recommended_action")


def spread_intake(session, weeks: int) -> None:
    """Deterministic pseudo-arrival dates, derived from the founder id."""
    now = utcnow()
    for founder in session.query(Founder).all():
        h = int(hashlib.sha256(founder.id.encode()).hexdigest()[:8], 16)
        founder.created_at = now - timedelta(days=h % (weeks * 7))
        if founder.workflow:
            founder.workflow.created_at = founder.created_at
            founder.workflow.stage_changed_at = founder.created_at


def main() -> int:
    """Build the demo SQLite database from the synthetic load population.

    Seeds MACHINE state only: every founder lands at the neutral `NEW` stage
    with no human decision, because manufacturing human workflow state would
    demonstrate something the product does not do."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(RAW_PATH))
    ap.add_argument("--reset", action="store_true", default=True)
    ap.add_argument("--keep", dest="reset", action="store_false",
                    help="append to an existing DB instead of rebuilding it")
    ap.add_argument("--intake-weeks", type=int, default=8,
                    help="spread synthetic created_at over N recent weeks (0 = all now)")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    init_db(drop=args.reset)
    payload = json.loads(Path(args.raw).read_text())
    if args.limit:
        payload = payload[:args.limit]
    raws = [RawProfile.model_validate(p) for p in payload]

    with session_scope() as session:
        cfg = effective_config(session)
        report = import_profiles(session, raws, cfg, source="seed:load_800",
                                 funnel="SYNTHETIC_LOAD")
        if args.intake_weeks:
            spread_intake(session, args.intake_weeks)

    with session_scope() as session:
        founders = session.query(Founder).all()
        versions = Counter(f.assessment_version for f in founders)
        rubrics = {f.rubric_version for f in founders}
        counts = {
            "founders": len(founders),
            "decisions": session.query(Decision).count(),
            "workflow": session.query(Workflow).count(),
            "audit": session.query(AuditLog).count(),
        }
        stages = Counter(f.workflow.stage for f in founders if f.workflow)
        assessed = {a["person_id"]: a for a in json.loads(ASSESSED_PATH.read_text())} \
            if ASSESSED_PATH.exists() else {}
        # The frozen CP5 artefact was produced with per-record normalize(), i.e.
        # WITHOUT corpus dedup, so founders that carry duplicate links legitimately
        # differ here (the duplicate flag is real evidence and moves confidence).
        # They are reported separately; the no-duplicate group must match exactly.
        mismatches, dup_deltas, compared = [], [], 0
        for f in founders:
            ref = assessed.get(f.id)
            if not ref:
                continue
            compared += 1
            for field in COMPARE_FIELDS:
                if f.assessment_json.get(field) != ref.get(field):
                    line = (f"{f.id}.{field}: db={f.assessment_json.get(field)} "
                            f"frozen={ref.get(field)}")
                    (dup_deltas if f.duplicate_flags else mismatches).append(line)

    print("=== SEED REPORT ===")
    print(f"raw file                     : {args.raw}")
    print(f"received / created / updated : {report.received} / {report.created} / "
          f"{report.updated}")
    for key, value in counts.items():
        print(f"{key:29}: {value}")
    print(f"assessment_version distrib.  : {dict(sorted(versions.items()))}")
    print(f"rubric_version distinct count: {len(rubrics)}  ({', '.join(sorted(rubrics))})")
    print(f"workflow stage distribution  : {dict(stages)}")
    print(f"duplicate links (by relation): {report.duplicate_counts}")
    print(f"never-merge pairs            : {len(report.never_merge_pairs)}")
    print(f"cross-check vs load_800_assessed.json on {list(COMPARE_FIELDS)}:")
    print(f"  compared: {compared} founders against the frozen file")
    print(f"  mismatches (no duplicate links, must be 0): {len(mismatches)}")
    print(f"  expected deltas (founders WITH duplicate links, absent from the "
          f"pre-dedup CP5 artefact): {len(dup_deltas)}")
    for m in mismatches[:10]:
        print(f"  MISMATCH {m}")
    for m in dup_deltas[:3]:
        print(f"  dedup-delta {m}")
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
