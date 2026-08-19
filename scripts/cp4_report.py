#!/usr/bin/env python3
"""CP4 evidence: exceptional detectors + archetypes, on the supplied sample and
across the synthetic load population."""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.evidence import (broad_score, compute_confidence,  # noqa: E402
                          compute_signals, detect_exceptional, label_archetype)
from app.evidence.exceptional import DETECTOR_NAMES  # noqa: E402
from app.evidence.signal import Strength  # noqa: E402
from app.models.raw import load_profiles  # noqa: E402
from app.normalize import load_config, normalize  # noqa: E402

CFG = load_config()
EX = CFG.weights["exceptional"]


def rule(char="=", n=100):
    """Print a horizontal separator."""
    print(char * n)


def full_report(c, label):
    """Print one profile's signals, exceptional detectors and archetype.

    Prints NOT-FIRED detectors too — "why is this person not flagged?" is as
    much a part of the evidence as why they are."""
    signals = compute_signals(c, CFG)
    ev = detect_exceptional(c, CFG)
    ar = label_archetype(c, signals, CFG, ev.flag)
    rule()
    print(f"### {label}   person_id={c.person_id}")
    print(f"    headline: {c.headline!r}")
    for r in c.roles:
        print(f"    role[{r.raw_index}] {r.title!r} @ {r.company!r} | level={r.management_level} "
              f"| dept={r.department} | size={r.company_size or r.company_size_range} "
              f"| {r.start_date}–{r.end_date or 'current'} | founder={r.founder_title_flag.value}")
    for e in c.education:
        print(f"    edu[{e.raw_index}] {e.degree_type.value} ({e.degree_raw!r}) | "
              f"field={e.field!r} | {e.institution!r} tier={e.institution_tier.value}")
    print(f"    broad_score={broad_score(signals, CFG)}  "
          f"confidence={compute_confidence(c, CFG).confidence}")
    rule("-")
    print(f"EXCEPTIONAL: flag={ev.flag}  rule={ev.rule}")
    for s in ev.signals:
        print(f"  FIRED {s.name}")
        print(f"        value={s.value}  strength={s.strength.value}  type={s.type.value}")
        print(f"        source_fields={list(s.source_fields)}")
        print(f"        explanation: {s.explanation}")
    for name in DETECTOR_NAMES:
        if name in ev.not_fired:
            print(f"  not fired  {name}: {ev.not_fired[name]}")
    rule("-")
    print(f"ARCHETYPE: {ar.archetype}")
    print(f"  primary: {ar.archetype}   secondary: {ar.secondary}")
    print(f"  matched: {ar.matched}   shares: {ar.shares}")
    print(f"  strong_signals: {ar.strong_signals}")
    print(f"  missing_for_archetype: {ar.missing_for_archetype}")
    print(f"  explanation: {ar.explanation}")
    return ev, ar


def main():
    """Evidence walkthrough over the supplied samples and the load population.
    Read-only; writes no file."""
    print("\n\n" + "#" * 100)
    print("# PART 1 — SUPPLIED SAMPLE PROFILES")
    print("#" * 100)
    for raw in load_profiles(str(ROOT / "data/raw/sample.json")):
        c = normalize(raw, CFG)
        full_report(c, f"SAMPLE — {raw.headline}")

    # ------------------------------------------------------------------ load
    canon = [normalize(r, CFG) for r in load_profiles(str(ROOT / "data/synthetic/load_800.json"))]
    results = []
    for c in canon:
        signals = compute_signals(c, CFG)
        ev = detect_exceptional(c, CFG)
        ar = label_archetype(c, signals, CFG, ev.flag)
        results.append((c, signals, ev, ar))

    print("\n\n" + "#" * 100)
    print("# PART 2 — HAND-PICKED load_800 RECORDS")
    print("#" * 100)

    def pick(pred, label, n=1):
        """Show up to `n` records matching `pred`, or say plainly that there are
        none. An absent category is REPORTED, never manufactured."""
        hits = [t for t in results if pred(t)]
        print(f"\n>>> {label}  ({len(hits)} such records in load_800)")
        for c, _s, _e, _a in hits[:n]:
            full_report(c, label)
        if not hits:
            print("    NONE FOUND in load_800 — reported, not manufactured.")

    def cats(ev):
        """The set of detector names that fired."""
        return set(ev.categories)

    pick(lambda t: "repeat_founder" in cats(t[2]), "A. REPEAT FOUNDER")
    pick(lambda t: (any(r.leadership_title and r.founder_title_flag.value == "NONE"
                        for r in t[0].roles)
                    and t[0].totals.explicit_founder_roles == 0),
         "B. CEO / PRESIDENT / MD — NOT A FOUNDER")
    pick(lambda t: "exceptional_progression" in cats(t[2]), "C. RAPID PROGRESSION")
    pick(lambda t: "major_leadership_scope" in cats(t[2]), "D. MAJOR LEADERSHIP SCOPE")
    pick(lambda t: "exceptional_credential" in cats(t[2])
         or "rare_domain_expertise" in cats(t[2]), "E. CREDENTIAL / RARE DOMAIN")
    pick(lambda t: (not t[2].flag and broad_score(t[1], CFG) >= 60), "F. STRONG BUT NOT EXCEPTIONAL")
    pick(lambda t: "exit_cue" in cats(t[2]), "G. EXIT CUE")

    # ------------------------------------------------- population sanity table
    print("\n\n" + "#" * 100)
    print("# PART 3 — POPULATION SANITY (load_800)")
    print("#" * 100)
    n = len(results)
    det = Counter()
    for _c, _s, ev, _a in results:
        det.update(ev.categories)
    print(f"\nN = {n} synthetic profiles\n")
    print(f"{'detector':<28}{'fired':>7}{'% of pop':>10}  configured strength")
    rule("-", 70)
    strengths = EX["detector_strengths"]
    for name in DETECTOR_NAMES:
        print(f"{name:<28}{det[name]:>7}{100*det[name]/n:>9.1f}%  {strengths[name]}")

    flagged = [t for t in results if t[2].flag]
    print(f"\nexceptional flag = True: {len(flagged)} / {n}  ({100*len(flagged)/n:.1f}%)")
    by_route = Counter("STRONG" if t[2].rule.startswith("STRONG") else "2+ MEDIUM"
                       for t in flagged)
    for k, v in by_route.items():
        print(f"  via {k:<12}{v:>5}  ({100*v/n:.1f}% of population)")

    print(f"\n{'signals per profile':<28}{'count':>7}{'% of pop':>10}")
    rule("-", 46)
    for k, v in sorted(Counter(len(t[2].signals) for t in results).items()):
        print(f"{k} exceptional signal(s){'':<6}{v:>7}{100*v/n:>9.1f}%")

    print(f"\n{'strength band':<28}{'signals':>8}")
    rule("-", 38)
    band = Counter(s.strength.value for t in results for s in t[2].signals)
    for k in ("STRONG", "MEDIUM", "WEAK"):
        print(f"{k:<28}{band.get(k, 0):>8}")

    founders = [t for t in results if t[0].totals.explicit_founder_roles > 0]
    fex = [t for t in founders if t[2].flag]
    print(f"\nprofiles with >=1 EXPLICIT founder role: {len(founders)}")
    print(f"  of those, exceptional flag = True:      {len(fex)}"
          f"  ({100*len(fex)/len(founders):.1f}% of founders)" if founders else "")

    print(f"\n{'archetype':<28}{'count':>7}{'% of pop':>10}")
    rule("-", 46)
    for name, cnt in Counter(t[3].archetype for t in results).most_common():
        print(f"{name:<28}{cnt:>7}{100*cnt/n:>9.1f}%")

    print(f"\n{'archetype (all matches)':<28}{'count':>7}")
    rule("-", 38)
    allm = Counter(m for t in results for m in t[3].matched)
    for name, cnt in allm.most_common():
        print(f"{name:<28}{cnt:>7}")

    # -------------------------------------------------- detector breadth check
    print("\n\n" + "#" * 100)
    print("# PART 4 — DETECTOR BREADTH (reviewer decision, NOT tuned)")
    print("#" * 100)
    print("\nA detector firing on a large share of an ordinary population is a")
    print("candidate for being too broad. Reported for reviewer decision only.\n")
    print(f"{'detector':<28}{'% of pop':>10}  note")
    rule("-", 100)
    for name in DETECTOR_NAMES:
        pct = 100 * det[name] / n
        note = ("BROAD — fires on more than a third of an ordinary population"
                if pct > 33 else
                "wide" if pct > 15 else
                "zero fires — reported honestly" if pct == 0 else "narrow")
        print(f"{name:<28}{pct:>9.1f}%  {note}")

    # clinicians vs credential detector
    clinical = [t for t in results
                if {e.degree_type.value for e in t[0].education} & {"MD", "DO", "RN", "BSN"}]
    md_phd = [t for t in results
              if {e.degree_type.value for e in t[0].education} & {"MD", "PhD", "DO"}]
    print(f"\nprofiles with a clinical degree (MD/DO/RN/BSN): {len(clinical)}")
    print(f"profiles with MD/PhD/DO (the configured credential list): {len(md_phd)}"
          f"  -> exceptional_credential fires on exactly these {det['exceptional_credential']}")
    print("Every clinician is NOT made exceptional: RN/BSN are not in the configured")
    print("credential list, and a single MEDIUM detector never sets the flag.")


if __name__ == "__main__":
    main()
