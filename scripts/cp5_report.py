#!/usr/bin/env python3
"""CP5 evidence: batch-assess load_800, write load_800_assessed.json, and print
the sanity report the CP5 gate requires (cross-tabs, causal decomposition,
supplied-profile assessments)."""
from __future__ import annotations

import copy
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.assessment import assess                        # noqa: E402
from app.models.raw import RawProfile, load_profiles     # noqa: E402
from app.normalize import load_config, normalize         # noqa: E402
from app.policy import (RULE_1, RULE_2, Attention, DataState,  # noqa: E402
                        PolicyInput, Potential, RecommendedAction, apply_policy)

CFG = load_config()
OUT = ROOT / "data" / "synthetic" / "load_800_assessed.json"


def rule(ch="=", n=100):
    """Print a horizontal separator."""
    print(ch * n)


def table(title, counter, order, total):
    """Print a counted distribution with percentages."""
    print(f"\n{title}")
    for k in order:
        n = counter.get(k, 0)
        print(f"  {k:<20} {n:>5}  {n / total:6.1%}")


def crosstab(title, pairs, rows, cols):
    """Print a two-dimension crosstab with margins.

    Used to show the four dimensions are genuinely ORTHOGONAL — e.g. that
    PRIORITY_REVIEW × UNKNOWN is a populated cell, not an empty one."""
    c = Counter(pairs)
    w = max(len(str(r)) for r in rows) + 2
    print(f"\n{title}")
    print(" " * w + "".join(f"{str(x):>20}" for x in cols) + f"{'TOTAL':>10}")
    for r in rows:
        vals = [c.get((r, x), 0) for x in cols]
        print(f"{str(r):<{w}}" + "".join(f"{v:>20}" for v in vals) + f"{sum(vals):>10}")
    tot = [sum(c.get((r, x), 0) for r in rows) for x in cols]
    print(f"{'TOTAL':<{w}}" + "".join(f"{v:>20}" for v in tot) + f"{sum(tot):>10}")


def show(a, label):
    """Print one assessment in full, including the complete policy trace."""
    rule()
    print(f"### {label}   person_id={a.person_id}")
    print(f"  broad_score        {a.broad_score}")
    print(f"  confidence         {a.confidence}   "
          f"(coverage {a.confidence_breakdown.coverage} "
          f"− contradictions {a.confidence_breakdown.contradiction_penalty} "
          f"− inferences {a.confidence_breakdown.inference_penalty})")
    print(f"  coverage components {a.confidence_breakdown.coverage_components}")
    print(f"  exceptional        flag={a.exceptional.flag}  rule={a.exceptional.rule}")
    for s in a.exceptional.signals:
        print(f"      FIRED {s.name} [{s.strength.value}] {list(s.source_fields)}")
    for k, v in a.exceptional.not_fired.items():
        print(f"      not fired {k}: {v}")
    print(f"  archetype          {a.archetype.archetype}  secondary={a.archetype.secondary}")
    print(f"      strong  : {a.archetype.strong_signals}")
    print(f"      missing : {a.archetype.missing_for_archetype}")
    rule("-")
    print(f"  potential          {a.potential.value}")
    print(f"  attention          {a.attention.value}")
    print(f"  data_state         {a.data_state.value}")
    print(f"  recommended_action {a.recommended_action.value}")
    rule("-")
    print("  SIGNALS")
    w = CFG.weights["signal_weights"]
    for s in a.signals:
        print(f"    {s.name:<24} w={w[s.name]:>3}  value={s.value:.3f}  "
              f"{s.strength.value:<7} {s.type.value:<9} observed={s.observed}")
        print(f"        sources: {list(s.source_fields)}")
        print(f"        {s.explanation}")
    print("  MISSING")
    for m in a.missing or []:
        print(f"    {m.code}: {m.detail}")
    if not a.missing:
        print("    (none)")
    print("  CONTRADICTIONS")
    for c in a.contradictions or []:
        print(f"    {c.code}: {c.detail}")
    if not a.contradictions:
        print("    (none)")
    print("  POLICY TRACE")
    for e in a.policy_trace:
        mark = "FIRED " if e.fired else "  -   "
        print(f"    {mark}{e.rule}")
        print(f"           condition: {e.condition}")
        print(f"           evidence : {e.evidence}")
        if e.sets:
            print(f"           sets     : {e.sets}")
        if e.overrode:
            print(f"           overrode : {e.overrode}")
        if e.preserved:
            print(f"           preserved: {e.preserved}")
        if e.note:
            print(f"           note     : {e.note}")


def matrix_and_boundaries():
    """Evidence items 3, 5, 6, 10 — the v2.2 amendment surfaces."""
    from app.evidence.confidence import coverage_subcomponents

    print("#" * 100)
    print("# 3 — SOURCE -> COVERAGE MATRIX (PLAN v2.2 §4.3 Amendment 1)")
    print("#" * 100)
    w = CFG.weights["confidence"]["coverage_weights"]
    families = {
        "history_depth": "experience[] presence / role count",
        "seniority_readability": "experience[].management_level",
        "tenure_readability": "experience[].duration_months",
        "is_current_known": "is_current / active_experience / date_to",
        "start_dates_readable": "date_from / date_from_year / date_from_month",
        "education_present": "education[] presence",
        "institution_present": "education[].institution_name",
        "degree_interpretable": "education[].degree",
        "industry_classified": "company_industry / categories_and_keywords",
        "scope_available": "company_employees_count / company_size_range",
        "titles_readable": "experience[].position_title",
        "total_experience_stated": "total_experience_duration_months",
        "location_known": "location_country / location_city",
        "breadth_inputs_readable": "company_industry (raw strings)",
    }
    protects = {
        "history_depth": "all signals; rule 5 / NEEDS_INFORMATION keys on THIS alone",
        "seniority_readability": "leadership (15) + career_trajectory (15)  <- the F-1 gap",
        "tenure_readability": "healthcare_depth, founder tenure bonus, other",
        "is_current_known": "engagement readiness",
        "start_dates_readable": "career_trajectory, exceptional_progression",
        "education_present": "education_signal (10)",
        "institution_present": "education_signal",
        "degree_interpretable": "education_signal, exceptional_credential",
        "industry_classified": "healthcare_depth (20)",
        "scope_available": "operating_environment (10), leadership scope bonus",
        "titles_readable": "founder_evidence (25), A8 decidability",
        "total_experience_stated": "other (5)",
        "location_known": "other (5)",
        "breadth_inputs_readable": "other (breadth)",
    }
    probe = coverage_subcomponents(
        normalize(next(iter(load_profiles(ROOT / "data" / "raw" / "sample.json"))), CFG))
    print(f"{'component (weight)':<34}{'sub-component':<26}{'raw evidence family':<44}"
          f"signals protected")
    for comp, subs in probe.items():
        for i, sub in enumerate(subs):
            head = f"{comp} ({w[comp]})" if i == 0 else ""
            print(f"{head:<34}{sub:<26}{families[sub]:<44}{protects[sub]}")

    print("\n" + "#" * 100)
    print("# 5/6 — BOUNDARY TESTS (thresholds REPORTED, never changed) + the former F-5 cases")
    print("#" * 100)

    def P(b, c, e=False, i=False, cov=1.0):
        """Run the policy on stated scalars — no profile, no scorer in the loop."""
        return apply_policy(PolicyInput(broad_score=b, confidence=c, exceptional=e,
                                        experience_incomplete=i, coverage=cov), CFG)

    def row(label, o):
        """Print one boundary probe as its four resulting dimensions."""
        print(f"  {label:<34} -> {o.attention.value:<16}{o.potential.value:<9}"
              f"{o.data_state.value:<19}{o.recommended_action.value}")

    print("\n broad boundaries @ confidence 0.8 (trusted, no exceptional)")
    for b in (29.99, 30, 30.01, 39.99, 40, 40.01, 64.99, 65, 65.01):
        row(f"broad={b}  conf=0.8", P(b, 0.8))
    print("\n THE FORMER F-5 INVERSION — broad boundaries @ confidence 0.5 (untrusted)")
    print("   v2.1: 29.99 -> MEDIUM but 30.00 -> UNKNOWN. v2.2 guard 5: all UNKNOWN.")
    for b in (20, 29.99, 30.0, 30.01, 39.99, 40, 64.99, 65, 65.01, 100):
        row(f"broad={b}  conf=0.5", P(b, 0.5))
    print("\n confidence boundaries")
    for c in (0.599, 0.600, 0.601):
        row(f"broad=70  conf={c}", P(70, c))
    for c in (0.599, 0.600, 0.601):
        row(f"broad=25  conf={c}", P(25, c))
    print("\n reviewer's required examples")
    row("exceptional, conf=0.40", P(45, 0.40, e=True))
    row("exceptional + NEEDS_INFORMATION", P(45, 0.40, e=True, i=True, cov=0.4))
    row("rule 2 + PARTIAL (action preserved)", P(70, 0.8, cov=0.85))
    row("rule 4 shape + PARTIAL", P(25, 0.9, cov=0.85))
    row("rule 4 shape + SUFFICIENT", P(25, 0.9, cov=1.0))


def main():
    """Assessment/policy walkthrough over the load population.

    Threshold boundaries are REPORTED, never changed: this script is a
    measuring instrument and writes no config."""
    matrix_and_boundaries()

    # ---------------------------------------------------- supplied profiles
    print("\n" + "#" * 100)
    print("# M — FULL ASSESSMENT, THE TWO SUPPLIED PROFILES")
    print("#" * 100)
    for i, p in enumerate(load_profiles(ROOT / "data" / "raw" / "sample.json"), 1):
        show(assess(normalize(p, CFG), CFG), f"SUPPLIED PROFILE {i}")

    # ---------------------------------------------------------- load_800
    profiles = load_profiles(ROOT / "data" / "synthetic" / "load_800.json")
    assessments = [assess(normalize(p, CFG), CFG) for p in profiles]
    n = len(assessments)
    OUT.write_text(json.dumps([a.to_dict() for a in assessments], indent=1))

    print("\n" + "#" * 100)
    print(f"# J — LOAD-800 SANITY REPORT   (N={n})   written to {OUT.relative_to(ROOT)}")
    print("#" * 100)

    table("attention", Counter(a.attention.value for a in assessments),
          ["PRIORITY_REVIEW", "REVIEW", "ROUTINE"], n)
    table("potential", Counter(a.potential.value for a in assessments),
          ["HIGH", "MEDIUM", "LOW", "UNKNOWN"], n)
    table("data_state", Counter(a.data_state.value for a in assessments),
          ["SUFFICIENT", "PARTIAL", "NEEDS_INFORMATION"], n)
    table("recommended_action", Counter(a.recommended_action.value for a in assessments),
          ["CONSIDER_ENGAGEMENT", "HUMAN_REVIEW", "RESEARCH", "NO_URGENT_ACTION"], n)

    crosstab("attention × data_state",
             [(a.attention.value, a.data_state.value) for a in assessments],
             ["PRIORITY_REVIEW", "REVIEW", "ROUTINE"],
             ["SUFFICIENT", "PARTIAL", "NEEDS_INFORMATION"])
    crosstab("potential × data_state  (v2.3: LOW row must be SUFFICIENT-only)",
             [(a.potential.value, a.data_state.value) for a in assessments],
             ["HIGH", "MEDIUM", "LOW", "UNKNOWN"],
             ["SUFFICIENT", "PARTIAL", "NEEDS_INFORMATION"])
    crosstab("attention × potential",
             [(a.attention.value, a.potential.value) for a in assessments],
             ["PRIORITY_REVIEW", "REVIEW", "ROUTINE"],
             ["HIGH", "MEDIUM", "LOW", "UNKNOWN"])

    # ------------------------------------------- causal decomposition
    pr = [a for a in assessments if a.attention is Attention.PRIORITY_REVIEW]
    by_exc = [a for a in pr if RULE_1 in a.fired_rules]
    by_r2 = [a for a in pr if RULE_2 in a.fired_rules]
    both = [a for a in pr if RULE_1 in a.fired_rules and RULE_2 in a.fired_rules]
    conf_bar = CFG.thresholds["priority_confidence"]
    low_conf = [a for a in assessments if a.confidence < conf_bar]

    print("\nCAUSAL DECOMPOSITION")
    print(f"  PRIORITY_REVIEW total                          {len(pr):>5}  {len(pr)/n:6.1%}")
    print(f"    caused by exceptional evidence (rule 1)      {len(by_exc):>5}")
    print(f"    caused by broad/confidence (rule 2)          {len(by_r2):>5}")
    print(f"    overlap (both rules fired)                   {len(both):>5}")
    print(f"    exceptional ONLY                             {len(by_exc)-len(both):>5}")
    print(f"    rule 2 ONLY                                  {len(by_r2)-len(both):>5}")
    print(f"  ROUTINE / LOW                                  "
          f"{sum(1 for a in assessments if a.attention is Attention.ROUTINE):>5}")
    print(f"  low-confidence profiles (< {conf_bar})              {len(low_conf):>5}")
    print(f"    ... of which ROUTINE                         "
          f"{sum(1 for a in low_conf if a.attention is Attention.ROUTINE):>5}"
          f"   <- must be 0: low confidence is protected from ROUTINE")
    print(f"  PRIORITY_REVIEW + NEEDS_INFORMATION            "
          f"{sum(1 for a in pr if a.data_state is DataState.NEEDS_INFORMATION):>5}")
    print(f"\n  --- v2.2 required invariant counts ---")
    print(f"  ROUTINE + PARTIAL                              "
          f"{sum(1 for a in assessments if a.attention is Attention.ROUTINE and a.data_state is DataState.PARTIAL):>5}"
          f"   <- must be 0")
    print(f"  ROUTINE + NEEDS_INFORMATION                    "
          f"{sum(1 for a in assessments if a.attention is Attention.ROUTINE and a.data_state is DataState.NEEDS_INFORMATION):>5}"
          f"   <- must be 0")
    print(f"  LOW + SUFFICIENT                               "
          f"{sum(1 for a in assessments if a.potential is Potential.LOW and a.data_state is DataState.SUFFICIENT):>5}")
    print(f"  LOW + PARTIAL                                  "
          f"{sum(1 for a in assessments if a.potential is Potential.LOW and a.data_state is DataState.PARTIAL):>5}"
          f"   <- must be 0 (v2.3)")
    print(f"  LOW + NEEDS_INFORMATION                        "
          f"{sum(1 for a in assessments if a.potential is Potential.LOW and a.data_state is DataState.NEEDS_INFORMATION):>5}"
          f"   <- must be 0 (v2.3)")
    print(f"  UNKNOWN + PARTIAL                              "
          f"{sum(1 for a in assessments if a.potential is Potential.UNKNOWN and a.data_state is DataState.PARTIAL):>5}")
    print(f"  ROUTINE not SUFFICIENT                         "
          f"{sum(1 for a in assessments if a.attention is Attention.ROUTINE and a.data_state is not DataState.SUFFICIENT):>5}"
          f"   <- must be 0")
    print(f"  PRIORITY_REVIEW + UNKNOWN                      "
          f"{sum(1 for a in pr if a.potential is Potential.UNKNOWN):>5}")
    print(f"  PRIORITY_REVIEW + potential != HIGH            "
          f"{sum(1 for a in pr if a.potential is not Potential.HIGH):>5}"
          f"   <- potential does not mirror attention")

    # -------------------------------------------------------- examples
    print("\n5 EXAMPLES OF PRIORITY_REVIEW (with cause)")
    for a in pr[:5]:
        print(f"  {a.person_id[:8]}  broad={a.broad_score:<6} conf={a.confidence:<6} "
              f"potential={a.potential.value:<8} data_state={a.data_state.value:<18} "
              f"action={a.recommended_action.value}")
        print(f"      fired={a.fired_rules}")
        print(f"      exceptional: {a.exceptional.rule}")

    routine = [a for a in assessments if a.attention is Attention.ROUTINE]
    print("\n3 EXAMPLES OF ROUTINE / LOW (with reason)")
    for a in routine[:3]:
        print(f"  {a.person_id[:8]}  broad={a.broad_score:<6} conf={a.confidence:<6} "
              f"potential={a.potential.value:<6} data_state={a.data_state.value:<12} "
              f"action={a.recommended_action.value}")
        print(f"      broad < {CFG.thresholds['routine_broad']} AND confidence >= {conf_bar} "
              f"AND exceptional={a.exceptional.flag} -> rule 4")

    # ------------------------------------------- L: ablation over the population
    print("\n" + "#" * 100)
    print("# L — MISSING-DATA SAFETY (v2.2 HARD INVARIANT: zero downgrades to ROUTINE)")
    print("#" * 100)
    # Evidence FAMILIES, not single fields: `is_current` is recoverable from
    # `active_experience` and country from city, so removing one alone removes
    # nothing. No family is exempted, including those carrying positive evidence.
    FAMILIES = {
        "position_title": ["position_title"],
        "management_level": ["management_level"],
        "duration_months": ["duration_months"],
        "role_dates": ["date_from", "date_from_year", "date_from_month",
                       "date_to", "date_to_year", "date_to_month"],
        "company_industry": ["company_industry", "company_categories_and_keywords"],
        "company_size": ["company_employees_count", "company_size_range"],
        "is_current": ["is_current", "active_experience"],
        "education": ["education"],
        "total_experience": ["total_experience_duration_months"],
        "location": ["location_country", "location_city"],
        "department": ["department"],
    }
    random.seed(20260819)
    sample = random.sample(profiles, 150)
    trans, downgrades = Counter(), []
    pot_changes, ds_changes = Counter(), Counter()
    conf_deltas, examples = [], {}
    total = 0
    for p in sample:
        raw = p.model_dump(mode="json", exclude_none=False)
        before = assess(normalize(RawProfile.model_validate(raw), CFG), CFG)
        if before.attention is Attention.ROUTINE:
            continue
        for family, fields in FAMILIES.items():
            d = copy.deepcopy(raw)
            for f in fields:
                if f == "education":
                    d["education"] = []
                    continue
                if f in d:
                    d[f] = None
                for key in ("experience", "education"):
                    for row in d.get(key) or []:
                        if f in row:
                            row[f] = None
            after = assess(normalize(RawProfile.model_validate(d), CFG), CFG)
            total += 1
            trans[(before.attention.value, after.attention.value)] += 1
            pot_changes[(before.potential.value, after.potential.value)] += 1
            ds_changes[(before.data_state.value, after.data_state.value)] += 1
            conf_deltas.append(after.confidence - before.confidence)
            if after.attention is Attention.ROUTINE:
                downgrades.append((raw["mdm_person_id"][:8], family,
                                   before.attention.value, after.attention.value))
            if family not in examples:
                examples[family] = (
                    raw["mdm_person_id"][:8],
                    f"{before.attention.value}/{before.potential.value}/"
                    f"{before.data_state.value} broad={before.broad_score} "
                    f"conf={before.confidence} cov={before.confidence_breakdown.coverage}",
                    f"{after.attention.value}/{after.potential.value}/"
                    f"{after.data_state.value} broad={after.broad_score} "
                    f"conf={after.confidence} cov={after.confidence_breakdown.coverage}")

    print(f"  total ablations                      {total}")
    print(f"  ATTENTION DOWNGRADES TO ROUTINE      {len(downgrades)}   "
          f"<- hard invariant: must be 0")
    print(f"  mean confidence delta                {sum(conf_deltas)/len(conf_deltas):+.4f}")
    ups = [d for d in conf_deltas if d > 1e-9]
    print(f"  confidence INCREASED in              {len(ups)} / {total} "
          f"({len(ups)/total:.2%})   <- FINDING F-6, all contradiction-driven")
    print(f"  max confidence increase              {max(conf_deltas):+.4f}")
    print("\n  attention transitions (before -> after):")
    for k, v in sorted(trans.items()):
        print(f"    {k[0]:<16} -> {k[1]:<16} {v:>5}")
    print("\n  potential transitions (before -> after), changes only:")
    for k, v in sorted(pot_changes.items(), key=lambda x: -x[1]):
        if k[0] != k[1]:
            print(f"    {k[0]:<9} -> {k[1]:<9} {v:>5}")
    print("\n  data_state transitions (before -> after), changes only:")
    for k, v in sorted(ds_changes.items(), key=lambda x: -x[1]):
        if k[0] != k[1]:
            print(f"    {k[0]:<18} -> {k[1]:<18} {v:>5}")
    print("\n  one example per ablated family (attention/potential/data_state):")
    for family, (pid, b, a) in examples.items():
        print(f"    {family:<20} {pid}")
        print(f"        before {b}")
        print(f"        after  {a}")
    if downgrades:
        print("\n  !!! DOWNGRADES (invariant violated):")
        for x in downgrades[:20]:
            print(f"    {x}")


if __name__ == "__main__":
    main()
