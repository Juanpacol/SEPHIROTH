"""Seed mock consultations with realistic answers for MVP dashboard.

Generates context-aware clinical responses for real patients without LLM calls.
Responses are fabricated but semantically relevant to each patient's conditions.

    PYTHONPATH=.:platform python3 real_data/patients/seed_consultations_mock.py --limit 10
"""

from __future__ import annotations

import asyncio
import logging

logging.basicConfig(level=logging.INFO)

# Mock responses template by condition
MOCK_RESPONSES = {
    "Acute bronchitis": (
        "First-line management focuses on symptomatic relief. Supportive care includes "
        "rest, hydration, and acetaminophen for fever/pain. Cough suppressants may help "
        "with sleep disturbance. Most cases resolve within 2-3 weeks. Antibiotics are NOT "
        "routinely indicated unless secondary bacterial infection is suspected."
    ),
    "Anemia": (
        "Management depends on severity and cause. Initial evaluation should include iron studies, "
        "B12, and folate levels. Iron supplementation is first-line for iron-deficiency anemia. "
        "For other causes, address underlying etiology. Monitor hemoglobin response in 4-6 weeks. "
        "Transfusion considered only if hemoglobin <7 g/dL or symptomatic at higher levels."
    ),
    "Type 2 Diabetes": (
        "First-line treatment combines lifestyle modification (diet, exercise, weight loss) with "
        "metformin monotherapy if HbA1c >6.5%. Add second agent if HbA1c remains >7% after 3 months. "
        "GLP-1 agonist or SGLT2 inhibitor preferred if cardiovascular or renal disease present. "
        "Target HbA1c 7% for most; individualize based on age and comorbidities."
    ),
    "Acute viral pharyngitis": (
        "Supportive care is primary treatment. Throat lozenges, warm liquids, and acetaminophen "
        "for pain/fever. Avoid NSAIDs if renal/cardiac disease present. Antibiotics NOT indicated "
        "for viral infection. Return precautions for severe dysphagia, respiratory distress, or "
        "signs of peritonsillar abscess (unilateral swelling, voice changes)."
    ),
}


def _mock_answer_for(conditions: list[str]) -> str:
    """Generate a plausible response based on patient conditions."""
    if not conditions:
        return (
            "Preventive care for this patient should include age-appropriate screening "
            "(blood pressure, cholesterol, cancer screening), immunizations (annual flu, "
            "COVID-19), and counseling on lifestyle (exercise, nutrition, stress management). "
            "Consider cardiovascular risk assessment based on family history and comorbidities."
        )
    condition = conditions[0]
    return MOCK_RESPONSES.get(condition, _generic_response(condition))


def _generic_response(condition: str) -> str:
    """Fallback generic response for unmapped conditions."""
    return (
        f"For {condition}, evidence-based management involves comprehensive evaluation "
        f"of severity, underlying causes, and relevant comorbidities. Treatment should be "
        f"individualized based on patient factors, existing medications, and guideline-concordant "
        f"recommendations. Regular monitoring and reassessment at follow-up is essential."
    )


async def _seed(limit: int, user_email: str) -> int:
    from sqlalchemy import func, select  # noqa: PLC0415

    from api.routers.agents import ConsultRequest, _persist  # noqa: PLC0415
    from core.db import SessionLocal  # noqa: PLC0415
    from data.schemas import Consultation, Patient, User  # noqa: PLC0415

    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == user_email))
        if user is None:
            print(f"No user found with email {user_email!r}")
            return 0
        patients = (await session.scalars(select(Patient).order_by(Patient.id))).all()

    seeded = 0

    for patient in patients:
        if seeded >= limit:
            break

        async with SessionLocal() as session:
            existing_count = await session.scalar(
                select(func.count()).select_from(Consultation).where(Consultation.patient_id == patient.id)
            )
        if existing_count:
            logging.info(
                "Patient %s already has %d consultation(s), skipping", patient.id[:8], existing_count
            )
            continue

        condition = patient.conditions[0] if patient.conditions else "this patient"
        question = f"What is the current evidence-based first-line management for {condition}?"
        answer = _mock_answer_for(patient.conditions)

        logging.info("Seeding mock consultation for patient=%s", patient.id[:8])

        request = ConsultRequest(query=question, patient_id=patient.id, context={})
        state = {
            "final_answer": answer,
            "agent_outputs": {},
            "tool_calls": [],
            "citation_report": {},
            "verification_report": {"claims": []},
            "abstention": None,
            "trace": None,
        }

        async with SessionLocal() as session:
            persist_user = await session.get(User, user.id)
            await _persist(session, persist_user, request, state)
        seeded += 1
        logging.info("Seeded mock consultation for patient=%s", patient.id[:8])

    return seeded


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Seed mock clinical consultations for MVP")
    parser.add_argument("--limit", type=int, default=10, help="Max new consultations to create")
    parser.add_argument("--user-email", default="jbotero@aztia.co", help="Clinician user to attribute to")
    args = parser.parse_args()

    seeded = asyncio.run(_seed(args.limit, args.user_email))
    print(f"Seeded {seeded} mock consultation(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
