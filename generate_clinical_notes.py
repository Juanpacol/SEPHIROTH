#!/usr/bin/env python3
"""Generate synthetic clinical notes via the API (auto-extracts timeline events)."""

import asyncio
import sys

import httpx
from openai import OpenAI

sys.path.insert(0, ".")
sys.path.insert(0, "platform")

from core.config import settings
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from data.schemas import Patient

API_URL = "http://localhost:8000"
EMAIL = "test-clinician@example.com"
PASSWORD = "TestPassword123!"


async def login() -> str:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_URL}/api/auth/login",
            json={"email": EMAIL, "password": PASSWORD},
        )
        if response.status_code != 200:
            print(f"  ✗ Login failed: {response.text}")
            return None
        return response.json()["access_token"]


def generate_note_content(openai_client: OpenAI, patient: dict) -> str:
    """Use OpenAI to write a realistic progress note."""
    prompt = f"""Write a brief, realistic clinical progress note (3-5 sentences) for:
Patient: {patient['name']}, {patient['age']}y {patient['sex']}
Conditions: {', '.join(patient['conditions'])}
Medications: {', '.join(patient['medications'])}

Include vital signs, a brief assessment, and a plan. Write in clinical shorthand style
(like a real doctor's note), mentioning at least one lab value or vital sign with a number.
No markdown, just plain text."""

    response = openai_client.chat.completions.create(
        model="gpt-3.5-turbo",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content.strip()


async def generate_notes():
    token = await login()
    if not token:
        return

    if not settings.openai_api_key:
        print("ERROR: OPENAI_API_KEY not set")
        return

    openai_client = OpenAI(api_key=settings.openai_api_key)

    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        patients = (await session.scalars(select(Patient))).all()
        print(f"Generating clinical notes for {len(patients)} patients...\n")

        async with httpx.AsyncClient(timeout=60.0) as client:
            for i, patient in enumerate(patients, 1):
                patient_dict = {
                    "id": patient.id,
                    "name": patient.name,
                    "age": patient.age,
                    "sex": patient.sex,
                    "conditions": patient.conditions or ["general health maintenance"],
                    "medications": patient.medications or ["none"],
                }

                print(f"[{i}/{len(patients)}] {patient.name}...", end=" ", flush=True)

                try:
                    content = generate_note_content(openai_client, patient_dict)

                    response = await client.post(
                        f"{API_URL}/api/patients/{patient.id}/notes",
                        headers={"Authorization": f"Bearer {token}"},
                        json={"content": content, "note_type": "progress_note"},
                    )

                    if response.status_code == 201:
                        data = response.json()
                        print(f"✓ ({data.get('entities_found', 0)} entities, {len(data.get('events_added', []))} events)")
                    else:
                        print(f"✗ ({response.status_code}: {response.text[:60]})")

                except Exception as e:
                    print(f"✗ ({str(e)[:60]})")

    await engine.dispose()
    print("\n✓ Clinical notes generated")


async def main():
    try:
        await generate_notes()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
