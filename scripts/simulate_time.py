#!/usr/bin/env python3
"""Keep-warm resurfacing demo — RUNBOOK CP9.

Drives the running API with `?as_of=` to show a founder crossing their keep-warm
date, and proves the crossing writes nothing. Time simulation here is a READ-TIME
LENS: it changes what a person is shown and touches no row anywhere.

    python scripts/simulate_time.py                 # read-only demo
    python scripts/simulate_time.py --reengage      # ... then perform the human act

The script only ever mutates when a flag explicitly asks it to, and every
mutation it performs is an ordinary human endpoint call carrying actor + reason.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

API = "http://127.0.0.1:8000"
ACTOR = "piyush"


# ----------------------------------------------------------------- transport
def call(method: str, path: str, payload: dict | None = None) -> tuple[int, object]:
    """One HTTP call against the running API, returning (status, parsed body).

    An HTTP error is returned rather than raised, so the demo can show a
    rejected transition as a real 409 instead of crashing."""
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        API + path, data=data, method=method,
        headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read() or "null")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or "null")


def get(path: str) -> object:
    """GET, or exit — a failed read means the demo cannot be trusted."""
    status, body = call("GET", path)
    if status != 200:
        raise SystemExit(f"GET {path} -> {status}: {body}")
    return body


# ------------------------------------------------------ database fingerprint
def fingerprint() -> dict[str, str]:
    """Hash every row of every table `as_of` must not touch. Read straight from
    SQLite, not through the API, so the proof does not depend on the API telling
    the truth about itself."""
    from sqlalchemy import inspect, select

    from app.db.base import session_factory
    from app.db.models import AuditLog, Decision, Founder, Workflow

    out: dict[str, str] = {}
    session = session_factory()()
    try:
        for model in (Founder, Decision, Workflow, AuditLog):
            cols = [c.key for c in inspect(model).columns]
            rows = session.execute(select(model)).scalars().all()
            key = (lambda r: r.id) if hasattr(model, "id") else (lambda r: r.founder_id)
            blob = json.dumps(
                [{c: str(getattr(r, c)) for c in cols} for r in sorted(rows, key=key)],
                sort_keys=True)
            out[model.__tablename__] = hashlib.sha256(blob.encode()).hexdigest()
    finally:
        session.close()
    return out


# ----------------------------------------------------------------- reporting
def rule(title: str) -> None:
    """Print a section heading."""
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def show_founder(founder_id: str, as_of: date) -> dict:
    """Print one founder as of a simulated date.

    Prints workflow and machine state side by side to show they are separate:
    "attention Routine" alongside "Re-engagement due" is the intended reading,
    not a contradiction."""
    detail = get(f"/founders/{founder_id}?as_of={as_of.isoformat()}")
    wf = detail["workflow"]
    a = detail["assessment"]
    print(f"  stage={wf['stage']:10} keep_warm_until={wf['keep_warm_until']} "
          f"due={str(wf['due']):5} reasons={wf['workflow_reasons']}")
    print(f"  machine: attention={a['attention']:16} potential={a['potential']:8} "
          f"confidence={a['confidence']:.2f}  v{detail['assessment_metadata']['assessment_version']}")
    return detail


def due_set(as_of: date) -> list[str]:
    """Founder ids that are re-engagement due at `as_of` (UTC, inclusive)."""
    body = get(f"/queue?due=true&limit=1000&as_of={as_of.isoformat()}")
    return [r["founder_id"] for r in body["rows"]]


def dashboard(as_of: date, stuck_days: int) -> dict:
    """Dashboard as of a simulated date."""
    return get(f"/dashboard?as_of={as_of.isoformat()}&stuck_days={stuck_days}")


# ---------------------------------------------------------------------- main
def main() -> int:
    """Demonstrate keep-warm resurfacing across simulated dates.

    `?as_of=` is a pure READ-TIME LENS: the read-only phase hashes every table
    before and after to prove no row, stage, assessment or audit entry was
    written. `--reengage` then performs the HUMAN re-engage act explicitly.

    F-21: this script will not manufacture keep-warm state — it requires a
    founder a human already moved to KEEP_WARM, because moving one is a human
    act and a demo that faked it would be demonstrating a different product."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--founder", help="founder id already in KEEP_WARM; "
                                      "otherwise the first due-able one is used")
    ap.add_argument("--reengage", action="store_true",
                    help="perform the human Re-engage after the read-only demo")
    ap.add_argument("--stuck-days", type=int, default=14)
    args = ap.parse_args()

    # ---- find a KEEP_WARM founder -------------------------------------------
    founder_id = args.founder
    if not founder_id:
        rows = get("/queue?stage=KEEP_WARM&limit=1000")["rows"]
        if not rows:
            raise SystemExit("no founder is in KEEP_WARM — move one there first "
                             "(POST /founders/{id}/stage with months 3, 6 or 9)")
        founder_id = rows[0]["founder_id"]

    detail = get(f"/founders/{founder_id}")
    until = detail["workflow"]["keep_warm_until"]
    if until is None:
        raise SystemExit(f"{founder_id} is KEEP_WARM with no date — inconsistent state")
    until = date.fromisoformat(until)
    before_day, on_day, after_day = until - timedelta(days=1), until, until + timedelta(days=1)

    rule(f"FOUNDER {founder_id} — keep_warm_until = {until}")

    # ---- purity baseline -----------------------------------------------------
    baseline = fingerprint()
    print("  database fingerprint before any read:")
    for table, digest in baseline.items():
        print(f"    {table:12} {digest[:32]}…")

    # ---- read-time simulation ------------------------------------------------
    for label, as_of in (("DAY BEFORE", before_day), ("DUE DATE", on_day),
                         ("DAY AFTER", after_day)):
        rule(f"{label} — as_of = {as_of}")
        show_founder(founder_id, as_of)
        ids = due_set(as_of)
        board = dashboard(as_of, args.stuck_days)
        print(f"  queue?due=true            : {len(ids)} founder(s); "
              f"this founder included: {founder_id in ids}")
        print(f"  dashboard.re_engagement_due: {board['re_engagement_due']}")
        print(f"  dashboard.stuck            : {board['stuck']['count']} "
              f"({board['stuck']['comparison']}, N={board['stuck']['threshold_days']}, "
              f"excludes {', '.join(board['stuck']['excluded_stages'])})")

    # ---- purity proof --------------------------------------------------------
    rule("TIME-SIMULATION PURITY")
    after = fingerprint()
    for table in baseline:
        same = baseline[table] == after[table]
        print(f"  {table:12} unchanged after every as_of read: {'YES' if same else 'NO'}")
    if baseline != after:
        print("  FAILED: a read mutated the database")
        return 1
    print("  Nine read requests across three simulated dates wrote nothing.")

    # ---- invalid as_of -------------------------------------------------------
    rule("INVALID as_of IS REJECTED, NOT SILENTLY TREATED AS TODAY")
    for bad in ("yesterday", "2027-13-01", "2027-02-30", "01/02/2027"):
        status, body = call("GET", f"/queue?as_of={urllib.parse.quote(bad)}")
        detail_msg = (body or {}).get("detail")
        first = detail_msg[0]["msg"] if isinstance(detail_msg, list) else detail_msg
        print(f"  as_of={bad!r:14} -> HTTP {status}  {first}")

    # ---- the human act -------------------------------------------------------
    if args.reengage:
        rule("HUMAN RE-ENGAGE — the only step that writes anything")
        before_detail = get(f"/founders/{founder_id}")
        status, body = call("POST", f"/founders/{founder_id}/stage", {
            "stage": "NURTURING", "actor": ACTOR,
            "reason": "keep-warm date reached — re-engaging"})
        print(f"  POST /founders/{founder_id}/stage -> {status} {body}")
        after_detail = get(f"/founders/{founder_id}")

        print("\n  preserved across the re-engagement:")
        for label, path in (("disposition", ("current_decision", "disposition")),
                            ("decision reason", ("current_decision", "reason")),
                            ("owner", ("workflow", "owner")),
                            ("next_action", ("workflow", "next_action")),
                            ("notes", ("workflow", "notes")),
                            ("assessment_version", ("assessment_metadata",
                                                    "assessment_version")),
                            ("rubric_version", ("assessment_metadata", "rubric_version")),
                            ("assessed_at", ("assessment_metadata", "assessed_at"))):
            b = before_detail[path[0]][path[1]] if before_detail[path[0]] else None
            a = after_detail[path[0]][path[1]] if after_detail[path[0]] else None
            print(f"    {label:19} {'SAME' if a == b else 'CHANGED'}")
        same_assessment = (json.dumps(before_detail["assessment"], sort_keys=True)
                           == json.dumps(after_detail["assessment"], sort_keys=True))
        print(f"    {'machine assessment':19} {'SAME (value-identical)' if same_assessment else 'CHANGED'}")

        print("\n  changed (authorized workflow fields only):")
        print(f"    stage               {before_detail['workflow']['stage']} -> "
              f"{after_detail['workflow']['stage']}")
        print(f"    keep_warm_until     {before_detail['workflow']['keep_warm_until']} -> "
              f"{after_detail['workflow']['keep_warm_until']}")

        ids = due_set(after_day)
        print(f"\n  still due at {after_day}? {founder_id in ids}")

        rule("AUDIT SEQUENCE")
        for e in get(f"/audit/{founder_id}")["events"]:
            kind = "SYSTEM" if e["event"] == "RESCORE" else "HUMAN "
            print(f"  #{e['id']:<4} {kind} {e['actor']:7} {e['event']:9} {e['field']:16} "
                  f"{str(e['from'])[:20]:22} -> {str(e['to'])[:22]}")
        print("  (no audit event exists for time passing — only human acts are recorded)")

    return 0


if __name__ == "__main__":
    import urllib.parse  # noqa: E402  (used in the invalid-as_of section)
    raise SystemExit(main())
