"""Seed real consultations using Claude API instead of Gemini/Groq.

Direct Claude calls, no agent orchestration — simple, fast seeding of realistic
clinical consultation data for real patients.

    PYTHONPATH=.:platform CLAUDE_API_KEY=sk-ant-... python3 \
        real_data/patients/seed_consultations_claude.py --limit 5
"""

from __future__ import annotations

import asyncio
import logging

import anthropic

logging.basicConfig(level=logging.INFO)


def _question_for(conditions: list[str]) -> str:
    if not conditions:
        return "What preventive care and screening recommendations apply for this patient's age group?"
    return f"What is the current evidence-based first-line management for {conditions[0]}?"


def _context_summary(patient) -> str:
    parts = []
    if patient.conditions:
        parts.append(f"Conditions: {', '.join(patient.conditions)}")
    if patient.medications:
        parts.append(f"Medications: {', '.join(patient.medications)}")
    if patient.lab_results:
        labs_str = ", ".join(f"{k}={v}" for k, v in patient.lab_results.items())
        parts.append(f"Labs: {labs_str}")
    return " | ".join(parts) if parts else "No recorded conditions/medications/labs"


async def _seed(limit: int, user_email: str) -> int:
    from sqlalchemy import func, select  # noqa: PLC0415

    from api.routers.agents import ConsultRequest, _persist  # noqa: PLC0415
    from core.config import settings  # noqa: PLC0415
    from core.db import SessionLocal  # noqa: PLC0415
    from data.schemas import Consultation, Patient, User  # noqa: PLC0415

    if not settings.claude_api_key:
        print("CLAUDE_API_KEY not set in .env or environment")
        return 0
    api_key = settings.claude_api_key
    model = settings.claude_model

    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == user_email))
        if user is None:
            print(f"No user found with email {user_email!r}")
            return 0
        patients = (await session.scalars(select(Patient).order_by(Patient.id))).all()

    seeded = 0
    client = anthropic.Anthropic(api_key=api_key)

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

        question = _question_for(patient.conditions)
        context_str = _context_summary(patient)

        logging.info("Seeding consultation for patient=%s question=%r", patient.id[:8], question)

        # Call Claude directly for realistic clinical response
        try:
            response = client.messages.create(
                model=model,
                max_tokens=1024,
                messages=[
                    {
                        "role": "user",
                        "content": f"""You are a clinical decision support AI. A clinician asks:

Question: {question}

Patient context: {context_str}

Provide a concise, evidence-based answer (2-3 sentences). Be direct and actionable.""",
                    }
                ],
            )
            answer = response.content[0].text
        except Exception as e:
            logging.error("Claude API error for patient %s: %s", patient.id[:8], e)
            continue

        # Persist as a real consultation
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
        logging.info("Seeded consultation for patient=%s", patient.id[:8])

    return seeded


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Seed real agent consultations using Claude API")
    parser.add_argument("--limit", type=int, default=5, help="Max new consultations to run")
    parser.add_argument(
        "--user-email", default="jbotero@aztia.co", help="Clinician user to attribute these to"
    )
    args = parser.parse_args()

    seeded = asyncio.run(_seed(args.limit, args.user_email))
    print(f"Seeded {seeded} new consultation(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
