"""Agent consultation endpoints — auth-protected, persisted per user."""

import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.pdf_export import render_consultation_pdf
from auth.deps import get_current_user
from core.config import settings
from core.db import SessionLocal, get_session
from data.schemas import Consultation, User
from intelligence.agents.explainability import build_explanation
from intelligence.agents.workflow import run_consultation, stream_consultation
from intelligence.llm import OllamaClient

router = APIRouter()

logger = logging.getLogger("api.consultations")

_client = OllamaClient(host=settings.ollama_host, model=settings.ollama_model)

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
    disclaimer: str = DISCLAIMER


async def _ensure_ollama() -> None:
    if not await _client.health():
        raise HTTPException(
            status_code=503,
            detail=(
                f"Ollama is not reachable at {settings.ollama_host} or model "
                f"'{settings.ollama_model}' is missing. Run: ollama pull {settings.ollama_model}"
            ),
        )


async def _persist(
    session: AsyncSession,
    user: User,
    request: ConsultRequest,
    state: Dict[str, Any],
) -> Consultation:
    consultation = Consultation(
        id=str(uuid4()),
        user_id=user.id,
        patient_id=request.patient_id or None,
        query=request.query,
        answer=state.get("final_answer", ""),
        agents=sorted(state.get("agent_outputs", {}).keys()),
        tool_calls=state.get("tool_calls", []),
        citation_report=state.get("citation_report", {}),
    )
    session.add(consultation)
    await session.commit()
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
    await _ensure_ollama()

    state = await run_consultation(
        _client,
        query=request.query,
        patient_id=request.patient_id,
        context=request.context,
    )
    consultation = await _persist(session, user, request, dict(state))
    return ConsultResponse(
        id=consultation.id,
        answer=consultation.answer,
        agents_involved=consultation.agents,
        tool_calls=consultation.tool_calls,
        citation_report=consultation.citation_report,
        explanation=dict(state).get("explanation", {}),
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
    await _ensure_ollama()

    async def event_stream():
        final_state: Dict[str, Any] = {}
        try:
            async for event in stream_consultation(
                _client,
                query=request.query,
                patient_id=request.patient_id,
                context=request.context,
            ):
                if event["event"] == "final":
                    final_state = {
                        "final_answer": event["answer"],
                        "agent_outputs": {a: "" for a in event["agents_involved"]},
                        "tool_calls": event["tool_calls"],
                        "citation_report": event["citation_report"],
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
            # Derived on read — improving the templates needs no backfill.
            "explanation": build_explanation(c.agents, c.tool_calls, c.citation_report),
            "patient_id": c.patient_id,
            "created_at": c.created_at.isoformat(),
        }
        for c in rows
    ]


@router.get("/history/{consultation_id}/export", summary="Export a consultation as PDF")
async def export_consultation(
    consultation_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Download one of the current user's consultations as a PDF report."""
    consultation = await session.scalar(
        select(Consultation).where(
            Consultation.id == consultation_id, Consultation.user_id == user.id
        )
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
        headers={
            "Content-Disposition": f'attachment; filename="consultation-{consultation.id[:8]}.pdf"'
        },
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
    await _ensure_ollama()

    result = await agent_cls(_client).run(request.query, request.context)
    return {"agent": request.agent, "answer": result.content, "tool_calls": result.tool_calls}
