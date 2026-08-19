"""Conservative duplicate detection — PLAN A6b.

Nothing is ever merged in the MVP. The detector's job is to *flag* so a human
can decide; silently merging two records is how a good founder's evidence gets
lost, which is the exact failure mode this system exists to avoid.

Hash strength:
  strong  — identifies an account/person directly (linkedin, email, public
            profile, github, crunchbase)
  weak    — consistent with, but not evidence of, the same person (name hash,
            professional email pool)

Classification, in order:
  1. same mdm_person_id                          -> SAME
  2. >= 2 matching strong hashes                 -> HIGH_CONFIDENCE  (flag, do not merge)
  3. exactly 1 matching strong hash              -> PROBABLE         (flag, do not merge)
  4. 0 strong matches, a weak match, and at
     least one strong hash present-and-different -> NEVER            (never merge, never assert;
                                                    reason = CONFLICTING_IDENTITY_HASHES)
  5. otherwise                                   -> no link
"""

from __future__ import annotations

from collections import defaultdict

from app.models.canonical import (DuplicateLink, DuplicateRelation, Flag,
                                  FlagCode, FlagKind)
from app.models.raw import RawProfile

STRONG_HASHES = ("linkedin_hash", "email_hash", "public_profile_id_hash",
                 "github_hash", "crunchbase_hash")
WEAK_HASHES = ("name_hash", "phone_hash", "twitter_hash", "facebook_hash")


def _pairwise(a: RawProfile, b: RawProfile) -> tuple[list[str], list[str], list[str]]:
    """Compare identity hashes: (strong matches, strong CONFLICTS, weak matches).

    Conflicts are collected as carefully as matches — two records that disagree
    on a strong hash are positive evidence of being different people."""
    matches, conflicts, weak = [], [], []
    for field in STRONG_HASHES:
        va, vb = getattr(a, field), getattr(b, field)
        if va and vb:
            (matches if va == vb else conflicts).append(field)
    for field in WEAK_HASHES:
        va, vb = getattr(a, field), getattr(b, field)
        if va and vb and va == vb:
            weak.append(field)
    pa = set(a.professional_emails_hashed or [])
    pb = set(b.professional_emails_hashed or [])
    if pa & pb:
        weak.append("professional_emails_hashed")
    return matches, conflicts, weak


def classify_pair(a: RawProfile, b: RawProfile) -> tuple[DuplicateRelation | None, list[str], list[str]]:
    """Classify one pair. Conservative by design (A6b): the result is a FLAG for
    a human, never an automatic merge.

    `NEVER` is the notable case — weak agreement plus a strong CONFLICT means
    "looks similar, provably not the same person", which is a stronger claim
    than simply returning no link."""
    if a.mdm_person_id and a.mdm_person_id == b.mdm_person_id:
        return DuplicateRelation.SAME, ["mdm_person_id"], []

    matches, conflicts, weak = _pairwise(a, b)
    if len(matches) >= 2:
        return DuplicateRelation.HIGH_CONFIDENCE, matches, conflicts
    if len(matches) == 1:
        return DuplicateRelation.PROBABLE, matches, conflicts
    if weak and conflicts:
        return DuplicateRelation.NEVER, weak, conflicts
    return None, [], []


def find_duplicates(profiles: list[RawProfile]) -> dict[str, list[DuplicateLink]]:
    """Returns person_id -> links. Candidate pairs come from an inverted index on
    hash values, so this is near-linear rather than 800^2."""
    index: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, p in enumerate(profiles):
        for field in STRONG_HASHES + WEAK_HASHES:
            if v := getattr(p, field):
                index[(field, v)].append(i)
        for v in p.professional_emails_hashed or []:
            index[("professional_emails_hashed", v)].append(i)

    candidates: set[tuple[int, int]] = set()
    for bucket in index.values():
        if len(bucket) < 2:
            continue
        for x in range(len(bucket)):
            for y in range(x + 1, len(bucket)):
                candidates.add((bucket[x], bucket[y]))

    links: dict[str, list[DuplicateLink]] = defaultdict(list)
    for i, j in sorted(candidates):
        a, b = profiles[i], profiles[j]
        relation, matching, conflicting = classify_pair(a, b)
        if relation is None:
            continue
        ida = a.mdm_person_id or f"idx:{i}"
        idb = b.mdm_person_id or f"idx:{j}"
        links[ida].append(DuplicateLink(other_person_id=idb, relation=relation,
                                        matching_hashes=matching,
                                        conflicting_hashes=conflicting, merged=False))
        links[idb].append(DuplicateLink(other_person_id=ida, relation=relation,
                                        matching_hashes=matching,
                                        conflicting_hashes=conflicting, merged=False))
    return dict(links)


def duplicate_flags(links: list[DuplicateLink]) -> list[Flag]:
    """Turn links into flags. A conflicting pair is a CONTRADICTION (the identity
    data disagrees); a probable/high-confidence pair is a QUALITY observation for
    the UI's 'Possible duplicate detected'."""
    flags: list[Flag] = []
    for link in links:
        if link.relation is DuplicateRelation.NEVER:
            flags.append(Flag(
                code=FlagCode.CONFLICTING_IDENTITY_HASHES,
                kind=FlagKind.CONTRADICTION,
                detail=(f"shares {', '.join(link.matching_hashes)} with {link.other_person_id} "
                        f"but {', '.join(link.conflicting_hashes)} differ — not treated as a duplicate"),
                source_fields=tuple(link.matching_hashes + link.conflicting_hashes),
            ))
        elif link.relation in (DuplicateRelation.PROBABLE,
                               DuplicateRelation.HIGH_CONFIDENCE,
                               DuplicateRelation.SAME):
            flags.append(Flag(
                code=FlagCode.POSSIBLE_DUPLICATE,
                kind=FlagKind.QUALITY,
                detail=(f"{link.relation.value} duplicate of {link.other_person_id} "
                        f"on {', '.join(link.matching_hashes)} — flagged, not merged"),
                source_fields=tuple(link.matching_hashes),
                value=link.relation.value,
            ))
    return flags
