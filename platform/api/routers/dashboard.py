"""Dashboard KPI endpoints — real counts from the database."""

from datetime import datetime, time, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.db import get_session
from data.schemas import Consultation, Patient
from intelligence.agents.risk_engine import assess_patient_risk, assess_risk_level
from intelligence.llm import OllamaClient

router = APIRouter()

_client = OllamaClient(host=settings.ollama_host, model=settings.ollama_model)


@router.get("/stats", summary="Dashboard KPIs, agent usage, and system status")
async def dashboard_stats(session: AsyncSession = Depends(get_session)) -> Dict[str, Any]:
    """KPI numbers + agent/system status for the dashboard."""
    patient_count = await session.scalar(select(func.count(Patient.id))) or 0
    consultation_count = await session.scalar(select(func.count(Consultation.id))) or 0

    # Rule-based risk sweep — fine at demo scale; cache if the panel grows.
    patients = (await session.scalars(select(Patient))).all()
    high_risk_count = sum(
        1 for p in patients if assess_risk_level(assess_patient_risk(p.lab_results, p.medications)) == "high"
    )

    today_start = datetime.combine(datetime.now(timezone.utc).date(), time.min)
    consultations_today = (
        await session.scalar(
            select(func.count(Consultation.id)).where(Consultation.created_at >= today_start)
        )
        or 0
    )

    # Per-agent usage from persisted consultations.
    agent_names = ["Evidence", "Radiology", "Laboratory", "Drug Safety", "Coordinator"]
    key_map = {
        "Evidence": "evidence",
        "Radiology": "radiology",
        "Laboratory": "laboratory",
        "Drug Safety": "drug-safety",
        "Coordinator": "coordinator",
    }
    all_agents_used = (await session.scalars(select(Consultation.agents))).all()
    usage = {name: 0 for name in agent_names}
    for agents_list in all_agents_used:
        for name, key in key_map.items():
            if key in (agents_list or []):
                usage[name] += 1
    # Coordinator synthesizes every consultation.
    usage["Coordinator"] = consultation_count

    ollama_ok = await _client.health()
    return {
        "kpis": [
            {"label": "Active Patients", "value": patient_count, "delta": "", "trend": "up"},
            {"label": "Consultations Today", "value": consultations_today, "delta": "", "trend": "up"},
            {"label": "Total Consultations", "value": consultation_count, "delta": "", "trend": "up"},
            {
                "label": "High-Risk Patients",
                "value": high_risk_count,
                "delta": "rule-based",
                "trend": "down" if high_risk_count else "up",
            },
        ],
        "agents": [
            {"name": name, "status": "ready" if ollama_ok else "offline", "consultations": usage[name]}
            for name in agent_names
        ],
        "system": {
            "ollama": "online" if ollama_ok else "offline",
            "model": settings.ollama_model,
            "local_only": True,
        },
    }
