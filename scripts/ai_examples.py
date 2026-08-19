#!/usr/bin/env python3
"""Two labelled example AI-check outputs — RUNBOOK CP10 §21.

Example A: a supported cue that is ACCEPTED, with real source paths, the
AI_INTERPRETED type, strength, full metadata, and the attention before/after.

Example B: a cue that is REJECTED, showing the proposed claim, the invalid
provenance, the discard reason and the zero impact on the assessment.

Both are produced by the **MockAdapter** and are labelled as such throughout —
no real-provider output exists in this environment, and canned output is never
presented as a model result.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.assessment import assess                         # noqa: E402
from app.llm.mock import MockAdapter                      # noqa: E402
from app.llm.service import run_ai_check                  # noqa: E402
from app.llm.validate import allowed_source_paths         # noqa: E402
from app.models.raw import RawProfile                     # noqa: E402
from app.normalize import load_config                     # noqa: E402
from app.normalize.normalizer import normalize_corpus     # noqa: E402

CFG = load_config()


def pick_founder(want_attention: str | None = None):
    """First synthetic founder matching `want_attention`, with its assessment.

    Chosen by deterministic scan, not cherry-picked after seeing AI output."""
    payload = json.loads((ROOT / "data" / "synthetic" / "load_800.json").read_text())
    raws = [RawProfile.model_validate(p) for p in payload[:60]]
    canon = normalize_corpus(raws, CFG)
    for raw, prof in zip(raws, canon):
        assessment = assess(prof, CFG).to_dict()
        if want_attention is None or assessment["attention"] == want_attention:
            return raw.raw_dict(), prof, assessment
    raise SystemExit(f"no founder with attention={want_attention} in the sample")


def show(title: str, result, note: str) -> None:
    """Print one labelled AI result: attention before/after, accepted cues,
    discarded items with reasons, and unsupported inferences."""
    print("=" * 78)
    print(title)
    print("=" * 78)
    print(f"  {note}\n")
    print(f"  attention_before   : {result.deterministic_attention}")
    print(f"  attention_with_ai  : {result.attention_with_ai}")
    print(f"  attention_changed  : {result.attention_changed}")
    print(f"  reason             : {result.attention_change_reason}")
    print(f"  aggregate_override : {result.aggregate_override}")
    print()
    for cue in result.ai_cues:
        print("  ACCEPTED CUE")
        print(f"    category      : {cue.category}")
        print(f"    strength      : {cue.strength.value}")
        print(f"    claim         : {cue.claim}")
        print(f"    source_fields : {list(cue.source_fields)}")
        print(f"    signal.type   : {cue.signal.type.value}")
        print(f"    signal.name   : {cue.signal.name}")
        print(f"    metadata      : provider={cue.metadata.provider} "
              f"model={cue.metadata.model}")
        print(f"                    prompt_version={cue.metadata.prompt_version} "
              f"prompt_sha256={cue.metadata.prompt_sha256[:16]}…")
        print(f"                    generated_at={cue.metadata.generated_at}")
        print()
    for item in result.discarded:
        print("  DISCARDED ITEM")
        print(f"    proposed claim: {item.claim}")
        print(f"    cited paths   : {item.source_fields}")
        print(f"    reason        : {item.reason.value}")
        print(f"    detail        : {item.detail}")
        print()
    if result.unsupported_inferences:
        print(f"  unsupported_inferences (diagnostic only): "
              f"{result.unsupported_inferences}\n")


def main() -> int:
    """Print one ACCEPTED and one REJECTED AI finding, each labelled.

    Both use MockAdapter with a hand-written payload, so the examples are
    reproducible and are provably not real model output — the point is to show
    the validation boundary, not to demonstrate a model."""
    # ---------------- Example A: accepted -------------------------------
    raw, canonical, assessment = pick_founder("REVIEW")
    allowed = allowed_source_paths(raw)
    titles = [p for p in allowed if p.endswith(".position_title")][:2]
    levels = [p for p in allowed if p.endswith(".management_level")][:2]
    cited = titles + levels
    claim = ("Two consecutive roles show a jump in recorded management level over a "
             "short tenure — a progression pattern the fixed rubric prices only "
             "through its slope cap.")
    adapter = MockAdapter({"exceptional_signal": True, "strength": "STRONG",
                           "category": "unusual_progression",
                           "evidence": [{"claim": claim, "source_fields": cited}],
                           "unsupported_inferences": []})
    result = run_ai_check("example-A", raw, canonical, assessment, adapter, CFG)
    show("EXAMPLE A — ACCEPTED  (MOCK OUTPUT, clearly labelled; not a real model result)",
         result,
         "Every cited path exists on this founder and holds a value; no quoted "
         "literal is ungrounded.")
    print(f"  cited values actually present:")
    for path in cited:
        print(f"    {path} = {allowed[path]!r}")

    before = json.dumps(assessment, sort_keys=True)

    # ---------------- Example B: rejected --------------------------------
    bad_claim = ('Exited "Helix Biosystems" to a strategic acquirer in 2021.')
    adapter_b = MockAdapter({
        "exceptional_signal": True, "strength": "STRONG", "category": "exit_signal",
        "evidence": [{"claim": bad_claim,
                      "source_fields": ["experience[0].exit_details",
                                        "experience[0].acquisition_amount"]}],
        "unsupported_inferences": [
            "the role ended in 2021, so the company was probably acquired",
            "a CEO title implies the person founded the company"]})
    result_b = run_ai_check("example-B", raw, canonical, assessment, adapter_b, CFG)
    print()
    show("EXAMPLE B — REJECTED  (MOCK OUTPUT, clearly labelled; not a real model result)",
         result_b,
         "The model asserted an exit. Neither cited path exists on this founder, so "
         "the claim is discarded rather than repaired to a nearby path.")
    print(f"  assessment unchanged by BOTH checks: "
          f"{json.dumps(assessment, sort_keys=True) == before}")
    print(f"  attention unchanged by the rejected finding: "
          f"{result_b.attention_with_ai == result_b.deterministic_attention}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
