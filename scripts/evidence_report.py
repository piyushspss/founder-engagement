#!/usr/bin/env python3
"""CP3 evidence: signal tables, confidence breakdowns, semantics probes."""
from __future__ import annotations
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.evidence import compute_confidence, compute_signals  # noqa: E402
from app.evidence.signals import broad_score  # noqa: E402
from app.models.raw import RawProfile, load_profiles  # noqa: E402
from app.normalize import load_config, normalize  # noqa: E402

CFG = load_config()
W = CFG.weights["signal_weights"]


def signal_table(c, label):
    """Print the per-signal table: weight, value, weighted contribution,
    strength, provenance type, observed flag and source fields."""
    signals = compute_signals(c, CFG)
    print(f"\n{'='*118}\n### {label}  —  person_id={c.person_id}")
    print(f"{'signal':<22}{'w':>4}{'value':>7}{'w*v':>7}  {'strength':<9}{'type':<9}{'obs':<5}sources")
    print("-"*118)
    for s in signals:
        src = ", ".join(s.source_fields[:3]) + ("…" if len(s.source_fields) > 3 else "")
        print(f"{s.name:<22}{W[s.name]:>4}{s.value:>7.3f}{W[s.name]*s.value:>7.2f}  "
              f"{s.strength.value:<9}{s.type.value:<9}{str(s.observed):<5}{src or '—'}")
    print(f"{'BROAD SCORE':<22}{100:>4}{'':>7}{broad_score(signals, CFG):>7.2f}")
    print("\nexplanations:")
    for s in signals:
        print(f"  • {s.name}: {s.explanation}")
    return signals


def conf_table(c, label):
    """Print the confidence decomposition: each coverage component and its
    contribution, then both penalties, then the final value."""
    cb = compute_confidence(c, CFG)
    cw = CFG.weights["confidence"]["coverage_weights"]
    print(f"\n--- confidence: {label} ---")
    print(f"{'coverage component':<34}{'weight':>7}{'share':>7}{'contrib':>9}")
    for k, v in cb.coverage_components.items():
        print(f"{k:<34}{cw[k]:>7}{v:>7.2f}{cw[k]*v/100:>9.3f}")
    print(f"{'coverage':<34}{'':>7}{'':>7}{cb.coverage:>9.3f}")
    print(f"{'contradiction_penalty':<34}{'':>7}{'':>7}{-cb.contradiction_penalty:>9.3f}   {cb.contradictions or '{}'}")
    print(f"{'inference_penalty':<34}{'':>7}{'':>7}{-cb.inference_penalty:>9.3f}   {cb.inferences or '{}'}")
    print(f"{'FINAL CONFIDENCE':<34}{'':>7}{'':>7}{cb.confidence:>9.3f}")
    return cb


def probe(name, **kw):
    """Build a minimal synthetic profile for a semantics probe.

    Starts empty so a probe isolates exactly the field under test — used to
    show that a missing field is neutral rather than negative."""
    base = {"mdm_person_id": name, "headline": "probe", "experience": [], "education": [],
            "total_experience_duration_months": None}
    base.update(kw)
    return normalize(RawProfile.model_validate(base), CFG)


def R(**kw):
    """A fully-populated role, overridable per keyword — the baseline a probe
    removes one field from."""
    b = {"position_title": "Product Manager", "company_name": "Acme Co",
         "company_industry": "Hospital & Health Care", "management_level": "Manager",
         "company_size_range": "51-200 employees", "company_employees_count": 120,
         "date_from": "01/2018", "date_from_year": 2018, "date_from_month": 1,
         "date_to": "01/2022", "date_to_year": 2022, "date_to_month": 1,
         "duration_months": 48}
    b.update(kw)
    return b


def main():
    """Evidence walkthrough over the two supplied sample profiles, plus
    semantics probes and load-population distributions. Read-only."""
    raws = load_profiles(str(ROOT / "data/raw/sample.json"))
    canon = [normalize(r, CFG) for r in raws]
    labels = ["FOUNDER #1 — Senior Product Manager, health tech",
              "FOUNDER #2 — RN → Clinical Operations Lead"]
    for c, lab in zip(canon, labels):
        signal_table(c, lab)
        conf_table(c, lab)
    section_c(canon)

    # ---------------- A. unknown-institution semantics ----------------
    print(f"\n{'='*118}\n### A. UNKNOWN-INSTITUTION SEMANTICS")
    p = CFG.weights["signal_params"]["education_signal"]
    print(f"config: institution_tier_scores={p['institution_tier_scores']}  "
          f"unknown_neutral={p['unknown_neutral']}   weight(education_signal)={W['education_signal']}")
    print(f"\n{'case':<44}{'value':>7}{'strength':>10}{'obs':>6}{'points of 100':>15}")
    print("-"*84)
    cases = [
        ("Tier-1 institution (Harvard, BA)", [{"institution_name": "Harvard University", "degree": "BA, History"}]),
        ("Tier-2 institution (Cornell, BA)", [{"institution_name": "Cornell University", "degree": "BA, History"}]),
        ("Unknown institution (Cobalt Ridge, BA)", [{"institution_name": "Cobalt Ridge University", "degree": "BA, History"}]),
        ("Unknown institution, unknown degree", [{"institution_name": "Cobalt Ridge University", "degree": "Certificate, Basketweaving"}]),
        ("Education missing entirely", []),
    ]
    for lab, edu in cases:
        s = compute_signals(probe(lab, education=edu), CFG)[4]
        print(f"{lab:<44}{s.value:>7.3f}{s.strength.value:>10}{str(s.observed):>6}"
              f"{W['education_signal']*s.value:>15.2f}")

    # ---------------- B. healthcare ambiguity ----------------
    print(f"\n{'='*118}\n### B. HEALTHCARE AMBIGUITY SEMANTICS")
    print(f"{'case':<44}{'health_flag':>12}{'hc value':>9}{'points':>7}"
          f"{'domain coverage':>17}{'confidence':>12}  flags")
    print("-"*118)
    hcases = [
        ("(a) recognised healthcare (Hospital & Health Care)", R()),
        ("(b) recognised non-healthcare (Computer Software)", R(company_industry="Computer Software")),
        ("(c) present but unrecognised ('Widget Fabrication')", R(company_industry="Widget Fabrication", company_categories_and_keywords=[])),
        ("(d) industry missing entirely", R(company_industry=None, company_categories_and_keywords=[])),
        ("    industry missing, health keyword present", R(company_industry=None, company_categories_and_keywords=["digital health"])),
    ]
    for lab, r in hcases:
        c = probe(lab, experience=[r])
        sg = compute_signals(c, CFG)[1]
        cb = compute_confidence(c, CFG)
        fl = sorted(c.flag_codes() & {"UNKNOWN_INDUSTRY"})
        print(f"{lab:<44}{c.roles[0].health_flag.value:>12}{sg.value:>9.3f}"
              f"{W['healthcare_depth']*sg.value:>7.2f}"
              f"{cb.coverage_components['company_domain_classification']:>17.2f}"
              f"{cb.confidence:>12.3f}  {fl or '—'}")

    # ---------------- D. Lead placement ----------------
    print(f"\n{'='*118}\n### D. `Lead` IN THE LEADERSHIP TAXONOMY")
    scores = CFG.weights["signal_params"]["leadership"]["level_scores"]
    from app.evidence.signals import LEVEL_RANK
    order = ["Training", "Entry", "Specialist", "Senior", "Lead", "Manager",
             "Director", "VP", "C-Level"]
    print(f"{'level':<14}{'level_score':>12}{'trajectory rank':>17}{'leadership signal value':>26}{'points':>8}")
    print("-"*78)
    for lv in order:
        s = compute_signals(probe(lv, experience=[R(management_level=lv)]), CFG)[2]
        print(f"{lv:<14}{scores.get(lv, float('nan')):>12}{LEVEL_RANK.get(lv, -1):>17}"
              f"{s.value:>26.3f}{W['leadership']*s.value:>8.2f}")

    section_f(canon)
    distributions()


def section_c(canon):
    """Show the company-size contradiction and what it costs confidence."""
    print(f"\n{'='*118}\n### C. COMPANY-SIZE CONTRADICTION (FOUNDER #2)")
    c = canon[1]
    print(f"{'role':<30}{'exact count':>12}{'supplied range':>22}{'range min/max':>16}{'mismatch':>10}")
    print("-"*92)
    for r in c.roles:
        mismatch = any(f.code == "SIZE_RANGE_MISMATCH" for f in r.flags)
        print(f"{str(r.title)[:28]:<30}{str(r.company_size):>12}{str(r.company_size_range):>22}"
              f"{str(r.company_size_range_min)+'/'+str(r.company_size_range_max):>16}{str(mismatch):>10}")
    print("\ncontradiction flags:")
    for f in c.contradictions:
        if f.code == "SIZE_RANGE_MISMATCH":
            print(f"  {f.code}: {f.detail}")
            print(f"     provenance: {list(f.source_fields)}")
    signals = compute_signals(c, CFG)
    lead = next(s for s in signals if s.name == "leadership")
    env = next(s for s in signals if s.name == "operating_environment")
    print("\nwhich value each signal actually consumes:")
    print(f"  leadership            -> {lead.explanation}")
    print(f"     source_fields: {list(lead.source_fields)}")
    print(f"  operating_environment -> {env.explanation}")
    print(f"     source_fields: {list(env.source_fields)}")
    cb = compute_confidence(c, CFG)
    cw = CFG.weights["confidence"]["contradiction_penalties"]
    print("\nconfidence cost of each contradiction:")
    for code, n in cb.contradictions.items():
        print(f"  {code:<24} x{n}  @ {cw.get(code, 0.0)} = -{cw.get(code, 0.0)*n:.2f}")
    print(f"  total contradiction_penalty = -{cb.contradiction_penalty:.2f} "
          f"(cap {CFG.weights['confidence']['contradiction_penalty_cap']})")
    print(f"  coverage {cb.coverage:.3f} - {cb.contradiction_penalty:.3f} "
          f"- {cb.inference_penalty:.3f} = confidence {cb.confidence:.3f}")

    # counterfactual: what confidence would be without each contradiction
    print("\ncounterfactual (config penalties only, coverage held at "
          f"{cb.coverage:.3f}):")
    base = cb.coverage
    print(f"  no contradictions at all            -> {base:.3f}")
    print(f"  TOTAL_MISMATCH only                 -> {base - cw['TOTAL_MISMATCH']:.3f}")
    print(f"  SIZE_RANGE_MISMATCH x2 only         -> {base - 2*cw['SIZE_RANGE_MISMATCH']:.3f}")
    print(f"  both (actual)                       -> {cb.confidence:.3f}")


def section_f(canon):
    """Assert provenance completeness: every OBSERVED signal must cite raw JSON
    paths. Unobserved signals legitimately cite nothing — they were not
    measured, so there is nothing to point at."""
    print(f"\n{'='*118}\n### F. PROVENANCE COMPLETENESS")
    ok = True
    for c, lab in zip(canon, ["FOUNDER #1", "FOUNDER #2"]):
        print(f"\n{lab}:")
        for s in compute_signals(c, CFG):
            if not s.observed:
                print(f"  {s.name:<22} (unobserved, neutral default) sources={list(s.source_fields) or '—'}")
                continue
            bad = [p for p in s.source_fields
                   if not p.startswith(("experience[", "education[",
                                        "total_experience_duration_months"))]
            ok = ok and bool(s.source_fields) and not bad
            print(f"  {s.name:<22} value={s.value:.3f}  raw paths={list(s.source_fields)}")
            if bad:
                print(f"     !! non-raw path: {bad}")
    print(f"\nevery observed signal traceable to raw JSON paths: {ok}")


def distributions():
    """Score/confidence/per-signal distributions across the load population.

    Distribution shape only — the load population is synthetic and no
    evaluation metric is ever computed from it."""
    import statistics
    from app.normalize import normalize_corpus
    raws = load_profiles(str(ROOT / "data/synthetic/load_800.json"))
    canon = normalize_corpus(raws, CFG)
    scores, confs = [], []
    per_signal = {n: [] for n in ["founder_evidence", "healthcare_depth", "leadership",
                                  "career_trajectory", "education_signal",
                                  "operating_environment", "other"]}
    for c in canon:
        sg = compute_signals(c, CFG)
        scores.append(broad_score(sg, CFG))
        confs.append(compute_confidence(c, CFG).confidence)
        for s in sg:
            per_signal[s.name].append(s.value)
    print(f"\n{'='*118}\n### DISTRIBUTIONS ACROSS load_800 (n={len(canon)})")

    def hist(vals, lo, hi, buckets, label, width=44):
        """Print a text histogram with quartiles."""
        print(f"\n{label}: min={min(vals):.2f} p25={sorted(vals)[len(vals)//4]:.2f} "
              f"median={statistics.median(vals):.2f} "
              f"p75={sorted(vals)[3*len(vals)//4]:.2f} max={max(vals):.2f} "
              f"mean={statistics.mean(vals):.2f}")
        step = (hi - lo) / buckets
        for i in range(buckets):
            a, b = lo + i*step, lo + (i+1)*step
            n = sum(1 for v in vals if (a <= v < b) or (i == buckets-1 and v == hi))
            print(f"  [{a:6.2f},{b:6.2f}) {n:>4} {'#'*int(width*n/len(vals))}")

    hist(scores, 0, 100, 10, "broad_score")
    hist(confs, 0, 1, 10, "confidence")
    print(f"\n{'signal':<24}{'mean':>7}{'median':>8}{'observed %':>12}{'strength NONE %':>17}")
    print("-"*68)
    for n, vals in per_signal.items():
        obs = [c for c in canon]
        n_obs = sum(1 for c in canon
                    if next(s for s in compute_signals(c, CFG) if s.name == n).observed)
        print(f"{n:<24}{statistics.mean(vals):>7.3f}{statistics.median(vals):>8.3f}"
              f"{100*n_obs/len(canon):>12.1f}{100*(1-n_obs/len(canon)):>17.1f}")


if __name__ == "__main__":
    main()
