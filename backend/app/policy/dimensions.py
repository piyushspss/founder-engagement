"""The four machine dimensions — PLAN §4.5.

These four enums are the ENTIRE vocabulary the machine is allowed to speak in.
`decision` (NEEDS_REVIEW / POTENTIAL / NOT_NOW / NEEDS_INFORMATION) and `stage`
(NEW … DEAL / CLOSED) are human authority (PLAN §0, §5) and deliberately do not
exist in this package, in the Assessment model, or in anything the assessor
serialises.

The dimensions are ORTHOGONAL. That is the product point, not an implementation
detail:

* `attention` — how urgently a human must look. Recall-first: it only ever
  ratchets UP.
* `potential`  — how strong the founder-quality claim is. `UNKNOWN` is a real
  answer, not a missing one.
* `data_state` — whether we hold enough to decide at all.
* `recommended_action` — what to do next. A recommendation; never a disposition.

A founder can be `PRIORITY_REVIEW` **and** `UNKNOWN` **and** `NEEDS_INFORMATION`
at once. Any implementation in which one of these mirrors another has collapsed
the model.
"""

from __future__ import annotations

from enum import Enum


class Attention(str, Enum):
    """How urgently a human must look. A RATCHET — see `ATTENTION_ORDER`.

    Not a quality judgment: `ROUTINE` means "nothing here demands a human
    today", never "this founder is weak". Missing data therefore cannot push a
    founder DOWN this scale; under the safety policy it pushes toward REVIEW."""

    PRIORITY_REVIEW = "PRIORITY_REVIEW"
    REVIEW = "REVIEW"
    ROUTINE = "ROUTINE"


class Potential(str, Enum):
    """How strong the founder-quality claim is.

    `UNKNOWN` is a REAL answer — "we have not got enough to judge" — and is
    deliberately not a worse `LOW`. `LOW` means sufficient evidence and few
    positive signals; `UNKNOWN` means the judgment was never made. The UI is
    tested on this distinction (F-9) and must never rank UNKNOWN below LOW."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class DataState(str, Enum):
    """Whether we hold enough to decide at all — orthogonal to `potential`.

    A founder may be `PRIORITY_REVIEW` + `UNKNOWN` + `NEEDS_INFORMATION` at
    once. Absence of data is recorded here rather than being charged against
    the founder's score."""

    SUFFICIENT = "SUFFICIENT"
    PARTIAL = "PARTIAL"
    NEEDS_INFORMATION = "NEEDS_INFORMATION"


class RecommendedAction(str, Enum):
    """What the machine suggests doing next. ADVISORY ONLY.

    This is never a disposition and never a lifecycle stage: both of those are
    human authority and do not exist in this package. `CONSIDER_ENGAGEMENT` is
    a prompt to a reviewer, not a decision that engagement will happen."""

    CONSIDER_ENGAGEMENT = "CONSIDER_ENGAGEMENT"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    RESEARCH = "RESEARCH"
    NO_URGENT_ACTION = "NO_URGENT_ACTION"


# Recall-first ordering. `attention` is a RATCHET: a rule may raise it and may
# never lower it, so "we found a reason to look" can never be undone by a later
# rule finding a reason not to.
ATTENTION_ORDER: dict[Attention, int] = {
    Attention.ROUTINE: 0,
    Attention.REVIEW: 1,
    Attention.PRIORITY_REVIEW: 2,
}
