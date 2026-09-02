#!/usr/bin/env python3
"""Generate synthetic consultations via the API."""

import asyncio
import sys

import httpx

sys.path.insert(0, ".")
sys.path.insert(0, "platform")

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from core.config import settings
from data.schemas import Patient

API_URL = "http://localhost:8000"
EMAIL = "test-clinician@example.com"
PASSWORD = "TestPassword123!"


async def register_clinician() -> str:
    """Register a clinician account and return JWT token."""
    async with httpx.AsyncClient() as client:
        # Check if user exists
        response = await client.post(
            f"{API_URL}/api/auth/register",
            json={"email": EMAIL, "name": "Test Clinician", "password": PASSWORD},
        )

        if response.status_code == 409:
            print("  ℹ Clinician already exists, logging in...")
        elif response.status_code != 201:
            print(f"  ✗ Registration failed: {response.text}")
            return None

        # Login
        response = await client.post(
            f"{API_URL}/api/auth/login",
            json={"email": EMAIL, "password": PASSWORD},
        )

        if response.status_code != 200:
            print(f"  ✗ Login failed: {response.text}")
            return None

        token = response.json()["access_token"]
        print(f"  ✓ Authenticated as {EMAIL}")
        return token


def generate_clinical_query(patient: dict) -> str:
    """Generate a realistic clinical query for the patient."""
    conditions = ", ".join(patient["conditions"][:2])
    medications = ", ".join(patient["medications"][:2])
    lab_values = list(patient["lab_results"].values())
    latest_lab = lab_values[0] if lab_values else "pending"
    allergies = ", ".join(patient["allergies"]) if patient["allergies"] else "NKDA"
    queries = [
        f"Patient {patient['name']}, {patient['age']}y, {patient['sex']}. Chief complaint: chest pain and "
        f"dyspnea. Conditions: {conditions}. Recent labs show elevated BNP. "
        f"Risk assessment and recommendations?",
        f"{patient['name']} ({patient['age']}) presents with fatigue and weight gain. PMH: {conditions}. "
        f"On medications: {medications}. Differential diagnosis?",
        f"Follow-up for {patient['name']}: monitoring {patient['conditions'][0]}. "
        f"Labs today: {latest_lab}. Adjust treatment plan?",
        f"{patient['name']}, {patient['age']}y. Allergies: {allergies}. "
        f"New medication request: evaluate interactions and safety.",
    ]
    return queries[hash(patient["id"]) % len(queries)]


async def generate_consultations():
    """Generate consultations for all patients."""
    # Register/login
    print("Registering clinician...")
    token = await register_clinician()
    if not token:
        return

    # Get patients
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        patients = (await session.scalars(select(Patient))).all()
        print(f"\nGenerating consultations for {len(patients)} patients...\n")

        async with httpx.AsyncClient(timeout=120.0) as client:
            for i, patient in enumerate(patients[:5], 1):  # Limit to 5 for demo
                patient_dict = {
                    "id": patient.id,
                    "name": patient.name,
                    "age": patient.age,
                    "sex": patient.sex,
                    "conditions": patient.conditions,
                    "medications": patient.medications,
                    "allergies": patient.allergies,
                    "lab_results": patient.lab_results,
                }

                query = generate_clinical_query(patient_dict)
                print(f"[{i}/{min(5, len(patients))}] {patient.name}...", end=" ", flush=True)

                try:
                    async with client.stream(
                        "POST",
                        f"{API_URL}/api/agents/consult/stream",
                        headers={"Authorization": f"Bearer {token}"},
                        json={
                            "patient_id": patient.id,
                            "query": query,
                        },
                    ) as response:
                        if response.status_code != 200:
                            body = await response.aread()
                            print(f"✗ ({response.status_code}: {body[:80]})")
                            continue

                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                pass  # Process SSE data

                    print("✓")

                except Exception as e:
                    print(f"✗ ({str(e)[:60]})")

    await engine.dispose()
    print("\n✓ Consultations generated")


async def main():
    try:
        await generate_consultations()
    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
