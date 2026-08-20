"""Agent consultation endpoints — auth-protected, persisted per user."""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.pdf_export import render_consultation_pdf
from auth.deps import get_current_user
from core.config import settings
from core.db import SessionLocal, get_session
from data.schemas import AIEvaluation, Consultation, User
from sephiroth.context import recent_consultation_summaries
from sephiroth.models import get_llm_client
from sephiroth.runtime import run_consultation, stream_consultation
from sephiroth.telemetry.explain import build_explanation

router = APIRouter()

logger = logging.getLogger("api.consultations")

DISCLAIMER = "Decision support only — not a diagnosis. Professional review required."


class ConsultRequest(BaseModel):
    query: str = Field(..., min_length=3, description="Clinical question")
    patient_id: str = ""
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional patient context: medications, lab_results, image_path, history",
    )


class ConsultResponse(BaseModel):
    id: str
    answer: str
    agents_involved: List[str]
    tool_calls: List[Dict[str, Any]]
    citation_report: Dict[str, Any] = {}
    explanation: Dict[str, Any] = {}
    verification_report: Dict[str, Any] = {}
    abstention: Optional[Dict[str, Any]] = None
    trace: Optional[Dict[str, Any]] = None
    disclaimer: str = DISCLAIMER


async def _ensure_llm() -> None:
    if not await get_llm_client().health():
        raise HTTPException(
            status_code=503,
            detail=(
                f"Gemini is not reachable or model '{settings.gemini_model}' is unavailable. "
                "Check GEMINI_API_KEY and quota."
            ),
        )


async def _persist(
    session: AsyncSession,
    user: User,
    request: ConsultRequest,
    state: Dict[str, Any],
) -> Consultation:
    trace = state.get("trace") or {}
    # VerificationReport.supported_claim_ratio is a derived @property, not a
    # serialized field — recompute it from the claims list already in the
    # (frozen-shape) verification_report dict rather than from the trace dump.
    verification_claims = state.get("verification_report", {}).get("claims", [])
    supported_ratio = (
        sum(1 for c in verification_claims if c.get("status") == "supported") / len(verification_claims)
        if verification_claims
        else 1.0
    )
    consultation = Consultation(
        id=str(uuid4()),
        user_id=user.id,
        patient_id=request.patient_id or None,
        query=request.query,
        answer=state.get("final_answer", ""),
        agents=sorted(state.get("agent_outputs", {}).keys()),
        tool_calls=state.get("tool_calls", []),
        citation_report=state.get("citation_report", {}),
        verification_report=state.get("verification_report", {}),
        abstention=state.get("abstention") or {},
        trace=trace or None,
        trace_id=trace.get("trace_id"),
        risk_level=trace.get("risk_level"),
        abstained=(state.get("abstention") or {}).get("status") == "abstain",
        supported_claim_ratio=supported_ratio,
    )
    session.add(consultation)
    await session.commit()
    logger.info("consultation_persisted consultation_id=%s", consultation.id[:8])
    # Separate commit: AIEvaluation.consultation_id is a plain FK column, not
    # an ORM relationship() SQLAlchemy's unit-of-work can use to order the
    # two inserts — flushing both in one transaction risked (and once hit,
    # against Supabase) inserting AIEvaluation before Consultation existed.
    abstention_status = (state.get("abstention") or {}).get("status", "answer")
    ai_eval = AIEvaluation(
        id=str(uuid4()),
        patient_id=consultation.patient_id,
        consultation_id=consultation.id,
        eval_type="consultation",
        # Same derived-not-self-reported confidence signal Consultation
        # itself stores (decision #15) — never a value the model reports.
        confidence=supported_ratio,
        requires_human_review=abstention_status != "answer" or consultation.risk_level == "high",
    )
    logger.info("adding_ai_eval ai_eval_id=%s consultation_id=%s", ai_eval.id[:8], ai_eval.consultation_id[:8])
    session.add(ai_eval)
    await session.commit()
    logger.info("ai_eval_persisted ai_eval_id=%s", ai_eval.id[:8])
    # Audit trail: one line per persisted consultation.
    logger.info(
        "consultation_id=%s user=%s patient=%s agents=%s tool_calls=%s fabricated_citations=%s",
        consultation.id[:8],
        user.email,
        consultation.patient_id or "-",
        len(consultation.agents),
        len(consultation.tool_calls),
        len((consultation.citation_report or {}).get("fabricated", [])),
    )
    return consultation


@router.post("/consult", response_model=ConsultResponse)
async def consult(
    request: ConsultRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ConsultResponse:
    """Run the multi-agent clinical workflow and persist it to the user's history."""
    if not settings.enable_agents:
        raise HTTPException(status_code=503, detail="Agent workflow is disabled")
    await _ensure_llm()

    context = dict(request.context)
    if request.patient_id:
        context["recent_consultations"] = await recent_consultation_summaries(request.patient_id, session)

    state = await run_consultation(
        get_llm_client(),
        query=request.query,
        patient_id=request.patient_id,
        context=context,
    )
    consultation = await _persist(session, user, request, dict(state))
    return ConsultResponse(
        id=consultation.id,
        answer=consultation.answer,
        agents_involved=consultation.agents,
        tool_calls=consultation.tool_calls,
        citation_report=consultation.citation_report,
        explanation=dict(state).get("explanation", {}),
        verification_report=consultation.verification_report,
        abstention=consultation.abstention or None,
        trace=consultation.trace,
    )


@router.post("/consult/stream")
async def consult_stream(
    request: ConsultRequest,
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Stream the multi-agent workflow as Server-Sent Events.

    Emits `routing`, one `agent_completed` per specialist, then `final`.
    The consultation is persisted once the final event is produced.
    """
    if not settings.enable_agents:
        raise HTTPException(status_code=503, detail="Agent workflow is disabled")
    await _ensure_llm()

    context = dict(request.context)
    if request.patient_id:
        async with SessionLocal() as lookup_session:
            context["recent_consultations"] = await recent_consultation_summaries(
                request.patient_id, lookup_session
            )

    async def event_stream():
        final_state: Dict[str, Any] = {}
        try:
            async for event in stream_consultation(
                get_llm_client(),
                query=request.query,
                patient_id=request.patient_id,
                context=context,
            ):
                if event["event"] == "final":
                    final_state = {
                        "final_answer": event["answer"],
                        "agent_outputs": {a: "" for a in event["agents_involved"]},
                        "tool_calls": event["tool_calls"],
                        "citation_report": event["citation_report"],
                        "verification_report": event.get("verification_report", {}),
                        "abstention": event.get("abstention"),
                        "trace": event.get("trace"),
                    }
                yield f"data: {json.dumps(event, default=str)}\n\n"
        except Exception as exc:  # surface errors as an SSE event, not a dropped socket
            yield f"data: {json.dumps({'event': 'error', 'detail': str(exc)})}\n\n"
            return

        # Persist outside the request-scoped session (the response is streaming),
        # then tell the client its id so Export PDF works without a reload.
        if final_state:
            async with SessionLocal() as session:
                consultation = await _persist(session, user, request, final_state)
            yield f"data: {json.dumps({'event': 'persisted', 'id': consultation.id})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


_AGENT_KEYS = {
    "Evidence": "evidence",
    "Radiology": "radiology",
    "Laboratory": "laboratory",
    "Drug Safety": "drug-safety",
    "Coordinator": "coordinator",
}


@router.get("/status", summary="Per-agent usage + LLM health, for the Agents Activity page")
async def agents_status(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Moved here (was previously folded into `/api/dashboard/stats`) when
    the dashboard was redesigned around a critical-patients list — this data
    is about agents, not "what needs my attention today," and belongs in
    this router. Behavior unchanged from the old dashboard endpoint."""
    consultation_count = await session.scalar(select(func.count(Consultation.id))) or 0
    all_agents_used = (await session.scalars(select(Consultation.agents))).all()
    usage = {name: 0 for name in _AGENT_KEYS}
    for agents_list in all_agents_used:
        for name, key in _AGENT_KEYS.items():
            if key in (agents_list or []):
                usage[name] += 1
    # Coordinator synthesizes every consultation.
    usage["Coordinator"] = consultation_count

    llm_ok = await get_llm_client().health()
    return {
        "agents": [
            {"name": name, "status": "ready" if llm_ok else "offline", "consultations": usage[name]}
            for name in _AGENT_KEYS
        ],
        "system": {
            "llm": "online" if llm_ok else "offline",
            "model": settings.gemini_model,
            "provider": "gemini",
            "local_only": False,
        },
    }


@router.get("/history")
async def history(
    limit: int = 20,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> List[Dict[str, Any]]:
    """The current user's past consultations, newest first."""
    rows = (
        await session.scalars(
            select(Consultation)
            .where(Consultation.user_id == user.id)
            .order_by(Consultation.created_at.desc())
            .limit(min(limit, 100))
        )
    ).all()
    return [
        {
            "id": c.id,
            "query": c.query,
            "answer": c.answer,
            "agents_involved": c.agents,
            "tool_calls": c.tool_calls,
            "citation_report": c.citation_report,
            "verification_report": c.verification_report,
            "abstention": c.abstention or None,
            "trace": c.trace,
            # Derived on read — improving the templates needs no backfill.
            "explanation": build_explanation(c.agents, c.tool_calls, c.citation_report),
            "patient_id": c.patient_id,
            "created_at": c.created_at.isoformat(),
            "acted_on": c.acted_on,
            "acted_at": c.acted_at.isoformat() if c.acted_at else None,
            "outcome": c.outcome,
            "outcome_at": c.outcome_at.isoformat() if c.outcome_at else None,
        }
        for c in rows
    ]


_OUTCOMES = ("improved", "not_improved", "unclear")


class ConsultationUpdate(BaseModel):
    """Partial update for the "My Recommendations" workflow — a clinician
    marking whether they acted on a past consultation's answer, and later,
    separately, whether the patient improved. Either field alone is a valid
    request; both get their own timestamp since they're recorded at
    different times, not atomically."""

    acted_on: Optional[bool] = None
    outcome: Optional[str] = Field(None, pattern="^(" + "|".join(_OUTCOMES) + ")$")


@router.patch("/history/{consultation_id}", summary="Mark a consultation acted-on and/or its outcome")
async def update_consultation_outcome(
    consultation_id: str,
    body: ConsultationUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    consultation = await session.scalar(
        select(Consultation).where(Consultation.id == consultation_id, Consultation.user_id == user.id)
    )
    if consultation is None:
        raise HTTPException(status_code=404, detail="Consultation not found")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if body.acted_on is not None:
        consultation.acted_on = body.acted_on
        consultation.acted_at = now
    if body.outcome is not None:
        consultation.outcome = body.outcome
        consultation.outcome_at = now
    await session.commit()

    return {
        "id": consultation.id,
        "acted_on": consultation.acted_on,
        "acted_at": consultation.acted_at.isoformat() if consultation.acted_at else None,
        "outcome": consultation.outcome,
        "outcome_at": consultation.outcome_at.isoformat() if consultation.outcome_at else None,
    }


@router.get("/recommendations/stats", summary="Effectiveness ratio across the current user's own history")
async def recommendation_stats(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, int]:
    """Raw counts, not a pre-formatted string — computed over the user's
    FULL history (never truncated the way `/history`'s `limit` is), so the
    ratio stays accurate regardless of how much of the list the UI renders."""
    total = (
        await session.scalar(select(func.count(Consultation.id)).where(Consultation.user_id == user.id)) or 0
    )
    acted_on = (
        await session.scalar(
            select(func.count(Consultation.id)).where(
                Consultation.user_id == user.id, Consultation.acted_on.is_(True)
            )
        )
        or 0
    )
    improved = (
        await session.scalar(
            select(func.count(Consultation.id)).where(
                Consultation.user_id == user.id, Consultation.outcome == "improved"
            )
        )
        or 0
    )
    return {"total": total, "acted_on": acted_on, "improved": improved}


@router.get("/history/{consultation_id}/export", summary="Export a consultation as PDF")
async def export_consultation(
    consultation_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Download one of the current user's consultations as a PDF report."""
    consultation = await session.scalar(
        select(Consultation).where(Consultation.id == consultation_id, Consultation.user_id == user.id)
    )
    if consultation is None:
        raise HTTPException(status_code=404, detail="Consultation not found")

    explanation = build_explanation(
        consultation.agents, consultation.tool_calls, consultation.citation_report
    )
    pdf_bytes = render_consultation_pdf(consultation, explanation)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="consultation-{consultation.id[:8]}.pdf"'},
    )


class AskAgentRequest(BaseModel):
    agent: str = Field(..., description="radiology|laboratory|drug-safety|evidence|coordinator")
    query: str
    context: Optional[Dict[str, Any]] = None


@router.post("/ask")
async def ask_single_agent(
    request: AskAgentRequest,
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Query one specialist agent directly (not persisted)."""
    from intelligence.agents import (
        ClinicalCoordinator,
        DrugSafetyAgent,
        EvidenceAgent,
        LabAgent,
        RadiologyAgent,
    )

    agents = {
        "radiology": RadiologyAgent,
        "laboratory": LabAgent,
        "drug-safety": DrugSafetyAgent,
        "evidence": EvidenceAgent,
        "coordinator": ClinicalCoordinator,
    }
    agent_cls = agents.get(request.agent)
    if agent_cls is None:
        raise HTTPException(status_code=404, detail=f"Unknown agent '{request.agent}'")
    await _ensure_llm()

    result = await agent_cls(get_llm_client()).run(request.query, request.context)
    return {"agent": request.agent, "answer": result.content, "tool_calls": result.tool_calls}
