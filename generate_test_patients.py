#!/usr/bin/env python3
"""Generate synthetic test patients using OpenAI API and insert into DB."""

import asyncio
import json
import sys
import uuid
from typing import Optional

from openai import OpenAI
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, ".")
sys.path.insert(0, "platform")

from core.config import settings
from data.schemas import Patient


def generate_patient_data(client: OpenAI, count: int = 3) -> list[dict]:
    """Use OpenAI to generate realistic synthetic patient data."""
    prompt = f"""Generate {count} realistic synthetic medical patient records in JSON format.
Each patient should have:
- name: realistic full name
- age: integer 18-85
- sex: "M" or "F"
- medical_record_number: unique MRN format (e.g., "P001234")
- conditions: list of 2-4 realistic chronic conditions (e.g., ["Type 2 Diabetes", "Hypertension"])
- medications: list of 3-5 realistic medications with dosages
- allergies: list of 0-3 drug allergies
- lab_results: dict with realistic lab values (e.g., {{"glucose": "145 mg/dL", "creatinine": "0.9 mg/dL"}})

Return ONLY valid JSON array, no markdown or explanation."""

    message = client.chat.completions.create(
        model="gpt-3.5-turbo",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    response_text = message.choices[0].message.content
    try:
        patients = json.loads(response_text)
        return patients
    except json.JSONDecodeError:
        print(f"Failed to parse OpenAI response: {response_text}")
        return []


async def insert_patients(patients: list[dict]) -> None:
    """Insert generated patients into database."""
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        for patient_data in patients:
            patient = Patient(
                id=f"PAT-{str(uuid.uuid4())[:8].upper()}",
                name=patient_data["name"],
                age=patient_data["age"],
                sex=patient_data["sex"],
                medical_record_number=patient_data["medical_record_number"],
                conditions=patient_data.get("conditions", []),
                medications=patient_data.get("medications", []),
                allergies=patient_data.get("allergies", []),
                lab_results=patient_data.get("lab_results", {}),
                status="active",
            )
            session.add(patient)
            print(f"  ✓ {patient.name} ({patient.age}y, {patient.sex})")

        await session.commit()
        print(f"\n✓ {len(patients)} patients inserted")

    await engine.dispose()


async def main():
    if not settings.openai_api_key:
        print("ERROR: OPENAI_API_KEY not set in .env")
        sys.exit(1)

    client = OpenAI(api_key=settings.openai_api_key)

    print("Generating synthetic patients with OpenAI...")
    patients = generate_patient_data(client, count=5)

    if not patients:
        print("No patients generated")
        sys.exit(1)

    print(f"\nGenerated {len(patients)} patients:")
    for p in patients:
        print(f"  • {p['name']} ({p['age']}y, {p['sex']}) - {', '.join(p.get('conditions', [])[:2])}")

    print("\nInserting into database...")
    await insert_patients(patients)


if __name__ == "__main__":
    asyncio.run(main())
