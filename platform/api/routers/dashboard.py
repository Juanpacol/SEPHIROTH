"""Dashboard endpoint — critical patients, the one thing a clinician
opening the app needs to see first. Replaced the old generic KPI-card /
agent-usage-chart payload (patient/consultation counts, per-agent call
counts, LLM health) — none of that told a clinician *who* needed attention,
only aggregate numbers. Today's agenda still comes from a separate call to
`GET /api/scheduling/agenda/today`, unchanged."""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session
from data.schemas import Patient
from sephiroth.safety.risk import RISK_ORDER, assess_patient_risk, assess_risk_level

router = APIRouter()


@router.get("/stats", summary="Critical patients for the dashboard")
async def dashboard_stats(session: AsyncSession = Depends(get_session)) -> Dict[str, Any]:
    """Every patient scored by the same rule-based risk engine `/api/patients`
    uses, filtered to high/medium, sorted riskiest-first, capped to the top
    10 — a scan-in-five-seconds list, not another count. Rule-based sweep
    over every patient; fine at demo scale, cache if the panel grows."""
    patients = (await session.scalars(select(Patient).order_by(Patient.name))).all()

    at_risk: List[Dict[str, Any]] = []
    for p in patients:
        flags = assess_patient_risk(p.lab_results, p.medications)
        level = assess_risk_level(flags)
        if level == "low":
            continue
        top_flag = max(flags, key=lambda f: 0 if f["severity"] == "high" else 1)
        at_risk.append(
            {
                "id": p.id,
                "name": p.name,
                "risk_level": level,
                "top_flag": top_flag["label"],
                "flag_count": len(flags),
            }
        )

    at_risk.sort(key=lambda s: RISK_ORDER.get(s["risk_level"], len(RISK_ORDER)))

    return {
        "critical_patients": at_risk[:10],
        "critical_count": sum(1 for s in at_risk if s["risk_level"] == "high"),
        "at_risk_count": len(at_risk),
    }
