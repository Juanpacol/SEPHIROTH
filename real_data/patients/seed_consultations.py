"""Seeds real consultations (actual Gemini agent calls, not fabricated
data) for real patients that don't have any yet — so the AI/Evidence
dashboard tabs have genuine signal for more than just the 2 old demo
patients (P001/P002).

Runs the exact same path `/api/agents/consult` does (`run_consultation`
+ `_persist`), attributed to a real clinician user. One question per
patient, grounded in that patient's own recorded conditions — not a
generic/random prompt.

Idempotent: only processes patients with zero existing consultations, so
it's safe to re-run (e.g. across multiple sessions to respect Gemini's
free-tier rate limit) without ever duplicating a seeded consultation.

    PYTHONPATH=.:platform python3 real_data/patients/seed_consultations.py \
        --limit 5 --user-email jbotero@aztia.co
"""

from __future__ import annotations

import asyncio
import logging

logging.basicConfig(level=logging.INFO)


def _question_for(conditions: list[str]) -> str:
    if not conditions:
        return "What preventive care and screening recommendations apply for this patient's age group?"
    return f"What is the current evidence-based first-line management for {conditions[0]}?"


async def _seed(limit: int, user_email: str) -> int:
    from sqlalchemy import func, select  # noqa: PLC0415

    from api.routers.agents import ConsultRequest, _persist  # noqa: PLC0415
    from core.db import SessionLocal  # noqa: PLC0415
    from data.schemas import Consultation, Patient, User  # noqa: PLC0415
    from sephiroth.models import get_llm_client  # noqa: PLC0415
    from sephiroth.runtime import run_consultation  # noqa: PLC0415

    # A fresh session per patient, not one held open across the whole loop:
    # each consultation makes real, multi-second LLM calls, and Supabase's
    # pooler closes connections that sit idle mid-transaction for too long
    # (hit this exact "connection was closed in the middle of operation"
    # error with a single long-lived session across several patients).
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == user_email))
        if user is None:
            print(
                f"No user found with email {user_email!r} — pass --user-email for an "
                "existing clinician account."
            )
            return 0
        patients = (await session.scalars(select(Patient).order_by(Patient.id))).all()

    seeded = 0
    client = get_llm_client()

    for patient in patients:
        if seeded >= limit:
            break

        async with SessionLocal() as session:
            existing_count = await session.scalar(
                select(func.count()).select_from(Consultation).where(Consultation.patient_id == patient.id)
            )
        if existing_count:
            continue

        question = _question_for(patient.conditions)
        context = {
            "conditions": patient.conditions,
            "medications": patient.medications,
            "lab_results": patient.lab_results,
            "language": "en",
        }
        logging.info("Seeding consultation for patient=%s question=%r", patient.id, question)
        state = await run_consultation(client, query=question, patient_id=patient.id, context=context)
        request = ConsultRequest(query=question, patient_id=patient.id, context=context)

        async with SessionLocal() as session:
            # Re-fetch `user` in this session — SQLAlchemy objects are bound
            # to the session that loaded them.
            persist_user = await session.get(User, user.id)
            await _persist(session, persist_user, request, dict(state))
        seeded += 1

    return seeded


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Seed real agent consultations for real patients")
    parser.add_argument("--limit", type=int, default=5, help="Max new consultations to run this invocation")
    parser.add_argument(
        "--user-email", default="jbotero@aztia.co", help="Clinician user to attribute these to"
    )
    args = parser.parse_args()

    seeded = asyncio.run(_seed(args.limit, args.user_email))
    print(f"Seeded {seeded} new consultation(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
