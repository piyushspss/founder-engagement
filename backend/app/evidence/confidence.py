"""Confidence — PLAN §4.3 (amended, PLAN v2.2 Amendment 1).

Confidence answers "how much of what we would need in order to decide is
actually here?", not "how many fields are populated".

    confidence = coverage − contradiction_penalty − inference_penalty   (clamped 0–1)

**Amendment 1 (v2.2), discovered at CP5 as finding F-1.** The seven top-level
coverage weights are UNCHANGED (30/10/15/10/15/15/5) and are not retuned. What
changed is what each component *measures*. Before the amendment, a component
could be satisfied by the mere existence of an `experience[]` object: deleting
`management_level` from every role removed 30 of the 100 broad-score points —
all of `leadership` and all of `career_trajectory` — and moved confidence by
*exactly zero*, because no component read it. Evidence vanished and the system
reported the same certainty as before.

The rule now enforced, and proved by test: **every evidence family that
materially feeds a deterministic signal must feed at least one coverage
component.** Coverage measures the availability of the evidence needed to
evaluate a dimension, not the presence of a container.

Each top-level component is the unweighted mean of named sub-components, all of
which are reported in the breakdown, so the source → component matrix is
readable straight off a live assessment rather than only out of this docstring.

Two deliberate exclusions, both about the difference between *availability* and
*recognisability*:

* **Institution TIER is not a coverage input.** A school that is not on the tier
  list is still an institution we can read; A7 fixes unknown as neutral, which is
  a valid evaluated outcome, not a gap. Scoring coverage on the tier list would
  make confidence a measure of how large our starter list is — on load_800 it
  would call 45.5% of education entries "missing" when the field is right there.
  What IS covered is that an institution name and an interpretable degree exist.
* **An unrecognised value is a coverage reduction, never negative evidence.** A
  `management_level` outside the known taxonomy, or an industry we cannot
  classify, genuinely leaves the dimension unevaluable, so it lowers coverage.
  It never lowers a signal below its neutral floor (PLAN §1, enforced in
  `signals.py`).

Confidence remains the ONLY place data quality enters the maths, and it still
never touches `potential` directly. Under v2.2 the two are linked in one
direction only, by safety guard 5 in `policy/safety.py`: low confidence forces
`potential = UNKNOWN`. That is uncertainty refusing to make a claim, not data
quality being scored as founder quality.
"""

from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, Field

from app.evidence.progression import LEVEL_RANK
from app.models.canonical import (CanonicalProfile, DegreeType, FlagKind,
                                  Ternary)


class ConfidenceBreakdown(BaseModel):
    """The full confidence computation, kept in parts rather than collapsed.

    Every term is reported so a reviewer can see WHICH gap or contradiction cost
    the confidence, rather than being handed a single number. Confidence is the
    only place data quality enters the maths, and it never touches `potential`
    directly — the one link is safety guard 5 (low confidence forces UNKNOWN),
    which is uncertainty declining to make a claim, not data quality being
    scored as founder quality."""

    coverage: float
    contradiction_penalty: float
    inference_penalty: float
    confidence: float
    coverage_components: dict[str, float]
    # v2.2: the sub-components each top-level component is the mean of. This is
    # the source -> coverage matrix, computed rather than documented.
    coverage_subcomponents: dict[str, dict[str, float]] = Field(default_factory=dict)
    contradictions: dict[str, int]
    inferences: dict[str, int]


def _fraction(numerator: int, denominator: int) -> float:
    """0/0 is 0.0: no items means no evidence, which is exactly what coverage
    should report. It is not 1.0 ('vacuously complete')."""
    return 0.0 if denominator <= 0 else numerator / denominator


def _mean(parts: dict[str, float]) -> float:
    """Unweighted mean of a component's sub-components; {} is 0.0."""
    return sum(parts.values()) / len(parts) if parts else 0.0


def coverage_subcomponents(profile: CanonicalProfile) -> dict[str, dict[str, float]]:
    """The source → coverage matrix, as numbers. Each inner dict is the set of
    evidence families feeding one top-level §4.3 component; the component is
    their unweighted mean.

    Every sub-component is in 0–1 and is a statement about AVAILABILITY of
    evidence, never about how good that evidence is.
    """
    roles = profile.roles
    n = len(roles)
    edu = profile.education

    # -- experience_history (30) : is there a usable career history to read? ---
    if n == 0:
        history_depth = 0.0
    elif n == 1:
        history_depth = 0.5   # one role tells us where they are, not how they got there
    else:
        history_depth = 1.0

    experience_history = {
        # PLAN §4.5 rule 5 / data_state NEEDS_INFORMATION keys on THIS
        # sub-component alone (interpretation I-3'), so enriching the component
        # around it cannot change what "experience history missing/incomplete"
        # means.
        "history_depth": history_depth,
        # feeds `leadership` (15 pts) and `career_trajectory` (15 pts) — the
        # 30 points that used to be invisible to confidence (F-1).
        "seniority_readability": _fraction(
            sum(1 for r in roles if r.management_level in LEVEL_RANK), n),
        # feeds `healthcare_depth`, `founder_evidence` tenure bonus and `other`
        "tenure_readability": _fraction(
            sum(1 for r in roles if r.duration_months is not None), n),
    }

    # -- current_role (10) : do we know whether the latest role is ongoing? ----
    current_role = {
        "is_current_known": (1.0 if roles and roles[0].is_current in
                             (Ternary.YES, Ternary.NO) else 0.0),
    }

    # -- chronology (15) : can the roles be placed in time? -------------------
    dated = _fraction(sum(1 for r in roles if r.start_date), n)
    inferred = _fraction(sum(1 for r in roles if r.start_date
                             and r.start_date.inferred_month), n)
    chronology = {
        # A date whose month we inferred still places the role, but only partly.
        "start_dates_readable": max(0.0, dated - 0.5 * inferred),
    }

    # -- education (10) : is the education legible? ---------------------------
    education = {
        "education_present": 1.0 if edu else 0.0,
        # availability of the institution, NOT its tier (see module docstring)
        "institution_present": _fraction(sum(1 for e in edu if e.institution), len(edu)),
        # a credential we cannot parse leaves the dimension unevaluable
        "degree_interpretable": _fraction(
            sum(1 for e in edu if e.degree_type is not DegreeType.OTHER), len(edu)),
    }

    # -- company_domain_classification (15) : can we place the employers? -----
    company_domain = {
        # feeds `healthcare_depth` (20 pts)
        "industry_classified": _fraction(
            sum(1 for r in roles if r.health_flag is not Ternary.UNKNOWN), n),
        # feeds `operating_environment` (10 pts) and the `leadership` scope bonus
        "scope_available": _fraction(
            sum(1 for r in roles
                if r.company_size is not None or r.company_size_range_min is not None), n),
    }

    # -- founder_evidence (15) : can founding be ruled in or out? -------------
    founder_evidence = {
        # A missing title is the case where we genuinely cannot decide (A8).
        "titles_readable": _fraction(sum(1 for r in roles if r.title), n),
    }

    # -- other (5) : the inputs the `other` signal reads ----------------------
    other = {
        "total_experience_stated": 1.0 if profile.totals.stated_total_months is not None else 0.0,
        "location_known": 1.0 if (profile.location_country or profile.location_city) else 0.0,
        # breadth is counted from distinct industries, so the raw strings matter
        # even where the health classifier could not place them.
        "breadth_inputs_readable": _fraction(sum(1 for r in roles if r.industry), n),
    }

    return {
        "experience_history": experience_history,
        "current_role": current_role,
        "chronology": chronology,
        "education": education,
        "company_domain_classification": company_domain,
        "founder_evidence": founder_evidence,
        "other": other,
    }


def coverage_components(profile: CanonicalProfile) -> dict[str, float]:
    """Each top-level component is the unweighted mean of its sub-components.
    Weights (unchanged from §4.3) are applied by the caller."""
    return {k: _mean(v) for k, v in coverage_subcomponents(profile).items()}


def history_depth(profile: CanonicalProfile) -> float:
    """The sub-component PLAN §4.5 rule 5 keys on (I-3'). Exposed as a named
    function so the policy condition and the data_state ladder read the same
    number and cannot drift apart."""
    return coverage_subcomponents(profile)["experience_history"]["history_depth"]


def compute_confidence(profile: CanonicalProfile, cfg) -> ConfidenceBreakdown:
    """coverage − contradiction_penalty − inference_penalty, clamped to 0–1.

    Missing evidence lands HERE, as reduced coverage, and nowhere else: it is
    never charged against a signal value and never becomes negative evidence
    about the founder. Both penalties are capped in config so no single messy
    record can drive confidence to zero on penalties alone.

    Note the deliberate non-monotonicity (F-6, accepted): removing the field
    that CARRIES a contradiction can RAISE confidence, because the remaining
    record is internally consistent. Recall safety does not depend on confidence
    being monotonic under deletion — it is enforced structurally by coverage,
    `data_state` and the guard-4 attention floor."""
    conf_cfg = cfg.weights["confidence"]
    weights = conf_cfg["coverage_weights"]
    total_weight = sum(weights.values())

    subs = coverage_subcomponents(profile)
    components = {k: _mean(v) for k, v in subs.items()}
    coverage = sum(weights[k] * v for k, v in components.items()) / total_weight

    contradiction_counts = Counter(
        f.code for f in profile._all_flags() if f.kind is FlagKind.CONTRADICTION)
    inference_counts = Counter(
        f.code for f in profile._all_flags() if f.kind is FlagKind.INFERENCE)

    c_table = conf_cfg["contradiction_penalties"]
    i_table = conf_cfg["inference_penalties"]
    contradiction_penalty = min(
        conf_cfg["contradiction_penalty_cap"],
        sum(c_table.get(code, 0.0) * count for code, count in contradiction_counts.items()))
    inference_penalty = min(
        conf_cfg["inference_penalty_cap"],
        sum(i_table.get(code, 0.0) * count for code, count in inference_counts.items()))

    confidence = max(0.0, min(1.0, coverage - contradiction_penalty - inference_penalty))
    return ConfidenceBreakdown(
        coverage=round(coverage, 4),
        contradiction_penalty=round(contradiction_penalty, 4),
        inference_penalty=round(inference_penalty, 4),
        confidence=round(confidence, 4),
        coverage_components={k: round(v, 4) for k, v in components.items()},
        coverage_subcomponents={k: {kk: round(vv, 4) for kk, vv in v.items()}
                                for k, v in subs.items()},
        contradictions=dict(contradiction_counts),
        inferences=dict(inference_counts),
    )
