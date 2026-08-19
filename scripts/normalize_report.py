#!/usr/bin/env python3
"""Normalizer report over a population: flag counts, examples, duplicate report.

Usage: python scripts/normalize_report.py [path.json]
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.models.canonical import DuplicateRelation, FlagKind  # noqa: E402
from app.models.raw import load_profiles  # noqa: E402
from app.normalize import normalize_corpus  # noqa: E402


def main(path: str) -> None:
    """Print normalization flag counts and the duplicate report. Read-only."""
    raws = load_profiles(path)
    canon = normalize_corpus(raws)
    by_id = {c.person_id: c for c in canon}

    counts: Counter[str] = Counter()
    kinds: dict[str, str] = {}
    holders: dict[str, list[str]] = defaultdict(list)
    for c in canon:
        for code in c.flag_codes():
            counts[code] += 1
            holders[code].append(c.person_id)
        for f in c._all_flags():
            kinds[f.code] = f.kind.value

    print(f"population: {path}  n={len(canon)}")
    print(f"\n{'flag':<32}{'kind':<16}{'profiles':>9}{'share':>8}")
    print("-" * 65)
    for code, n in counts.most_common():
        print(f"{code:<32}{kinds[code]:<16}{n:>9}{n/len(canon):>8.2%}")

    clean = sum(1 for c in canon if not c._all_flags())
    print(f"\nprofiles with zero flags: {clean} ({clean/len(canon):.1%})")
    print("mean contradictions/profile:",
          round(sum(len(c.contradictions) for c in canon) / len(canon), 2))
    print("mean inferences/profile:   ",
          round(sum(len(c.inferences) for c in canon) / len(canon), 2))

    for code in ("TOTAL_MISMATCH", "AMBIGUOUS_CURRENT", "REORDERED", "OVERLAP"):
        print(f"\n### {code} — 3 examples of {counts[code]}")
        for pid in holders[code][:3]:
            c = by_id[pid]
            f = next(x for x in c._all_flags() if x.code == code)
            print(f"  {pid[:8]}…  {f.detail}")
            print(f"     sources: {list(f.source_fields)[:4]}")

    # ---- duplicates ----
    print("\n### duplicate report")
    rel_counts: Counter[str] = Counter()
    pairs: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for c in canon:
        for link in c.duplicates:
            key = tuple(sorted((c.person_id, link.other_person_id)))
            pairs[link.relation.value].add(key)
    for rel in (DuplicateRelation.SAME, DuplicateRelation.HIGH_CONFIDENCE,
                DuplicateRelation.PROBABLE, DuplicateRelation.NEVER):
        rel_counts[rel.value] = len(pairs[rel.value])
    for rel, n in rel_counts.items():
        print(f"  {rel:<18}{n:>4} pairs")
    merged = sum(1 for c in canon for link in c.duplicates if link.merged)
    print(f"  merged             {merged:>4}   <- must be 0 (A6b: flag, never merge)")
    flagged = sum(1 for c in canon if c.duplicates)
    print(f"  profiles carrying a duplicate link: {flagged}")

    for rel in ("PROBABLE", "HIGH_CONFIDENCE", "NEVER"):
        if not pairs[rel]:
            continue
        # prefer an example where both records actually carry evidence
        a, b = max(sorted(pairs[rel]),
                   key=lambda kv: min(len(by_id[kv[0]].roles), len(by_id[kv[1]].roles)))
        link = next(x for x in by_id[a].duplicates if x.other_person_id == b)
        print(f"\n  example {rel}: {a[:8]}… <-> {b[:8]}…")
        print(f"    matching={link.matching_hashes}  conflicting={link.conflicting_hashes}"
              f"  merged={link.merged}")
        for pid in (a, b):
            c = by_id[pid]
            print(f"    {pid[:8]}…  roles={len(c.roles)}  founder_roles="
                  f"{c.totals.explicit_founder_roles}  headline={c.headline!r}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "data/synthetic/load_800.json"))
