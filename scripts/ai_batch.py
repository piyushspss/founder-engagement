#!/usr/bin/env python3
"""Golden-set AI batch — RUNBOOK CP10.

Runs the frozen 50-case golden set twice: deterministic-only, and deterministic
plus the optional AI overlay. The comparison is the whole point — with the
no-finding MockAdapter the two runs must be IDENTICAL, which is what proves the
optional layer does not disturb the product it is optional to.

    python scripts/ai_batch.py                      # deterministic vs no-op mock
    python scripts/ai_batch.py --provider openai    # real run, if a key exists
    python scripts/ai_batch.py --provider anthropic # real run, if a key exists

The prompt is frozen (see docs/EVAL_DECISIONS.md → CP10 PROMPT FREEZE). This script
never writes to cases.yaml, profiles.json or any config: it is a measuring
instrument, like scripts/eval.py.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.assessment import assess                                # noqa: E402
from app.llm.mock import no_finding_adapter                      # noqa: E402
from app.llm.provider import make_adapter                        # noqa: E402
from app.llm.prompt import PROMPT_VERSION, prompt_sha256         # noqa: E402
from app.llm.service import run_ai_check                         # noqa: E402
from app.models.raw import RawProfile                            # noqa: E402
from app.normalize import load_config                            # noqa: E402
from app.normalize.normalizer import normalize_corpus            # noqa: E402
from app.policy import Attention                                 # noqa: E402

CFG = load_config()
CASES = ROOT / "data" / "golden" / "cases.yaml"
PROFILES = ROOT / "data" / "golden" / "profiles.json"
SURFACED = (Attention.PRIORITY_REVIEW.value, Attention.REVIEW.value)


def sha256(path: Path) -> str:
    """Hash a golden-set file, printed with every run to prove which cases ran."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_golden():
    """Load the frozen golden cases plus their profiles and companion records."""
    cases = yaml.safe_load(CASES.read_text())["cases"]
    entries = json.loads(PROFILES.read_text())
    raws, ids = [], []
    for entry in entries:
        raws.append(RawProfile.model_validate(entry["profile"]))
        ids.append(entry["case_id"])
        for companion in entry.get("companions", []):
            raws.append(RawProfile.model_validate(companion))
            ids.append(None)
    canon = normalize_corpus(raws, CFG)
    by_case = {cid: (raw, prof) for cid, raw, prof in zip(ids, raws, canon) if cid}
    return cases, by_case


def metrics(rows: list[dict]) -> dict:
    """Headline metrics for one run. `precision_informational` is exactly that —
    with no outcome labels it means "how many reasonable-low cases were
    escalated", not precision in any predictive sense."""
    must = [r for r in rows if r["group"] == "must_surface"]
    surfaced = [r for r in must if r["attention"] in SURFACED]
    queue = [r for r in rows if r["attention"] in SURFACED]
    return {
        "cases": len(rows),
        "must_surface": len(must),
        "recall": round(len(surfaced) / len(must), 4) if must else 0.0,
        "routine_leakage": sum(1 for r in must if r["attention"] == "ROUTINE"),
        "queue_rate": round(len(queue) / len(rows), 4) if rows else 0.0,
        "precision_informational": round(len(surfaced) / len(queue), 4) if queue else 0.0,
        "attention": dict(Counter(r["attention"] for r in rows)),
    }


def compare(cases, by_case, adapter) -> dict:
    """Run the golden set deterministically and with the overlay. One source of
    truth for the CP10 numbers: scripts/eval.py renders this into docs/EVAL_REPORT.md
    so the report cannot drift from the instrument."""
    deterministic_rows, overlay_rows = [], []
    escalations = Counter()
    accepted = discarded = unsupported = 0
    latencies: list[int] = []
    usage = Counter()

    started = time.perf_counter()
    for case in cases:
        cid = case["id"]
        if cid not in by_case:
            continue
        raw_profile, canonical = by_case[cid]
        assessment = assess(canonical, CFG).to_dict()
        group = case.get("group", "?")

        deterministic_rows.append({"case_id": cid, "group": group,
                                   "attention": assessment["attention"]})

        result = run_ai_check(cid, raw_profile.raw_dict(), canonical, assessment,
                              adapter, CFG)
        overlay_rows.append({"case_id": cid, "group": group,
                             "attention": result.attention_with_ai})
        accepted += len(result.ai_cues)
        discarded += len(result.discarded)
        unsupported += len(result.unsupported_inferences)
        if result.attention_changed:
            escalations[f"{result.deterministic_attention} -> "
                        f"{result.attention_with_ai}"] += 1
        if result.metadata:
            if result.metadata.latency_ms is not None:
                latencies.append(result.metadata.latency_ms)
            for key, value in (result.metadata.usage or {}).items():
                if isinstance(value, int):
                    usage[key] += value

    return {
        "deterministic_rows": deterministic_rows,
        "overlay_rows": overlay_rows,
        "det": metrics(deterministic_rows),
        "ovl": metrics(overlay_rows),
        "identical": deterministic_rows == overlay_rows,
        "accepted": accepted,
        "discarded": discarded,
        "unsupported": unsupported,
        "escalations": dict(escalations),
        "latencies": sorted(latencies),
        "usage": dict(usage),
        "wall": time.perf_counter() - started,
    }


def main() -> int:
    """Run the batch and, for the mock provider, enforce the NO-OP GATE.

    With the no-finding MockAdapter the two runs must be byte-identical per
    case; anything else means the optional layer disturbed the product it is
    optional to, and the script exits non-zero. A real provider is exploratory
    and is NOT part of the frozen evaluation — no prompt, weight or threshold
    may be tuned after seeing its output."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=("mock", "openai", "anthropic"),
                    default="mock")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    cases, by_case = load_golden()
    if args.limit:
        cases = cases[:args.limit]

    # The mock path uses the no-finding adapter explicitly: the CP10 no-op gate
    # depends on it finding nothing, not on whatever FOUNDER_AI_MOCK_FINDING says.
    adapter = (no_finding_adapter() if args.provider == "mock"
               else make_adapter(args.provider))

    print("=" * 78)
    print("CP10 GOLDEN-SET AI BATCH")
    print("=" * 78)
    print(f"  cases.yaml SHA-256    : {sha256(CASES)}")
    print(f"  profiles.json SHA-256 : {sha256(PROFILES)}")
    print(f"  rubric_version        : {CFG.version_hash()}")
    print(f"  prompt_version        : {PROMPT_VERSION}")
    print(f"  prompt_sha256         : {prompt_sha256()}")
    print(f"  provider requested    : {args.provider}")
    print(f"  provider available    : {adapter.available()}")
    if not adapter.available():
        print(f"  reason                : {getattr(adapter, 'last_error', 'n/a')}")
        if args.provider != "mock":
            print(f"\n  real-provider evaluation not run ({args.provider})")
            return 0

    cmp = compare(cases, by_case, adapter)
    deterministic_rows = cmp["deterministic_rows"]
    overlay_rows = cmp["overlay_rows"]
    escalations = Counter(cmp["escalations"])
    accepted, discarded, unsupported = cmp["accepted"], cmp["discarded"], cmp["unsupported"]
    latencies, usage, wall = cmp["latencies"], Counter(cmp["usage"]), cmp["wall"]

    det, ovl = cmp["det"], cmp["ovl"]
    print(f"\n{'metric':32} {'deterministic':>14} {'+ AI overlay':>14}")
    print("-" * 62)
    for key in ("cases", "must_surface", "recall", "routine_leakage", "queue_rate",
                "precision_informational"):
        print(f"  {key:30} {str(det[key]):>14} {str(ovl[key]):>14}")
    print(f"  {'attention distribution':30} {str(det['attention']):>14}")
    print(f"  {'':30} {str(ovl['attention']):>14}")

    identical = deterministic_rows == overlay_rows
    print(f"\n  every per-case attention identical : {'YES' if identical else 'NO'}")
    print(f"  accepted AI cues                   : {accepted}")
    print(f"  discarded evidence items           : {discarded}")
    print(f"  unsupported inferences             : {unsupported}")
    print("  attention escalations              : "
          f"{dict(escalations) if escalations else '0'}")
    for arrow in ("REVIEW -> PRIORITY_REVIEW", "ROUTINE -> REVIEW",
                  "ROUTINE -> PRIORITY_REVIEW"):
        print(f"    {arrow:34}: {escalations.get(arrow, 0)}")

    if det["recall"] == 1.0:
        print("\n  recall lift = 0 because the deterministic baseline is already "
              "saturated (1.000)")

    print(f"\n  batch wall time : {wall:.2f}s")
    if latencies:
        latencies.sort()
        print(f"  request latency : min {latencies[0]}ms  median "
              f"{latencies[len(latencies)//2]}ms  max {latencies[-1]}ms")
    if usage:
        print(f"  token usage     : {dict(usage)}")

    if args.provider == "mock":
        ok = (identical and det["recall"] == ovl["recall"]
              and det["queue_rate"] == ovl["queue_rate"])
        print(f"\n  NO-OP GATE: {'PASS' if ok else 'FAIL'} — the optional layer "
              f"{'does not' if ok else 'DOES'} disturb the deterministic product")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
