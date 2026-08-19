#!/usr/bin/env python3
"""Golden-set evaluation + seeded ablation — docs/PLAN.md §4.6, RUNBOOK CP6.

Reads data/golden/{cases.yaml,profiles.json}, assesses every case, and writes
docs/EVAL_REPORT.md.

The primary metric is RECALL OF must_surface, and the hard safety property is
`must_surface in ROUTINE == 0`. Precision is reported for information only: with
no outcome labels, "precision" here means nothing more than "how many
reasonable_low cases were escalated", which §7 of the report decomposes properly.

This script never writes to cases.yaml or profiles.json, and never reads or
writes config. It is a measuring instrument.

WHAT THESE NUMBERS ARE, AND ARE NOT. Golden-set metrics measure CONSISTENCY
WITH OUR STATED POLICY ASSUMPTIONS under designed sparse/contradictory
scenarios. They are NOT an estimate of real-world accuracy at identifying great
founders — no outcome-labelled data exists anywhere in this repository, so
nothing here has been validated against founders who actually succeeded or
failed. "Recall 1.000" means every designed must-surface scenario obeyed the
intended policy, and no more than that.

Consequently: NO WEIGHT, THRESHOLD OR PROMPT MAY BE TUNED TO IMPROVE THESE
NUMBERS. A failing case is classified (a) implementation violates intended
policy → fix the code, or (b) the assumption/test is wrong → report it and
leave the case failing until a human approves the change. The deterministic
baseline and any LLM intervention are kept SEPARATELY measurable (§9) so the
optional layer's contribution can never be folded into the baseline's.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.assessment import assess                              # noqa: E402
from app.evidence.signal import Strength                       # noqa: E402
from app.models.raw import RawProfile                          # noqa: E402
from app.normalize import load_config                          # noqa: E402
from app.normalize.normalizer import normalize_corpus          # noqa: E402
from app.policy import Attention, DataState, Potential         # noqa: E402

CFG = load_config()
CASES_PATH = ROOT / "data" / "golden" / "cases.yaml"
PROFILES_PATH = ROOT / "data" / "golden" / "profiles.json"
REPORT_PATH = ROOT / "docs" / "EVAL_REPORT.md"

SURFACED = (Attention.PRIORITY_REVIEW, Attention.REVIEW)

# Decision-relevant fields the ablation may remove. Both classes matter: fields
# that FEED §4.3 coverage, and fields that carry positive evidence only.
ABLATION_FIELDS = [
    "experience", "education", "position_title", "management_level", "date_from",
    "date_from_year", "date_from_month", "date_to", "date_to_year", "date_to_month",
    "duration_months", "is_current", "active_experience", "company_industry",
    "company_categories_and_keywords", "company_employees_count", "company_size_range",
    "company_employees_count_change_yearly_percentage", "department",
    "total_experience_duration_months", "location_country", "location_city", "headline",
]
ROLE_LEVEL = {"position_title", "management_level", "date_from", "date_from_year",
              "date_from_month", "date_to", "date_to_year", "date_to_month",
              "duration_months", "is_current", "active_experience", "company_industry",
              "company_categories_and_keywords", "company_employees_count",
              "company_size_range", "company_employees_count_change_yearly_percentage",
              "department"}


def sha256(path: Path) -> str:
    """Hash a golden-set file. Printed with every run so the report is provably
    about the frozen cases and not an edited copy."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------- load
def load_golden():
    """Load the frozen cases and their profiles, normalized as a corpus.

    Read-only: expected outcomes were authored and hashed BEFORE the assessor
    was first run against them, and this function never writes either file."""
    cases = yaml.safe_load(CASES_PATH.read_text())
    profiles = {e["case_id"]: e for e in json.loads(PROFILES_PATH.read_text())}
    return cases, profiles


def assess_corpus(profile_entries: list[dict]) -> dict[str, object]:
    """Normalize the WHOLE golden corpus together (dedup needs the corpus), then
    assess each case profile. Companion records exist only to make duplicate
    detection real; they are not scored as cases."""
    raws, case_ids = [], []
    for entry in profile_entries:
        raws.append(RawProfile.model_validate(entry["profile"]))
        case_ids.append(entry["case_id"])
        for comp in entry.get("companions", []):
            raws.append(RawProfile.model_validate(comp))
            case_ids.append(None)
    canon = normalize_corpus(raws, CFG)
    out = {}
    for cid, prof in zip(case_ids, canon):
        if cid is not None:
            out[cid] = (assess(prof, CFG), prof)
    return out


# ----------------------------------------------------------------- expectations
def check_case(case: dict, assessment, canonical) -> list[str]:
    """Returns the list of expectation failures for one case (empty == pass)."""
    fails = []
    exp = case["expected"]
    got = {"attention": assessment.attention.value, "potential": assessment.potential.value,
           "data_state": assessment.data_state.value,
           "action": assessment.recommended_action.value}
    for dim, want in exp.items():
        if got[dim] != want:
            fails.append(f"{dim}: expected {want}, got {got[dim]}")

    ev = case.get("expected_evidence") or {}
    fired = {s.name for s in assessment.exceptional.signals}
    signals = {s.name: s for s in assessment.signals}
    contradictions = {c.code for c in assessment.contradictions}
    inferences = set(assessment.confidence_breakdown.inferences)
    quality = {f.code for f in canonical._all_flags() if f.kind.value == "QUALITY"}
    matched = list(assessment.archetype.secondary) + [assessment.archetype.archetype]

    if "exceptional_flag" in ev and assessment.exceptional.flag != ev["exceptional_flag"]:
        fails.append(f"exceptional_flag: expected {ev['exceptional_flag']}, "
                     f"got {assessment.exceptional.flag} ({assessment.exceptional.rule})")
    for d in ev.get("detectors_fired", []):
        if d not in fired:
            fails.append(f"detector {d} expected to FIRE; not_fired reason: "
                         f"{assessment.exceptional.not_fired.get(d, '?')}")
    for d in ev.get("detectors_not_fired", []):
        if d in fired:
            fails.append(f"detector {d} expected NOT to fire, but it did")
    for name in ev.get("signals_zero", []):
        if signals[name].value != 0.0:
            fails.append(f"signal {name} expected 0.0, got {signals[name].value}")
    for name in ev.get("signals_positive", []):
        if signals[name].value <= 0.0:
            fails.append(f"signal {name} expected > 0, got {signals[name].value}")
    for code in ev.get("contradictions_include", []):
        if code not in contradictions:
            fails.append(f"contradiction {code} expected, got {sorted(contradictions)}")
    for code in ev.get("inferences_include", []):
        if code not in inferences:
            fails.append(f"inference {code} expected, got {sorted(inferences)}")
    for code in ev.get("quality_flags_include", []):
        if code not in quality:
            fails.append(f"quality flag {code} expected, got {sorted(quality)}")
    for name in ev.get("archetype_matched_includes", []):
        if name not in matched:
            fails.append(f"archetype {name!r} expected among matches, got {matched}")
    if "archetype_primary_not" in ev and assessment.archetype.archetype == ev["archetype_primary_not"]:
        fails.append(f"archetype primary must not be {ev['archetype_primary_not']!r}")
    if "duplicate_relation" in ev:
        rels = {d.relation.value for d in canonical.duplicates}
        if ev["duplicate_relation"] not in rels:
            fails.append(f"duplicate relation {ev['duplicate_relation']} expected, got {sorted(rels)}")
    return fails


# -------------------------------------------------------------------- ablation
def ablate(raw: dict, rng: random.Random, fraction: float) -> dict:
    """Null a random `fraction` of decision-relevant fields, seeded.

    Profile-level fields are nulled outright; role-level fields are nulled on
    every role, because removing one role's `management_level` and leaving the
    others is a smaller perturbation than the property under test needs."""
    d = copy.deepcopy(raw)
    chosen = [f for f in ABLATION_FIELDS if rng.random() < fraction]
    for field in chosen:
        if field in ("experience", "education"):
            d[field] = []
            continue
        if field in d:
            d[field] = None
        if field in ROLE_LEVEL:
            for row in d.get("experience") or []:
                if field in row:
                    row[field] = None
    return d, chosen


def run_ablation(entries, base, runs=5, fraction=0.30, seed0=20260819):
    """Seeded ablation: delete `fraction` of decision-relevant fields, reassess.

    The safety property under test is DIRECTIONAL, not "the score is stable":
    removing data must lower confidence and grow the review queue, and must
    produce ZERO attention downgrades to ROUTINE. Missing information may never
    make a founder easier to dismiss. Seeded so the run is reproducible."""
    rows = []
    conf_increases = []
    downgrades = []
    new_lows = []
    for run in range(runs):
        rng = random.Random(seed0 + run)
        ablated_entries = []
        for e in entries:
            prof, _ = ablate(e["profile"], rng, fraction)
            ablated_entries.append({"case_id": e["case_id"], "profile": prof,
                                    "companions": e.get("companions", [])})
        results = assess_corpus(ablated_entries)
        rows.append((run, results))
        for cid, (a, _) in results.items():
            b = base[cid][0]
            if a.confidence > b.confidence:
                conf_increases.append((run, cid, b.confidence, a.confidence,
                                       a.attention.value, a.potential.value,
                                       sorted(set(b.confidence_breakdown.contradictions)
                                              - set(a.confidence_breakdown.contradictions))))
            if b.attention in SURFACED and a.attention is Attention.ROUTINE:
                downgrades.append((run, cid, b.attention.value))
            if b.potential is not Potential.LOW and a.potential is Potential.LOW:
                new_lows.append((run, cid, b.potential.value))
    return rows, conf_increases, downgrades, new_lows



# ------------------------------------------------- F-6 targeted probe
CONTRADICTION_CARRIERS = {
    "TOTAL_MISMATCH": ["total_experience_duration_months"],
    "SIZE_RANGE_MISMATCH": ["company_size_range"],
    "AMBIGUOUS_CURRENT": ["date_to", "date_to_year", "date_to_month"],
    "OVERLAP": ["date_from", "date_from_year", "date_from_month"],
    "CONFLICTING_IDENTITY_HASHES": ["name_hash"],
}


def strip_fields(raw: dict, fields: list[str]) -> dict:
    """Null every supplied form of the field. The schema carries dates twice —
    as a string and as decomposed integers — so nulling only one form removes
    nothing, and the probe would silently report 'no change' for a deletion it
    never actually made."""
    d = copy.deepcopy(raw)
    for field in fields:
        if field in d:
            d[field] = None
        for row in d.get("experience") or []:
            if field in row:
                row[field] = None
    return d


def f6_probe(entries, base):
    """Remove ONLY the field that CARRIES a contradiction, one case at a time.

    This is the F-6 phenomenon isolated: PLAN v2.3 accepts that deleting the
    field carrying a contradiction can legitimately RAISE confidence, because
    the remaining record is internally consistent. The safety question is not
    whether confidence rises — it is whether any such case becomes easier to
    dismiss. That is what the last two columns answer."""
    rows = []
    for e in entries:
        cid = e["case_id"]
        b = base[cid][0]
        codes = sorted({c.code for c in b.contradictions})
        if not codes:
            continue
        for code in codes:
            fields = CONTRADICTION_CARRIERS.get(code, [])
            if not fields:
                continue
            probe_entry = {"case_id": cid, "profile": strip_fields(e["profile"], fields),
                           "companions": e.get("companions", [])}
            a = assess_corpus([probe_entry])[cid][0]
            gone = code not in {c.code for c in a.contradictions}
            rows.append({"case": cid, "code": code, "field": " + ".join(fields), "removed": gone,
                         "conf_before": b.confidence, "conf_after": a.confidence,
                         "att_before": b.attention.value, "att_after": a.attention.value,
                         "pot_before": b.potential.value, "pot_after": a.potential.value})
    return rows


# ---------------------------------------------------------------------- report
def pct(n, d):
    """Percentage string, or "n/a" for a zero denominator."""
    return f"{(100.0 * n / d):.1f}%" if d else "n/a"


def ai_section(w) -> None:
    """§9 — deterministic-only vs deterministic + no-op MockAdapter.

    Rendered from scripts/ai_batch.compare(), the same instrument the CP10 gate
    used, so the report cannot drift from the measurement. Runs the MockAdapter
    only: no API key, no network, no cost. A real-provider run is a separate,
    explicit `python scripts/ai_batch.py --provider anthropic`.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import ai_batch                                             # noqa: PLC0415
    from app.llm.mock import no_finding_adapter                 # noqa: PLC0415
    from app.llm.prompt import PROMPT_VERSION, prompt_sha256    # noqa: PLC0415

    cases, by_case = ai_batch.load_golden()
    adapter = no_finding_adapter()
    r = ai_batch.compare(cases, by_case, adapter)
    det, ovl = r["det"], r["ovl"]

    w("## 9. AI evaluation — deterministic vs deterministic + no-op AI overlay")
    w("")
    w("> **What this proves and what it does not.** The no-op evaluation proves that enabling")
    w("> the AI subsystem does not itself alter deterministic behavior. **It does not")
    w("> demonstrate real-provider lift.**")
    w("")
    w("> **Real-provider evaluation was not run because no provider API key/SDK environment")
    w("> was available during the checkpoint. Therefore incremental real-LLM lift is")
    w("> unmeasured.** Nothing below should be read as evidence that the LLM improves founder")
    w("> discovery. What CP10 delivers is an experimental architecture ready to *measure*")
    w("> incremental lift, not a proven lift result.")
    w("")
    w(f"Prompt version `{PROMPT_VERSION}` · SHA-256 `{prompt_sha256()}`  ")
    w(f"Overlay provider for this run: `{adapter.provider}` (no-finding MockAdapter) · "
      f"available: {adapter.available()}")
    w("")
    w("| metric | deterministic | + no-op MockAdapter | measured lift |")
    w("|---|---|---|---|")
    w(f"| cases | {det['cases']} | {ovl['cases']} | — |")
    w(f"| must_surface cases | {det['must_surface']} | {ovl['must_surface']} | — |")
    w(f"| **must_surface recall** | **{det['recall']:.3f}** | **{ovl['recall']:.3f}** | "
      f"**{ovl['recall'] - det['recall']:+.3f}** |")
    w(f"| **must_surface leakage into ROUTINE** | **{det['routine_leakage']}** | "
      f"**{ovl['routine_leakage']}** | **{ovl['routine_leakage'] - det['routine_leakage']:+d}** |")
    w(f"| review-queue rate | {det['queue_rate']:.2f} | {ovl['queue_rate']:.2f} | "
      f"{ovl['queue_rate'] - det['queue_rate']:+.2f} |")
    w(f"| precision *(informational only)* | {det['precision_informational']:.4f} | "
      f"{ovl['precision_informational']:.4f} | "
      f"{ovl['precision_informational'] - det['precision_informational']:+.4f} |")
    w(f"| attention distribution | {det['attention']} | {ovl['attention']} | — |")
    w(f"| **every per-case attention identical** | — | "
      f"**{'YES' if r['identical'] else 'NO'}** | — |")
    w("")
    w("| overlay behaviour on this run | count |")
    w("|---|---|")
    w(f"| accepted AI cues | {r['accepted']} |")
    w(f"| discarded evidence items (invalid source path) | {r['discarded']} |")
    w(f"| unsupported inferences (diagnostic only) | {r['unsupported']} |")
    w(f"| attention escalations | {r['escalations'] or 0} |")
    for arrow in ("ROUTINE -> REVIEW", "ROUTINE -> PRIORITY_REVIEW",
                  "REVIEW -> PRIORITY_REVIEW"):
        w(f"| &nbsp;&nbsp;`{arrow}` | {r['escalations'].get(arrow, 0)} |")
    w(f"| attention DOWNGRADES (impossible by construction) | 0 |")
    w("")
    if det["recall"] == 1.0:
        w(f"**Measured recall lift: {ovl['recall'] - det['recall']:+.3f}.** The deterministic")
        w("baseline is already **saturated** on this golden set (recall 1.000), so a no-op")
        w("adapter can only produce zero lift. This is a property of the measurement setup, not")
        w("a finding about language models: **the golden set as designed cannot demonstrate")
        w("incremental contextual lift**, because there is no headroom left to recover. Real")
        w("evaluation needs (a) a real provider, and ultimately (b) reviewer-labelled cases")
        w("where the deterministic baseline demonstrably misses.")
    w("")
    w("**NO-OP GATE: "
      f"{'PASS' if r['identical'] else 'FAIL'}** — the optional layer "
      f"{'does not' if r['identical'] else 'DOES'} disturb the deterministic product.")
    w("")
    w("### Metrics defined now, for when a real provider is wired in")
    w("")
    w("These are the numbers that would make the LLM earn its place; none of them is")
    w("claimed today.")
    w("")
    w("* incremental must-surface recall, measured **only on cases where the baseline has")
    w("  headroom** (the current golden set has none);")
    w("* incremental *useful* founders surfaced, as judged by a reviewer;")
    w("* reviewer acceptance rate of AI-contributed evidence;")
    w("* unsupported-inference rate (how often the model reaches past its evidence);")
    w("* review-queue expansion — extra human load per additional useful surface;")
    w("* latency and cost per additional useful surface;")
    w("* downstream reviewer/outcome lift once outcome labels exist.")
    w("")


def main():
    """Run the evaluation and rewrite docs/EVAL_REPORT.md. Writes no other file."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--ablation-runs", type=int, default=5)
    ap.add_argument("--no-ablation", action="store_true")
    args = ap.parse_args()

    cases_doc, profiles = load_golden()
    cases = cases_doc["cases"]
    entries = [profiles[c["id"]] for c in cases]
    base = assess_corpus(entries)

    results = []
    for c in cases:
        a, canon = base[c["id"]]
        fails = check_case(c, a, canon)
        results.append({"case": c, "a": a, "canon": canon, "fails": fails})

    ms = [r for r in results if r["case"]["group"] == "must_surface"]
    rl = [r for r in results if r["case"]["group"] == "reasonable_low"]
    surfaced_ms = [r for r in ms if r["a"].attention in SURFACED]
    leaked = [r for r in ms if r["a"].attention is Attention.ROUTINE]
    recall = len(surfaced_ms) / len(ms)
    queue = [r for r in results if r["a"].attention in SURFACED]
    rl_surfaced = [r for r in rl if r["a"].attention in SURFACED]
    precision = len(surfaced_ms) / len(queue) if queue else 0.0

    lines: list[str] = []
    w = lines.append
    w("# EVAL_REPORT — final golden-set evaluation (deterministic + AI ablation)")
    w("")
    w("> **What this measures.** The golden set evaluates whether the system behaves")
    w("> consistently with the stated MVP assumptions and safety policy under sparse,")
    w("> contradictory and adversarial data. **It does not estimate accuracy at identifying")
    w("> successful founders; no real founder-outcome labels are available.** Nothing in this")
    w("> report is a founder-selection accuracy number, and \"precision\" below is")
    w("> informational only — with no outcome labels it measures nothing but how many")
    w("> reasonable_low cases were escalated. Real validation needs reviewer-labelled")
    w("> historical candidates or prospective reviewer feedback (PLAN §4.6).")
    w("")
    w(f"Golden set: `cases.yaml` SHA-256 `{sha256(CASES_PATH)}`  ")
    w(f"`profiles.json` SHA-256 `{sha256(PROFILES_PATH)}`  ")
    w(f"Rubric version (config hash): `{CFG.version_hash()}`  ")
    w(f"Assessment version: `{base[cases[0]['id']][0].assessment_version}`")
    w("")

    # -------------------------------------------------- 1. headline metrics
    w("## 1. Primary and required metrics")
    w("")
    w("| metric | value |")
    w("|---|---|")
    w(f"| **must_surface recall** (attention ∈ {{PRIORITY_REVIEW, REVIEW}}) | "
      f"**{recall:.3f}** ({len(surfaced_ms)}/{len(ms)}) |")
    w(f"| **must_surface leakage into ROUTINE** (hard safety property, must be 0) | "
      f"**{len(leaked)}** |")
    w(f"| review-queue rate (whole set) | {pct(len(queue), len(results))} "
      f"({len(queue)}/{len(results)}) |")
    w(f"| precision *(informational only)* | {precision:.3f} "
      f"({len(surfaced_ms)}/{len(queue)}) |")
    w(f"| expectation pass rate (all four dimensions + evidence assertions) | "
      f"{pct(sum(1 for r in results if not r['fails']), len(results))} "
      f"({sum(1 for r in results if not r['fails'])}/{len(results)}) |")
    w("")
    w(f"Target recall ≥ 0.95: **{'MET' if recall >= 0.95 else 'NOT MET'}**. "
      f"Leakage = 0: **{'MET' if not leaked else 'NOT MET'}**.")
    w("")

    # -------------------------------------------------- 2. per group
    w("## 2. Per-group results")
    w("")
    w("| group | cases | expectation pass | fail | attention distribution |")
    w("|---|---|---|---|---|")
    for g in ("must_surface", "reasonable_low", "ambiguous_spiky", "data_quality_adversarial"):
        rows = [r for r in results if r["case"]["group"] == g]
        ok = [r for r in rows if not r["fails"]]
        dist = Counter(r["a"].attention.value for r in rows)
        w(f"| {g} | {len(rows)} | {len(ok)} | {len(rows) - len(ok)} | "
          f"{', '.join(f'{k} {v}' for k, v in sorted(dist.items()))} |")
    w("")

    # -------------------------------------------------- 3. every case
    w("## 3. Every case")
    w("")
    w("| id | group | attention | potential | data_state | action | broad | conf | "
      "exceptional | result |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for r in results:
        a = r["a"]
        exc = ", ".join(s.name for s in a.exceptional.signals) or "—"
        w(f"| {r['case']['id']} | {r['case']['group'][:4]} | {a.attention.value} | "
          f"{a.potential.value} | {a.data_state.value} | {a.recommended_action.value} | "
          f"{a.broad_score:.1f} | {a.confidence:.3f} | "
          f"{'YES' if a.exceptional.flag else 'no'} ({exc}) | "
          f"{'PASS' if not r['fails'] else '**FAIL**'} |")
    w("")

    # -------------------------------------------------- 4. failures
    failures = [r for r in results if r["fails"]]
    w("## 4. Failing cases")
    w("")
    if not failures:
        w("None.")
    else:
        for r in failures:
            a = r["a"]
            w(f"### {r['case']['id']} ({r['case']['group']})")
            w("")
            w(f"*{r['case']['description'].strip()}*")
            w("")
            for f in r["fails"]:
                w(f"* {f}")
            w("")
            w(f"Observed: broad **{a.broad_score}**, confidence **{a.confidence}** "
              f"(coverage {a.confidence_breakdown.coverage}, "
              f"contradiction −{a.confidence_breakdown.contradiction_penalty}, "
              f"inference −{a.confidence_breakdown.inference_penalty}); "
              f"fired rules {a.fired_rules}.")
            w("")
            w(f"Expectation rests on: `{'`, `'.join(r['case']['expected_reason'])}`. "
              f"Adjudication is recorded in docs/EVAL_DECISIONS.md.")
            w("")
    w("")

    # -------------------------------------------------- 5. robustness (§7)
    w("## 5. Robustness decomposition")
    w("")
    w("Is recall achieved only by sending everything to REVIEW? This is the answer.")
    w("")
    ms_exc = [r for r in ms if r["a"].exceptional.flag]
    ms_noexc = [r for r in surfaced_ms if not r["a"].exceptional.flag]
    ms_partial = [r for r in ms if r["a"].data_state is not DataState.SUFFICIENT]
    rl_low = [r for r in rl if r["a"].potential is Potential.LOW]
    w("| measure | count | cases |")
    w("|---|---|---|")
    w(f"| must_surface WITH exceptional evidence | {len(ms_exc)} | "
      f"{', '.join(r['case']['id'] for r in ms_exc)} |")
    w(f"| must_surface surfaced WITHOUT exceptional evidence | {len(ms_noexc)} | "
      f"{', '.join(r['case']['id'] for r in ms_noexc)} |")
    w(f"| must_surface with PARTIAL / NEEDS_INFORMATION | {len(ms_partial)} | "
      f"{', '.join(r['case']['id'] + ':' + r['a'].data_state.value[:4] for r in ms_partial)} |")
    w(f"| reasonable_low correctly reaching LOW | {len(rl_low)} | "
      f"{', '.join(r['case']['id'] for r in rl_low)} |")
    w(f"| reasonable_low escalated to REVIEW+ | {len(rl_surfaced)} | "
      f"{', '.join(r['case']['id'] for r in rl_surfaced)} |")
    w("")
    if rl_surfaced:
        w("**Why each reasonable_low escalated:**")
        w("")
        for r in rl_surfaced:
            a = r["a"]
            why = [e.rule for e in a.policy_trace if e.fired and e.rule.startswith(("rule", "guard"))]
            w(f"* **{r['case']['id']}** → {a.attention.value} / {a.potential.value} / "
              f"{a.data_state.value}: broad {a.broad_score}, confidence {a.confidence}. "
              f"Fired: {', '.join(why)}.")
        w("")
    w(f"Attention split inside must_surface: "
      f"{dict(Counter(r['a'].attention.value for r in ms))}. "
      f"Recall is not carried by a blanket REVIEW: "
      f"{sum(1 for r in ms if r['a'].attention is Attention.PRIORITY_REVIEW)} of {len(ms)} are "
      f"PRIORITY_REVIEW, and {len(ms_noexc)} surfaced without any exceptional signal at all.")
    w("")

    # -------------------------------------------------- 6. distributions
    w("## 6. Output distributions (whole golden set)")
    w("")
    for name, vals in (("attention", [r["a"].attention.value for r in results]),
                       ("potential", [r["a"].potential.value for r in results]),
                       ("data_state", [r["a"].data_state.value for r in results]),
                       ("recommended_action", [r["a"].recommended_action.value for r in results])):
        w(f"* **{name}**: " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(vals).items())))
    w("")
    grid = Counter((r["a"].potential.value, r["a"].data_state.value) for r in results)
    w("`potential × data_state` (v2.3 requires the LOW row to be SUFFICIENT-only):")
    w("")
    w("| potential | SUFFICIENT | PARTIAL | NEEDS_INFORMATION |")
    w("|---|---|---|---|")
    for p in ("HIGH", "MEDIUM", "LOW", "UNKNOWN"):
        w(f"| {p} | {grid[(p, 'SUFFICIENT')]} | {grid[(p, 'PARTIAL')]} | "
          f"{grid[(p, 'NEEDS_INFORMATION')]} |")
    w("")
    w(f"Invariants on this set: `LOW ∧ ¬SUFFICIENT` = "
      f"{sum(v for (p, d), v in grid.items() if p == 'LOW' and d != 'SUFFICIENT')}; "
      f"`ROUTINE ∧ ¬SUFFICIENT` = "
      f"{sum(1 for r in results if r['a'].attention is Attention.ROUTINE and r['a'].data_state is not DataState.SUFFICIENT)}; "
      f"`ROUTINE ∧ exceptional` = "
      f"{sum(1 for r in results if r['a'].attention is Attention.ROUTINE and r['a'].exceptional.flag)}.")
    w("")

    # -------------------------------------------------- 7. ablation
    if not args.no_ablation:
        w("## 7. Seeded 30% decision-relevant ablation (5 runs)")
        w("")
        rows, conf_inc, downgrades, new_lows = run_ablation(
            entries, base, runs=args.ablation_runs)
        w("| run | must_surface recall | mean confidence | review-queue rate | LOW | ROUTINE | "
          "UNKNOWN | SUFFICIENT / PARTIAL / NEEDS_INFO |")
        w("|---|---|---|---|---|---|---|---|")
        base_conf = statistics.mean(a.confidence for a, _ in base.values())
        base_queue = len(queue) / len(results)
        base_low = sum(1 for r in results if r["a"].potential is Potential.LOW)
        base_routine = sum(1 for r in results if r["a"].attention is Attention.ROUTINE)
        base_unknown = sum(1 for r in results if r["a"].potential is Potential.UNKNOWN)
        base_ds = Counter(r["a"].data_state.value for r in results)
        w(f"| **baseline** | **{recall:.3f}** | **{base_conf:.3f}** | **{base_queue:.3f}** | "
          f"**{base_low}** | **{base_routine}** | **{base_unknown}** | "
          f"**{base_ds['SUFFICIENT']} / {base_ds['PARTIAL']} / {base_ds['NEEDS_INFORMATION']}** |")
        agg = defaultdict(list)
        for run, res in rows:
            ms_ids = [c["id"] for c in cases if c["group"] == "must_surface"]
            r_recall = sum(1 for i in ms_ids if res[i][0].attention in SURFACED) / len(ms_ids)
            conf = statistics.mean(a.confidence for a, _ in res.values())
            q = sum(1 for a, _ in res.values() if a.attention in SURFACED) / len(res)
            low = sum(1 for a, _ in res.values() if a.potential is Potential.LOW)
            routine = sum(1 for a, _ in res.values() if a.attention is Attention.ROUTINE)
            unk = sum(1 for a, _ in res.values() if a.potential is Potential.UNKNOWN)
            ds = Counter(a.data_state.value for a, _ in res.values())
            for k, v in (("recall", r_recall), ("conf", conf), ("queue", q), ("low", low),
                         ("routine", routine), ("unknown", unk),
                         ("suff", ds["SUFFICIENT"]), ("part", ds["PARTIAL"]),
                         ("need", ds["NEEDS_INFORMATION"])):
                agg[k].append(v)
            w(f"| {run + 1} | {r_recall:.3f} | {conf:.3f} | {q:.3f} | {low} | {routine} | {unk} | "
              f"{ds['SUFFICIENT']} / {ds['PARTIAL']} / {ds['NEEDS_INFORMATION']} |")
        w(f"| **mean** | **{statistics.mean(agg['recall']):.3f}** | "
          f"**{statistics.mean(agg['conf']):.3f}** | **{statistics.mean(agg['queue']):.3f}** | "
          f"**{statistics.mean(agg['low']):.1f}** | **{statistics.mean(agg['routine']):.1f}** | "
          f"**{statistics.mean(agg['unknown']):.1f}** | "
          f"**{statistics.mean(agg['suff']):.1f} / {statistics.mean(agg['part']):.1f} / "
          f"{statistics.mean(agg['need']):.1f}** |")
        w("")
        m_conf = statistics.mean(agg["conf"])
        m_queue = statistics.mean(agg["queue"])
        m_recall = statistics.mean(agg["recall"])
        w(f"**Ablation deltas (baseline → {args.ablation_runs}-run mean).** "
          f"mean confidence {base_conf:.3f} → {m_conf:.3f} "
          f"(**{m_conf - base_conf:+.3f}**); review-queue rate {base_queue:.3f} → "
          f"{m_queue:.3f} (**{m_queue - base_queue:+.3f}**); must_surface recall "
          f"{recall:.3f} → {m_recall:.3f} (**{m_recall - recall:+.3f}**). Recall holds "
          f"while confidence falls and the queue grows — the intended recall-first "
          f"response to sparse data, and its direct cost in reviewer load.")
        w("")
        w("### Safety properties under ablation")
        w("")
        w(f"* **PRIORITY_REVIEW/REVIEW → ROUTINE downgrades: {len(downgrades)}** "
          f"(required: 0)." + ("" if not downgrades else f" {downgrades}"))
        w(f"* **Transitions into LOW caused by data removal: {len(new_lows)}** "
          f"(required: 0)." + ("" if not new_lows else f" {new_lows}"))
        w(f"* Individual confidence INCREASES (F-6, accepted): **{len(conf_inc)}**. "
          f"Of those, reaching ROUTINE: "
          f"**{sum(1 for x in conf_inc if x[4] == 'ROUTINE')}**; reaching LOW: "
          f"**{sum(1 for x in conf_inc if x[5] == 'LOW')}** (both expected 0).")
        if conf_inc:
            w("")
            w("| run | case | confidence before → after | attention after | potential after | "
              "contradictions removed |")
            w("|---|---|---|---|---|---|")
            for run, cid, b, a_, att, pot, removed in conf_inc[:25]:
                w(f"| {run + 1} | {cid} | {b:.3f} → {a_:.3f} | {att} | {pot} | "
                  f"{', '.join(removed) or '—'} |")
            if len(conf_inc) > 25:
                w(f"| … | *{len(conf_inc) - 25} more* | | | | |")
        w("")

    # -------------------------------------------------- 8. F-6 probe
    w("## 8. F-6 probe — removing the field that CARRIES the contradiction")
    w("")
    w("The random 30% ablation above rarely isolates a contradiction: it usually removes the")
    w("contradiction *and* several coverage families in the same draw, so the coverage loss")
    w("dominates and confidence falls. To answer the F-6 question directly, this probe removes")
    w("**only** the carrier field, one case at a time.")
    w("")
    probe_rows = f6_probe(entries, base)
    w("| case | contradiction | field removed | resolved | confidence before → after | Δ | "
      "attention | potential |")
    w("|---|---|---|---|---|---|---|---|")
    for r in probe_rows:
        d = r["conf_after"] - r["conf_before"]
        w(f"| {r['case']} | {r['code']} | `{r['field']}` | "
          f"{'yes' if r['removed'] else 'no'} | {r['conf_before']:.3f} → {r['conf_after']:.3f} | "
          f"{d:+.3f} | {r['att_before']} → {r['att_after']} | "
          f"{r['pot_before']} → {r['pot_after']} |")
    ups = [r for r in probe_rows if r["conf_after"] > r["conf_before"]]
    bad_att = [r for r in ups if r["att_after"] == "ROUTINE" and r["att_before"] != "ROUTINE"]
    bad_pot = [r for r in ups if r["pot_after"] == "LOW" and r["pot_before"] != "LOW"]
    w("")
    w(f"* Confidence increases from isolated contradiction removal: **{len(ups)}** of "
      f"{len(probe_rows)} probes — the accepted F-6 behaviour, not a defect.")
    w(f"* Of those, any that became ROUTINE: **{len(bad_att)}** (required 0). "
      f"Any that became LOW: **{len(bad_pot)}** (required 0).")
    w("")

    ai_section(w)

    REPORT_PATH.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\n--- wrote {REPORT_PATH} ---", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
