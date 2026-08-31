#!/usr/bin/env python3
"""Analyze real medical images (from Wikimedia Commons, public domain) via
the vision API and save results as TimelineEvents so the dashboard/imaging
page has a real analysis history to preview."""

import asyncio
import sys
from datetime import date, timedelta

import httpx

sys.path.insert(0, ".")
sys.path.insert(0, "platform")

from core.config import settings
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from data.schemas import Patient, TimelineEvent

API_URL = "http://localhost:8000"
EMAIL = "test-clinician@example.com"
PASSWORD = "TestPassword123!"

IMAGE_DIR = "/tmp/sephiroth-imaging-uploads"

# (filename, modality, clinical_focus)
IMAGES = [
    ("chest_xray_3.jpg", "xray", "lateral view abnormalities"),
    ("mri_brain_2.jpg", "mri", "brain structures"),
    ("mri_brain_tumor.jpg", "mri", "mass lesions"),
    ("pathology_1.jpg", "pathology", "cell morphology"),
    ("pathology_2.jpg", "pathology", "tissue architecture"),
]


async def login() -> str:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_URL}/api/auth/login",
            json={"email": EMAIL, "password": PASSWORD},
        )
        if response.status_code != 200:
            print(f"  Login failed: {response.text}")
            return None
        return response.json()["access_token"]


async def analyze_images():
    token = await login()
    if not token:
        return
    print(f"  Authenticated\n")

    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        patients = (await session.scalars(select(Patient))).all()
        if len(patients) < len(IMAGES):
            print("Not enough patients for all images")
            return

        async with httpx.AsyncClient(timeout=90.0) as client:
            for i, (filename, modality, focus) in enumerate(IMAGES):
                patient = patients[3 + i]  # offset past patients already imaged
                image_path = f"{IMAGE_DIR}/{filename}"

                print(f"[{i+1}/{len(IMAGES)}] {patient.name} - {filename} ({modality})...", end=" ", flush=True)

                if i > 0:
                    await asyncio.sleep(8)  # avoid Gemini free-tier rate limit

                try:
                    # Describe the image via vision API
                    describe_response = await client.post(
                        f"{API_URL}/api/medical/imaging/describe",
                        headers={"Authorization": f"Bearer {token}"},
                        json={"image_path": image_path, "clinical_focus": focus},
                    )

                    if describe_response.status_code != 200:
                        print(f"✗ describe failed ({describe_response.status_code})")
                        continue

                    result = describe_response.json()
                    description = result.get("description") or result.get("result", {}).get("description", "")

                    if not description:
                        description = str(result)[:500]

                    # Save as TimelineEvent (type=imaging), referencing image path
                    event_date = date.today() - timedelta(days=(len(IMAGES) - i) * 3)
                    event = TimelineEvent(
                        patient_id=patient.id,
                        date=event_date,
                        type="imaging",
                        title=f"{modality.upper()} imaging analysis",
                        detail=f"[image_path:{image_path}] {description[:800]}",
                        ai_generated=True,
                    )
                    session.add(event)
                    await session.commit()

                    print(f"✓ ({len(description)} chars)")

                except Exception as e:
                    print(f"✗ ({str(e)[:60]})")

    await engine.dispose()
    print("\n✓ Imaging analysis complete")


async def main():
    try:
        await analyze_images()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
