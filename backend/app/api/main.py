"""FastAPI application — RUNBOOK CP7 §5.

Route inventory, and which side of the machine/human line each one sits on:

    machine   POST /import            raw -> normalize -> dedup -> assess -> store
    machine   POST /rescore           re-run the pipeline under the effective config
    machine   GET  /config            the effective rubric
    machine   PUT  /config            change it; does NOT rescore, does NOT touch humans
    read      GET  /queue             prioritised work list
    read      GET  /founders/{id}     separated sections: facts / assessment / human
    read      GET  /dashboard         operating metrics
    read      GET  /audit/{id}        who changed what, when, why
    HUMAN     POST /founders/{id}/decision
    HUMAN     POST /founders/{id}/stage
    HUMAN     POST /founders/{id}/notes
    HUMAN     PATCH /founders/{id}/workflow      (owner / next_action only)

The four HUMAN routes are the only code paths in the application that write to
`decisions` or `workflow`. No route reads `recommended_action` and acts on it:
the machine recommends, a person decides.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from typing import Any

from fastapi import (Body, Depends, FastAPI, File, HTTPException, Query,
                     Request, UploadFile)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (ConfigPutRequest, DecisionRequest, ImportRequest,
                             NoteRequest, RescoreRequest, StageRequest,
                             WorkflowPatchRequest)
from app.db.base import init_db, session_factory
from app.llm.provider import default_adapter
from app.llm.prompt import PROMPT_VERSION, prompt_sha256
from app.llm.service import run_ai_check
from app.db.models import Founder
from app.models.canonical import CanonicalProfile
from app.services import views
from app.services.config_service import (ConfigValidationError, apply_patch,
                                         effective_config, get_runtime_row)
from app.services.pipeline import (ImportError_, import_profiles, parse_csv,
                                   parse_json, rescore_all)
from app.services.workflow_service import (WorkflowError, append_note,
                                           change_stage, patch_workflow,
                                           record_decision)

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Create tables on startup. Idempotent — safe on an existing database."""
    init_db()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Founder Engagement Workflow",
    version="cp7",
    description="Human-in-the-loop founder engagement. The machine assesses; "
                "people decide. docs/PLAN.md v2.3 (FROZEN).",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])


def get_db() -> Session:
    """Request-scoped session: commit on success, roll back on ANY exception.

    This is what makes a rejected human mutation leave no trace — the workflow
    service raises before or during the write and the whole request unwinds."""
    session = session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _founder(session: Session, founder_id: str) -> Founder:
    """Load a founder or raise 404."""
    f = session.get(Founder, founder_id)
    if f is None:
        raise HTTPException(status_code=404, detail=f"founder {founder_id!r} not found")
    return f


@app.exception_handler(WorkflowError)
async def _workflow_error(_: Request, exc: WorkflowError) -> JSONResponse:
    """Rejected human mutation → 409 (illegal transition) or 400 (bad request).

    Reports the error code and message only; no environment, no configuration
    and no secret is ever included in an error body."""
    # 409 for a rejected transition, 400 for a malformed request. Either way the
    # transaction is rolled back by the dependency, so nothing was written.
    status = 409 if exc.code in ("invalid_transition", "no_op") else 400
    return JSONResponse(status_code=status,
                        content={"error": exc.code, "detail": str(exc)})


@app.exception_handler(ConfigValidationError)
async def _config_error(_: Request, exc: ConfigValidationError) -> JSONResponse:
    """Invalid config patch → 422 with the per-field errors, nothing else."""
    return JSONResponse(status_code=422,
                        content={"error": "invalid_config", "errors": exc.errors})


@app.exception_handler(ImportError_)
async def _import_error(_: Request, exc: ImportError_) -> JSONResponse:
    """Invalid import payload → 422 with the per-record errors, nothing else."""
    return JSONResponse(status_code=422,
                        content={"error": "invalid_payload", "errors": exc.errors})


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}


# ------------------------------------------------------------------- machine
@app.post("/import", tags=["machine"])
async def import_endpoint(request: Request, session: Session = Depends(get_db),
                          file: UploadFile | None = File(default=None),
                          source: str | None = Query(default=None),
                          funnel: str | None = Query(default=None)) -> dict[str, Any]:
    """JSON body (`{profiles: [...]}` or a bare array) or a multipart CSV/JSON file."""
    if file is not None:
        payload = (await file.read()).decode("utf-8")
        name = (file.filename or "").lower()
        raws = parse_csv(payload) if name.endswith(".csv") else parse_json(json.loads(payload))
        source = source or file.filename
    else:
        body = await request.json()
        if isinstance(body, dict) and "profiles" in body:
            try:
                parsed = ImportRequest.model_validate(body)
            except ValidationError as exc:
                # An unknown top-level key on an import is refused, not ignored.
                # `stage` / `decision` arriving with machine input is exactly the
                # thing this endpoint must never quietly accept.
                raise ImportError_([f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
                                    for e in exc.errors()]) from exc
            raws = parse_json(parsed.profiles)
            source = source or parsed.source
            funnel = funnel or parsed.funnel
        else:
            raws = parse_json(body)
    cfg = effective_config(session)
    report = import_profiles(session, raws, cfg, source=source, funnel=funnel)
    return report.to_dict()


@app.post("/rescore", tags=["machine"])
def rescore_endpoint(body: RescoreRequest | None = Body(default=None),
                     session: Session = Depends(get_db)) -> dict[str, Any]:
    """Re-run the machine pipeline for every founder under the effective config.

    Human state is not in the write set. One transaction: if any founder fails,
    the whole rescore is rolled back."""
    body = body or RescoreRequest()
    cfg = effective_config(session)
    report = rescore_all(session, cfg, actor=body.actor, reason=body.reason)
    return report.to_dict()


@app.get("/config", tags=["machine"])
def get_config(session: Session = Depends(get_db)) -> dict[str, Any]:
    """The effective rubric plus read-only AI-layer STATUS.

    `ai_layer` is status, not configuration: it never enters the scoring rubric,
    `rubric_version`, `assessment_version` or rescore semantics (F-24), and it
    exposes no credential — provider name, availability, model and prompt
    version/hash only, never an API key or any part of one."""
    row = get_runtime_row(session)
    # `ai_layer` is read-only status, not configuration: it lets the UI label the
    # optional AI action honestly ("unavailable" / "Mock" / "Run") before a
    # person spends a call on it. It changes no rubric and enters no hash.
    adapter = default_adapter()
    available = adapter.available()
    return {"rubric_version": row.rubric_version, "updated_at": row.updated_at,
            "updated_by": row.updated_by, "config": row.sections_json,
            "ai_layer": {
                "provider": adapter.provider,
                "available": available,
                "detail": ("" if available
                           else getattr(adapter, "last_error", None)
                           or "no AI provider is configured"),
                "prompt_version": PROMPT_VERSION,
                "prompt_sha256": prompt_sha256(),
            }}


@app.put("/config", tags=["machine"])
def put_config(body: ConfigPutRequest, session: Session = Depends(get_db)) -> dict[str, Any]:
    """Validate + persist the effective config. Explicitly does NOT rescore and
    does NOT touch decisions or workflow — call POST /rescore for that."""
    before = get_runtime_row(session).rubric_version
    row = apply_patch(session, body.config, body.actor)
    return {"rubric_version_before": before, "rubric_version": row.rubric_version,
            "rescored": False, "config": row.sections_json,
            "note": "Config updated. No founder was rescored and no human state changed. "
                    "POST /rescore to re-evaluate under this config."}


# ---------------------------------------------------------------------- read
@app.get("/queue", tags=["read"])
def queue(session: Session = Depends(get_db),
          attention: list[str] | None = Query(default=None),
          data_state: list[str] | None = Query(default=None),
          stage: list[str] | None = Query(default=None),
          owner: str | None = Query(default=None),
          due: bool | None = Query(default=None),
          as_of: date | None = Query(default=None),
          limit: int = Query(default=100, ge=1, le=1000),
          offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
    """The priority queue. Every filter is server-side; `as_of` is a read lens
    and an unparseable date is rejected with 422, never treated as today."""
    return views.list_queue(session, attention=attention, data_state=data_state,
                            stage=stage, owner=owner, due=due, as_of=as_of,
                            limit=limit, offset=offset)


@app.get("/founders/{founder_id}", tags=["read"])
def founder_detail(founder_id: str, as_of: date | None = Query(default=None),
                   session: Session = Depends(get_db)) -> dict[str, Any]:
    """Facts, assessment, metadata, human decision, workflow and duplicates."""
    return views.founder_detail(session, _founder(session, founder_id), as_of)


@app.get("/dashboard", tags=["read"])
def dashboard(stuck_days: int = Query(default=views.DEFAULT_STUCK_DAYS, ge=1),
              as_of: date | None = Query(default=None),
              session: Session = Depends(get_db)) -> dict[str, Any]:
    """Operating dashboard. `stuck_days` is a display threshold and never enters
    `rubric_version`."""
    return views.dashboard(session, stuck_days=stuck_days, as_of=as_of)


@app.get("/audit/{founder_id}", tags=["read"])
def audit(founder_id: str, session: Session = Depends(get_db)) -> dict[str, Any]:
    """Who changed what, when and why — machine and human events in one trail."""
    _founder(session, founder_id)
    return {"founder_id": founder_id, "events": views.audit_trail(session, founder_id)}


# --------------------------------------------------------------------- human
@app.post("/founders/{founder_id}/decision", tags=["human"])
def post_decision(founder_id: str, body: DecisionRequest,
                  session: Session = Depends(get_db)) -> dict[str, Any]:
    """HUMAN — record a disposition. One of only four routes that may write
    human state. Changes no assessment field and no stage."""
    founder = _founder(session, founder_id)
    row = record_decision(session, founder, disposition=body.disposition,
                          actor=body.actor, reason=body.reason)
    session.refresh(founder)          # the append-only history just grew
    return {"founder_id": founder_id, "current_decision": {
        "disposition": row.disposition, "reason": row.reason, "actor": row.actor,
        "at": row.created_at}, "decision_events": len(founder.decisions)}


@app.post("/founders/{founder_id}/stage", tags=["human"])
def post_stage(founder_id: str, body: StageRequest,
               session: Session = Depends(get_db)) -> dict[str, Any]:
    """HUMAN — validated stage transition. Moving to KEEP_WARM requires
    `months` in {3,6,9}; leaving it clears the obsolete schedule. Re-engagement
    is this endpoint being called by a person, never a machine event."""
    founder = _founder(session, founder_id)
    result = change_stage(session, founder, target=body.stage, actor=body.actor,
                          reason=body.reason, keep_warm_months=body.months)
    return {"founder_id": founder_id, **result}


@app.post("/founders/{founder_id}/notes", tags=["human"])
def post_note(founder_id: str, body: NoteRequest,
              session: Session = Depends(get_db)) -> dict[str, Any]:
    """HUMAN — append a note. Append-only."""
    founder = _founder(session, founder_id)
    note = append_note(session, founder, text=body.text, actor=body.actor)
    return {"founder_id": founder_id, "note": note,
            "notes": founder.workflow.notes}


@app.patch("/founders/{founder_id}/workflow", tags=["human"])
def patch_founder_workflow(founder_id: str, body: WorkflowPatchRequest,
                           session: Session = Depends(get_db)) -> dict[str, Any]:
    """owner / next_action only. Cannot reach stage, keep_warm_until, notes or
    decisions."""
    founder = _founder(session, founder_id)
    present = set(body.model_dump(exclude_unset=True)) & {"owner", "next_action"}
    changed = patch_workflow(session, founder, actor=body.actor, reason=body.reason,
                             owner=body.owner, next_action=body.next_action,
                             fields_present=present)
    wf = founder.workflow
    return {"founder_id": founder_id, "changed": changed,
            "workflow": {"stage": wf.stage, "owner": wf.owner,
                         "next_action": wf.next_action,
                         "keep_warm_until": wf.keep_warm_until}}


@app.post("/founders/{founder_id}/ai_check", tags=["machine"])
def ai_check(founder_id: str, session: Session = Depends(get_db)) -> dict[str, Any]:
    """Optional, raise-only AI evidence overlay — run ONLY on explicit request.

    Never called by import, queue, rescore, dashboard or the founder GET: the
    cost, the latency and the human intention behind an AI call all stay
    visible. The deterministic assessment is read and returned unchanged; the
    AI result is a separate section beside it, never merged into it, and never
    persisted over it."""
    founder = _founder(session, founder_id)
    before = json.dumps(founder.assessment_json, sort_keys=True)

    result = run_ai_check(
        founder_id=founder.id, raw=founder.raw_json,
        canonical=CanonicalProfile.model_validate(founder.canonical_json),
        assessment_json=founder.assessment_json,
        adapter=default_adapter(), cfg=effective_config(session))

    # Belt and braces: the overlay must not have touched the stored assessment.
    assert json.dumps(founder.assessment_json, sort_keys=True) == before, (
        "AI check mutated the deterministic assessment")

    return {
        "founder_id": founder_id,
        "deterministic_assessment": founder.assessment_json,
        "assessment_metadata": {
            "assessment_version": founder.assessment_version,
            "assessed_at": founder.assessed_at,
            "rubric_version": founder.rubric_version,
            "engine_version": founder.engine_version,
        },
        "ai_evidence": [c.model_dump(mode="json") for c in result.ai_cues],
        "discarded_evidence": [d.model_dump(mode="json") for d in result.discarded],
        "unsupported_inferences": result.unsupported_inferences,
        "attention_before": result.deterministic_attention,
        "attention_with_ai": result.attention_with_ai,
        "attention_changed": result.attention_changed,
        "attention_change_reason": result.attention_change_reason,
        "aggregate_override": result.aggregate_override,
        "aggregate_rule": result.aggregate_rule,
        "available": result.available,
        "provider": result.provider,
        "status": result.status,
        "detail": result.detail,
        "metadata": result.metadata.model_dump(mode="json") if result.metadata else None,
        "note": ("Supplemental AI-interpreted evidence. It may only RAISE attention, "
                 "never lower it; it does not change the deterministic assessment, "
                 "any human decision, or any workflow state."),
    }


@app.get("/founders", tags=["read"])
def list_founders(session: Session = Depends(get_db),
                  limit: int = Query(default=50, ge=1, le=1000)) -> dict[str, Any]:
    """Founder ids, ordered — a convenience index for scripts and the demo."""
    ids = list(session.execute(select(Founder.id).order_by(Founder.id).limit(limit)).scalars())
    return {"founder_ids": ids}
