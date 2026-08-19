"""The machine pipeline behind /import and /rescore.

    stored raw profile -> normalize (under the EFFECTIVE config)
                       -> evidence/assessment -> safety policy -> persist

Re-normalising from raw is not an optimisation detail. Tier lists and the health
taxonomy are *normalization* inputs, not just scoring inputs (RUNBOOK CP7 §2):
rescoring a stored canonical snapshot would silently miss a config change that
moved an institution between tiers. Raw is the only durable truth.

Everything in this module is machine-owned. It writes `founders` rows and
RESCORE audit events. It contains no code path that can create, alter or delete
a `decisions` or `workflow` row — the neutral `NEW` workflow created alongside a
brand-new founder is the single, deliberate exception (PLAN §5: a founder has to
be somewhere), and it is never touched again by any machine path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assessment import ASSESSMENT_VERSION, Assessment, assess
from app.db.models import AuditLog, Founder, Stage, Workflow, utcnow
from app.models.canonical import CanonicalProfile
from app.models.raw import RawProfile
from app.normalize.config import Config
from app.normalize.dedup import duplicate_flags, find_duplicates
from app.normalize.normalizer import normalize

SYSTEM_ACTOR = "system"


def stable_person_id(raw: RawProfile, fallback_index: int) -> str:
    """`mdm_person_id` is identity (A6b). Records that carry none get a stable
    content hash rather than a positional id, so re-importing the same anonymous
    record does not create a second founder."""
    if raw.mdm_person_id:
        return raw.mdm_person_id
    import hashlib
    import json
    blob = json.dumps(raw.raw_dict(), sort_keys=True, default=str)
    return "anon:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


@dataclass
class Evaluated:
    """One founder's complete machine evaluation, before persistence.

    Machine-owned throughout: there is deliberately no decision, stage, owner or
    note field here, so nothing downstream can persist human state by accident."""

    person_id: str
    raw: RawProfile
    canonical: CanonicalProfile
    assessment: Assessment
    duplicates: list[dict[str, Any]] = field(default_factory=list)


def evaluate_corpus(raws: list[RawProfile], ids: list[str], cfg: Config) -> list[Evaluated]:
    """Normalize + dedup + assess a whole corpus together.

    Dedup is corpus-level by nature, so the caller must pass every record that
    should be able to see every other one (on import: stored ∪ incoming)."""
    canon = [normalize(r, cfg, person_id=pid) for r, pid in zip(raws, ids)]

    # find_duplicates keys on mdm_person_id or a positional fallback; remap onto
    # our stable ids so anonymous records still link correctly.
    key_to_id = {(r.mdm_person_id or f"idx:{i}"): ids[i] for i, r in enumerate(raws)}
    links = find_duplicates(raws)

    out: list[Evaluated] = []
    for i, (raw, prof) in enumerate(zip(raws, canon)):
        key = raw.mdm_person_id or f"idx:{i}"
        found = links.get(key, [])
        for link in found:
            link.other_person_id = key_to_id.get(link.other_person_id, link.other_person_id)
        if found:
            prof.duplicates = found
            prof.flags.extend(duplicate_flags(found))
        out.append(Evaluated(
            person_id=ids[i], raw=raw, canonical=prof, assessment=assess(prof, cfg),
            duplicates=[link.model_dump(mode="json") for link in found]))
    return out


# --------------------------------------------------------------- persistence
def write_assessment(founder: Founder, ev: Evaluated, *, first: bool) -> None:
    """Machine-owned columns only. Note what is absent: no stage, no owner, no
    disposition, no notes."""
    founder.raw_json = ev.raw.raw_dict()
    founder.canonical_json = ev.canonical.model_dump(mode="json")
    founder.assessment_json = ev.assessment.to_dict()
    founder.duplicate_flags = ev.duplicates
    founder.rubric_version = ev.assessment.rubric_version
    founder.engine_version = ASSESSMENT_VERSION
    founder.assessed_at = utcnow()
    founder.assessment_version = 1 if first else (founder.assessment_version or 0) + 1
    founder.updated_at = utcnow()


def create_founder(session: Session, ev: Evaluated, *, source: str | None,
                   funnel: str | None) -> Founder:
    """Insert a new founder plus its Workflow row at the neutral `NEW` stage.

    The new founder has NO human decision. `NEW` is the pre-human creation
    default — a founder has to be somewhere — and is explicitly not an
    assessment-driven recommendation; no machine path may move it afterwards."""
    founder = Founder(
        id=ev.person_id, mdm_person_id=ev.raw.mdm_person_id, raw_json={}, canonical_json={},
        assessment_json={}, rubric_version="", source=source, funnel=funnel,
        created_at=utcnow(), updated_at=utcnow())
    write_assessment(founder, ev, first=True)
    session.add(founder)
    # PLAN §5: a founder must be somewhere. NEW is the neutral, pre-human state —
    # it is NOT an assessment-driven lifecycle recommendation, and no machine
    # path may move it afterwards.
    session.add(Workflow(founder_id=founder.id, stage=Stage.NEW.value, notes=[],
                         stage_changed_at=utcnow(), created_at=utcnow(), updated_at=utcnow()))
    session.flush()
    return founder


def load_all_founders(session: Session) -> list[Founder]:
    """Every founder, ordered by id so corpus operations are reproducible."""
    return list(session.execute(select(Founder).order_by(Founder.id)).scalars())


def audit_rescore(session: Session, founder: Founder, actor: str, from_rubric: str,
                  to_rubric: str, reason: str | None) -> None:
    """Record a RESCORE audit event: assessment version and rubric, before → after.

    A machine event about a machine field. It is not a decision event and never
    appears as one; the audit trail keeps machine and human events distinct."""
    session.add(AuditLog(
        founder_id=founder.id, actor=actor, event="RESCORE", field="assessment",
        from_value=f"v{founder.assessment_version - 1} rubric {from_rubric[:12]}",
        to_value=f"v{founder.assessment_version} rubric {to_rubric[:12]}",
        reason=reason or "explicit rescore", created_at=utcnow()))
