"""Dashboard endpoints — priorización clínica, evolución, alertas,
medicación, laboratorios, imaging, IA, evidencia, pendientes y rendimiento.

`/stats` is the original "critical patients" scan-in-five-seconds list
(kept, extended with `priority_score`); every other section is its own
endpoint so the frontend can refetch each independently, same reasoning
`agendaToday` (60s) already gets a separate cadence from `dashboardStats`
(30s). Each endpoint follows dashboard.py's original pattern: a rule-based
or straight-aggregation sweep over rows, returned as a hand-built dict —
no `response_model=`, no background jobs, nothing persisted here that
wasn't already persisted by another route."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session
from data.schemas import AIEvaluation, Alert, Consultation, ImagingStudy, LabResult, MedicationOrder, Patient
from intelligence.mcp.drug_safety_server import find_interactions
from sephiroth.safety.priority import compute_priority_score
from sephiroth.safety.risk import RISK_ORDER, assess_patient_risk, assess_risk_level

router = APIRouter()


@router.get("/stats", summary="Critical patients for the dashboard")
async def dashboard_stats(session: AsyncSession = Depends(get_session)) -> Dict[str, Any]:
    """Every patient scored by the same rule-based risk engine `/api/patients`
    uses, filtered to high/medium, sorted riskiest-first, capped to the top
    10 — a scan-in-five-seconds list, not another count. Rule-based sweep
    over every patient; fine at demo scale, cache if the panel grows."""
    patients = (await session.scalars(select(Patient).order_by(Patient.name))).all()

    scored: List[Dict[str, Any]] = []
    for p in patients:
        flags = assess_patient_risk(p.lab_results, p.medications)
        level = assess_risk_level(flags)
        scored.append(
            {
                "id": p.id,
                "name": p.name,
                "risk_level": level,
                "priority_score": compute_priority_score(level),
                "top_flag": max(flags, key=lambda f: 0 if f["severity"] == "high" else 1)["label"]
                if flags
                else None,
                "flag_count": len(flags),
            }
        )

    at_risk = [s for s in scored if s["risk_level"] != "low"]
    at_risk.sort(key=lambda s: RISK_ORDER.get(s["risk_level"], len(RISK_ORDER)))

    return {
        "critical_patients": at_risk[:10],
        "critical_count": sum(1 for s in scored if s["risk_level"] == "high"),
        "moderate_count": sum(1 for s in scored if s["risk_level"] == "medium"),
        "stable_count": sum(1 for s in scored if s["risk_level"] == "low"),
        "at_risk_count": len(at_risk),
        "max_priority_score": max((s["priority_score"] for s in scored), default=0),
        "avg_priority_score": round(sum(s["priority_score"] for s in scored) / len(scored), 2) if scored else 0.0,
    }


@router.get("/evolution", summary="Clinical evolution — deterioration/improvement signals")
async def dashboard_evolution(session: AsyncSession = Depends(get_session)) -> Dict[str, Any]:
    """Compares each patient's two most recent readings per lab test
    (`LabResult`, real time series) to flag deterioration/improvement.
    Patients with fewer than 2 readings for any test are counted as
    "no_change" — there's nothing to compare yet, not a claim of stability."""
    patients = (await session.scalars(select(Patient))).all()
    results = (await session.scalars(select(LabResult).order_by(LabResult.taken_at))).all()

    by_patient: Dict[str, Dict[str, List[LabResult]]] = {}
    for r in results:
        by_patient.setdefault(r.patient_id, {}).setdefault(r.test_name, []).append(r)

    deteriorating, improving, no_change, new_flags_total = [], [], [], 0
    for p in patients:
        tests = by_patient.get(p.id, {})
        worsened = improved = 0
        for readings in tests.values():
            if len(readings) < 2:
                continue
            prev, latest = readings[-2], readings[-1]
            if latest.is_critical and not prev.is_critical:
                new_flags_total += 1
                worsened += 1
            elif prev.is_critical and not latest.is_critical:
                improved += 1
            elif latest.is_abnormal and not prev.is_abnormal:
                worsened += 1
            elif prev.is_abnormal and not latest.is_abnormal:
                improved += 1
        entry = {"id": p.id, "name": p.name}
        if worsened > improved:
            deteriorating.append(entry)
        elif improved > worsened:
            improving.append(entry)
        else:
            no_change.append(entry)

    return {
        "deteriorating": deteriorating,
        "improving": improving,
        "no_change": no_change,
        "deteriorating_count": len(deteriorating),
        "improving_count": len(improving),
        "no_change_count": len(no_change),
        "new_risk_factors_count": new_flags_total,
    }


@router.get("/alerts", summary="Clinical alerts")
async def dashboard_alerts(session: AsyncSession = Depends(get_session)) -> Dict[str, Any]:
    alerts = (await session.scalars(select(Alert).order_by(Alert.created_at.desc()))).all()

    now = datetime.now(timezone.utc)
    recent_cutoff = now - timedelta(hours=24)
    review_durations = [
        (a.reviewed_at - a.created_at).total_seconds()
        for a in alerts
        if a.reviewed_at is not None
    ]

    def _naive_utc(dt: datetime) -> datetime:
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    return {
        "active_count": sum(1 for a in alerts if a.status == "active"),
        "new_count": sum(1 for a in alerts if _naive_utc(a.created_at) >= recent_cutoff),
        "critical_count": sum(1 for a in alerts if a.severity == "critical" and a.status != "resolved"),
        "pending_review_count": sum(1 for a in alerts if a.status == "active" and a.reviewed_at is None),
        "resolved_count": sum(1 for a in alerts if a.status == "resolved"),
        "avg_review_seconds": round(sum(review_durations) / len(review_durations), 1)
        if review_durations
        else None,
        "recent": [
            {
                "id": a.id,
                "patient_id": a.patient_id,
                "category": a.category,
                "severity": a.severity,
                "status": a.status,
                "title": a.title,
            }
            for a in alerts[:20]
        ],
    }


@router.get("/medications", summary="Medication safety metrics")
async def dashboard_medications(session: AsyncSession = Depends(get_session)) -> Dict[str, Any]:
    """Interactions reuse the same curated table `sephiroth.safety.risk`
    checks; structured counts (high-risk, polypharmacy) come from
    `MedicationOrder` when a patient has orders, falling back to the flat
    `Patient.medications` list otherwise (same fallback `risk.py` uses)."""
    patients = (await session.scalars(select(Patient))).all()
    orders = (await session.scalars(select(MedicationOrder).where(MedicationOrder.status == "active"))).all()

    orders_by_patient: Dict[str, List[MedicationOrder]] = {}
    for o in orders:
        orders_by_patient.setdefault(o.patient_id, []).append(o)

    interactions = contraindications = high_risk = polypharmacy = 0
    severity_map = {"major": "high", "moderate": "medium"}
    for p in patients:
        meds = [o.name for o in orders_by_patient.get(p.id, [])] or p.medications or []
        found = find_interactions(meds)
        interactions += len(found)
        contraindications += sum(1 for f in found if severity_map.get(f["severity"]) == "high")
        high_risk += sum(1 for o in orders_by_patient.get(p.id, []) if o.is_high_risk)
        if len(meds) >= 5:
            polypharmacy += 1

    return {
        "interaction_count": interactions,
        "contraindication_count": contraindications,
        "high_risk_medication_count": high_risk,
        "dose_anomaly_count": 0,  # requires a dosing-range reference table; not implemented yet
        "polypharmacy_patient_count": polypharmacy,
    }


@router.get("/labs", summary="Laboratory metrics")
async def dashboard_labs(session: AsyncSession = Depends(get_session)) -> Dict[str, Any]:
    results = (await session.scalars(select(LabResult).order_by(LabResult.taken_at))).all()

    by_patient_test: Dict[tuple, List[LabResult]] = {}
    for r in results:
        by_patient_test.setdefault((r.patient_id, r.test_name), []).append(r)

    significant_changes = 0
    for readings in by_patient_test.values():
        if len(readings) < 2:
            continue
        prev, latest = readings[-2], readings[-1]
        if prev.value and abs(latest.value - prev.value) / abs(prev.value) >= 0.2:
            significant_changes += 1

    deteriorating_trends = sum(
        1
        for readings in by_patient_test.values()
        if len(readings) >= 3 and all(r.is_abnormal for r in readings[-3:])
    )

    return {
        "abnormal_count": sum(1 for r in results if r.is_abnormal),
        "critical_count": sum(1 for r in results if r.is_critical),
        "deteriorating_trend_count": deteriorating_trends,
        "significant_change_count": significant_changes,
        "pending_count": 0,  # no "ordered but not resulted" state exists yet
    }


@router.get("/imaging", summary="Imaging analysis metrics")
async def dashboard_imaging(session: AsyncSession = Depends(get_session)) -> Dict[str, Any]:
    studies = (await session.scalars(select(ImagingStudy).order_by(ImagingStudy.study_date))).all()

    by_patient_part: Dict[tuple, List[ImagingStudy]] = {}
    for s in studies:
        by_patient_part.setdefault((s.patient_id, s.body_part), []).append(s)

    new_vs_prior = sum(
        1
        for group in by_patient_part.values()
        if len(group) >= 2 and group[-1].is_new_finding
    )

    analyzed = [s for s in studies if s.status == "analyzed"]
    return {
        "analyzed_count": len(analyzed),
        "critical_finding_count": sum(1 for s in analyzed if s.severity == "critical"),
        "requires_review_count": sum(1 for s in analyzed if s.severity == "review"),
        "no_relevant_finding_count": sum(1 for s in analyzed if s.severity == "none"),
        "new_finding_vs_prior_count": new_vs_prior,
        "pending_count": sum(1 for s in studies if s.status == "pending"),
    }


@router.get("/ai", summary="AI evaluation metrics")
async def dashboard_ai(session: AsyncSession = Depends(get_session)) -> Dict[str, Any]:
    evaluations = (await session.scalars(select(AIEvaluation))).all()
    consultations = (await session.scalars(select(Consultation))).all()

    confidences = [e.confidence for e in evaluations if e.confidence is not None]
    return {
        "evaluations_count": len(evaluations),
        "consultations_count": len(consultations),
        "high_risk_prediction_count": sum(1 for c in consultations if c.risk_level == "high"),
        "avg_confidence": round(sum(confidences) / len(confidences), 3) if confidences else None,
        "requires_human_review_count": sum(1 for e in evaluations if e.requires_human_review),
        "clinician_modified_count": sum(1 for e in evaluations if e.clinician_modified),
        "clinician_rejected_count": sum(1 for e in evaluations if e.clinician_rejected),
    }


@router.get("/evidence", summary="Evidence and explainability metrics")
async def dashboard_evidence(session: AsyncSession = Depends(get_session)) -> Dict[str, Any]:
    """Derived entirely from `Consultation.verification_report` /
    `citation_report`, already persisted per consultation — no new table."""
    consultations = (await session.scalars(select(Consultation))).all()

    with_evidence = without_evidence = 0
    sources: set = set()
    ratios = []
    for c in consultations:
        report = c.verification_report or {}
        claims = report.get("claims", [])
        if not claims:
            continue
        supported = sum(1 for claim in claims if claim.get("status") == "supported")
        if supported == 0:
            without_evidence += 1
        else:
            with_evidence += 1
        for claim in claims:
            for evidence_id in claim.get("evidence_ids", []) or []:
                sources.add(evidence_id)
        if c.supported_claim_ratio is not None:
            ratios.append(c.supported_claim_ratio)

    return {
        "recommendations_with_evidence_count": with_evidence,
        "recommendations_without_evidence_count": without_evidence,
        "distinct_sources_used": len(sources),
        "avg_supported_claim_ratio": round(sum(ratios) / len(ratios), 3) if ratios else None,
    }


@router.get("/pending", summary="Pending clinical items")
async def dashboard_pending(session: AsyncSession = Depends(get_session)) -> Dict[str, Any]:
    alerts = (await session.scalars(select(Alert).where(Alert.status == "active"))).all()
    consultations = (await session.scalars(select(Consultation))).all()

    pending_follow_up = {a.patient_id for a in alerts}
    return {
        "unresolved_clinical_issues_count": len(alerts),
        "patients_pending_follow_up_count": len(pending_follow_up),
        "pending_recommendations_count": sum(1 for c in consultations if c.acted_on is None),
        "cases_requiring_decision_count": sum(
            1 for c in consultations if c.acted_on is None and c.risk_level == "high"
        ),
    }


@router.get("/performance", summary="Clinical/AI performance metrics")
async def dashboard_performance(session: AsyncSession = Depends(get_session)) -> Dict[str, Any]:
    """AUC/sensitivity/specificity here are a **best-effort proxy**, not a
    validated model metric: there is no labeled ground-truth dataset in
    this system. They're derived from `Consultation.outcome` (clinician-
    recorded, optional) versus `risk_level` (the model's own high/medium/
    low call) — treat as directional, never as clinical validation."""
    alerts = (await session.scalars(select(Alert).where(Alert.reviewed_at.is_not(None)))).all()
    consultations = (await session.scalars(select(Consultation).where(Consultation.outcome.is_not(None)))).all()

    def _naive_utc(dt: datetime) -> datetime:
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    review_durations = [(_naive_utc(a.reviewed_at) - _naive_utc(a.created_at)).total_seconds() for a in alerts]
    resolved = sum(1 for a in alerts if a.status == "resolved")

    true_positive = sum(1 for c in consultations if c.risk_level == "high" and c.outcome == "not_improved")
    false_positive = sum(1 for c in consultations if c.risk_level == "high" and c.outcome == "improved")
    true_negative = sum(1 for c in consultations if c.risk_level != "high" and c.outcome == "improved")
    false_negative = sum(1 for c in consultations if c.risk_level != "high" and c.outcome == "not_improved")

    sensitivity = true_positive / (true_positive + false_negative) if (true_positive + false_negative) else None
    specificity = true_negative / (true_negative + false_positive) if (true_negative + false_positive) else None

    return {
        "avg_alert_response_seconds": round(sum(review_durations) / len(review_durations), 1)
        if review_durations
        else None,
        "alerts_resolved_count": resolved,
        "false_positive_count": false_positive,
        "false_negative_count": false_negative,
        "sensitivity": round(sensitivity, 3) if sensitivity is not None else None,
        "specificity": round(specificity, 3) if specificity is not None else None,
        "auc": None,  # needs a probability score per prediction, not just a 3-level label — not computable today
        "methodology": "proxy estimate from Consultation.outcome vs risk_level — no labeled ground-truth dataset",
    }
