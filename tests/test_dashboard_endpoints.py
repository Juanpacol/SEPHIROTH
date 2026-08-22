"""Coverage for the dashboard endpoints beyond /stats and /automation
(each already tested in test_api_agenda_today.py and
test_dashboard_automation.py): /evolution, /alerts, /medications, /labs,
/imaging, /ai, /evidence, /pending, /performance, /bootstrap."""

from datetime import date, datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from core.db import get_session
from data.schemas import (
    AIEvaluation,
    Alert,
    Consultation,
    ImagingStudy,
    LabResult,
    MedicationOrder,
    Patient,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client(db_session):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    yield AsyncClient(transport=transport, base_url="http://test")
    app.dependency_overrides.clear()


async def _clinician(client, email="dash-endpoints-clin@example.org") -> dict:
    res = await client.post(
        "/api/auth/register", json={"email": email, "name": "Dr. Dash", "password": "password123"}
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


async def test_dashboard_evolution_flags_deterioration_and_improvement(client, db_session):
    p1 = Patient(id="PEV1", name="Deteriorating", age=50, sex="M", medical_record_number="PT-PEV1")
    p2 = Patient(id="PEV2", name="Improving", age=51, sex="F", medical_record_number="PT-PEV2")
    p3 = Patient(id="PEV3", name="No history", age=52, sex="F", medical_record_number="PT-PEV3")
    db_session.add_all([p1, p2, p3])
    db_session.add_all(
        [
            LabResult(
                patient_id="PEV1",
                test_name="glucose",
                value=90,
                is_critical=False,
                is_abnormal=False,
                taken_at=datetime(2026, 1, 1),
            ),
            LabResult(
                patient_id="PEV1",
                test_name="glucose",
                value=300,
                is_critical=True,
                is_abnormal=True,
                taken_at=datetime(2026, 1, 2),
            ),
            LabResult(
                patient_id="PEV2",
                test_name="glucose",
                value=300,
                is_critical=True,
                is_abnormal=True,
                taken_at=datetime(2026, 1, 1),
            ),
            LabResult(
                patient_id="PEV2",
                test_name="glucose",
                value=90,
                is_critical=False,
                is_abnormal=False,
                taken_at=datetime(2026, 1, 2),
            ),
        ]
    )
    await db_session.commit()

    headers = await _clinician(client)
    res = await client.get("/api/dashboard/evolution", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert {p["id"] for p in body["deteriorating"]} == {"PEV1"}
    assert {p["id"] for p in body["improving"]} == {"PEV2"}
    assert "PEV3" in {p["id"] for p in body["no_change"]}
    assert body["new_risk_factors_count"] == 1


async def test_dashboard_alerts_counts_and_recent(client, db_session):
    p = Patient(id="PAL1", name="Alert Patient", age=40, sex="M", medical_record_number="PT-PAL1")
    db_session.add(p)
    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            Alert(
                id="AL1",
                patient_id="PAL1",
                category="lab",
                severity="critical",
                status="active",
                title="Critical lab",
                source="rule",
                created_at=now,
            ),
            Alert(
                id="AL2",
                patient_id="PAL1",
                category="lab",
                severity="medium",
                status="resolved",
                title="Resolved alert",
                source="rule",
                created_at=now - timedelta(days=5),
                reviewed_at=now - timedelta(days=4),
            ),
        ]
    )
    await db_session.commit()

    headers = await _clinician(client)
    res = await client.get("/api/dashboard/alerts", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["active_count"] == 1
    assert body["critical_count"] == 1
    assert body["resolved_count"] == 1
    assert body["avg_review_seconds"] is not None
    assert len(body["recent"]) == 2


async def test_dashboard_medications_polypharmacy_and_high_risk(client, db_session):
    p = Patient(
        id="PMED1",
        name="Med Patient",
        age=60,
        sex="F",
        medical_record_number="PT-PMED1",
        medications=[],
    )
    db_session.add(p)
    db_session.add_all(
        [
            MedicationOrder(
                id="MO1", patient_id="PMED1", name="warfarin", status="active", is_high_risk=True
            ),
            MedicationOrder(id="MO2", patient_id="PMED1", name="med2", status="active"),
            MedicationOrder(id="MO3", patient_id="PMED1", name="med3", status="active"),
            MedicationOrder(id="MO4", patient_id="PMED1", name="med4", status="active"),
            MedicationOrder(id="MO5", patient_id="PMED1", name="med5", status="active"),
        ]
    )
    await db_session.commit()

    headers = await _clinician(client)
    res = await client.get("/api/dashboard/medications", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["high_risk_medication_count"] == 1
    assert body["polypharmacy_patient_count"] == 1


async def test_dashboard_labs_significant_change_and_trend(client, db_session):
    p = Patient(id="PLAB1", name="Lab Patient", age=45, sex="M", medical_record_number="PT-PLAB1")
    db_session.add(p)
    db_session.add_all(
        [
            LabResult(
                patient_id="PLAB1",
                test_name="creatinine",
                value=1.0,
                is_abnormal=True,
                taken_at=datetime(2026, 1, 1),
            ),
            LabResult(
                patient_id="PLAB1",
                test_name="creatinine",
                value=1.0,
                is_abnormal=True,
                taken_at=datetime(2026, 1, 2),
            ),
            LabResult(
                patient_id="PLAB1",
                test_name="creatinine",
                value=2.0,
                is_abnormal=True,
                is_critical=True,
                taken_at=datetime(2026, 1, 3),
            ),
        ]
    )
    await db_session.commit()

    headers = await _clinician(client)
    res = await client.get("/api/dashboard/labs", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["significant_change_count"] == 1
    assert body["deteriorating_trend_count"] == 1
    assert body["critical_count"] == 1
    assert body["abnormal_count"] == 3


async def test_dashboard_imaging_new_finding_vs_prior(client, db_session):
    p = Patient(id="PIMG1", name="Imaging Patient", age=45, sex="F", medical_record_number="PT-PIMG1")
    db_session.add(p)
    db_session.add_all(
        [
            ImagingStudy(
                id="IMG1",
                patient_id="PIMG1",
                modality="CT",
                body_part="chest",
                study_date=date(2026, 1, 1),
                status="analyzed",
                severity="none",
                is_new_finding=False,
            ),
            ImagingStudy(
                id="IMG2",
                patient_id="PIMG1",
                modality="CT",
                body_part="chest",
                study_date=date(2026, 1, 5),
                status="analyzed",
                severity="critical",
                is_new_finding=True,
            ),
            ImagingStudy(
                id="IMG3",
                patient_id="PIMG1",
                modality="XR",
                body_part="hand",
                study_date=date(2026, 1, 1),
                status="pending",
                severity="none",
            ),
        ]
    )
    await db_session.commit()

    headers = await _clinician(client)
    res = await client.get("/api/dashboard/imaging", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["analyzed_count"] == 2
    assert body["critical_finding_count"] == 1
    assert body["new_finding_vs_prior_count"] == 1
    assert body["pending_count"] == 1


async def test_dashboard_ai_metrics(client, db_session):
    p = Patient(id="PAI1", name="AI Patient", age=45, sex="M", medical_record_number="PT-PAI1")
    db_session.add(p)
    db_session.add(
        AIEvaluation(
            id="EV1",
            patient_id="PAI1",
            eval_type="consultation",
            confidence=0.8,
            requires_human_review=True,
            clinician_modified=True,
            clinician_rejected=False,
        )
    )
    db_session.add(
        Consultation(
            id="C1",
            user_id="U-doesnotmatter",
            query="q",
            answer="a",
            risk_level="high",
        )
    )
    await db_session.commit()

    headers = await _clinician(client)
    res = await client.get("/api/dashboard/ai", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["evaluations_count"] == 1
    assert body["consultations_count"] == 1
    assert body["high_risk_prediction_count"] == 1
    assert body["avg_confidence"] == 0.8
    assert body["requires_human_review_count"] == 1
    assert body["clinician_modified_count"] == 1


async def test_dashboard_evidence_with_and_without_support(client, db_session):
    db_session.add_all(
        [
            Consultation(
                id="CE1",
                user_id="U1",
                query="q1",
                answer="a1",
                verification_report={
                    "claims": [{"status": "supported", "evidence_ids": ["src1"]}],
                },
                supported_claim_ratio=1.0,
            ),
            Consultation(
                id="CE2",
                user_id="U1",
                query="q2",
                answer="a2",
                verification_report={"claims": [{"status": "unsupported", "evidence_ids": []}]},
                supported_claim_ratio=0.0,
            ),
            Consultation(id="CE3", user_id="U1", query="q3", answer="a3", verification_report={}),
        ]
    )
    await db_session.commit()

    headers = await _clinician(client)
    res = await client.get("/api/dashboard/evidence", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["recommendations_with_evidence_count"] == 1
    assert body["recommendations_without_evidence_count"] == 1
    assert body["distinct_sources_used"] == 1
    assert body["avg_supported_claim_ratio"] == 0.5


async def test_dashboard_pending_counts_unresolved_and_decisions(client, db_session):
    p = Patient(id="PPEND1", name="Pending Patient", age=45, sex="F", medical_record_number="PT-PPEND1")
    db_session.add(p)
    db_session.add(
        Alert(
            id="ALP1",
            patient_id="PPEND1",
            category="lab",
            severity="high",
            status="active",
            title="Alert",
            source="rule",
        )
    )
    db_session.add(
        Consultation(id="CP1", user_id="U1", query="q", answer="a", risk_level="high", acted_on=None)
    )
    await db_session.commit()

    headers = await _clinician(client)
    res = await client.get("/api/dashboard/pending", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["unresolved_clinical_issues_count"] == 1
    assert body["patients_pending_follow_up_count"] == 1
    assert body["pending_recommendations_count"] == 1
    assert body["cases_requiring_decision_count"] == 1


async def test_dashboard_performance_sensitivity_and_specificity(client, db_session):
    p = Patient(id="PPERF1", name="Perf Patient", age=45, sex="M", medical_record_number="PT-PPERF1")
    db_session.add(p)
    now = datetime.now(timezone.utc)
    db_session.add(
        Alert(
            id="ALPF1",
            patient_id="PPERF1",
            category="lab",
            severity="high",
            status="resolved",
            title="Alert",
            source="rule",
            created_at=now - timedelta(hours=2),
            reviewed_at=now,
        )
    )
    db_session.add_all(
        [
            Consultation(
                id="CPF1", user_id="U1", query="q", answer="a", risk_level="high", outcome="not_improved"
            ),
            Consultation(
                id="CPF2", user_id="U1", query="q", answer="a", risk_level="high", outcome="improved"
            ),
            Consultation(
                id="CPF3", user_id="U1", query="q", answer="a", risk_level="low", outcome="improved"
            ),
            Consultation(
                id="CPF4", user_id="U1", query="q", answer="a", risk_level="low", outcome="not_improved"
            ),
        ]
    )
    await db_session.commit()

    headers = await _clinician(client)
    res = await client.get("/api/dashboard/performance", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["alerts_resolved_count"] == 1
    assert body["avg_alert_response_seconds"] is not None
    assert body["sensitivity"] == 0.5
    assert body["specificity"] == 0.5
    assert body["auc"] is None


async def test_dashboard_bootstrap_combines_stats_agenda_alerts(client):
    headers = await _clinician(client)
    res = await client.get("/api/dashboard/bootstrap", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert "stats" in body
    assert "agenda" in body
    assert "alerts" in body
