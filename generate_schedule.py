#!/usr/bin/env python3
"""Populate scheduling data via the real API — availability rules (Mon-Fri
09:00-17:00) for the test clinician, then a spread of booked appointments
across patients over the next two weeks. Goes through the actual endpoints
(not direct DB inserts) so overlap/conflict validation runs for real."""

import asyncio
import sys
from datetime import date, timedelta

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


async def login() -> str:
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{API_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
        if response.status_code != 200:
            print(f"Login failed: {response.text}")
            return None
        return response.json()["access_token"]


async def main():
    token = await login()
    if not token:
        return
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        me = (await client.get(f"{API_URL}/api/auth/me", headers=headers)).json()
        clinician_id = me["id"]
        print(f"Clinician: {me['name']} ({clinician_id})\n")

        # 1) Availability rules — Mon-Fri, 09:00-17:00, 30-min slots.
        print("Creating availability rules (Mon-Fri 09:00-17:00)...")
        for weekday in range(5):  # 0=Mon .. 4=Fri
            resp = await client.post(
                f"{API_URL}/api/scheduling/availability",
                headers=headers,
                json={
                    "weekday": weekday,
                    "start_time": "09:00",
                    "end_time": "17:00",
                    "timezone": "America/Bogota",
                    "slot_minutes": 30,
                },
            )
            status = "created" if resp.status_code == 201 else f"skip ({resp.status_code})"
            print(f"  weekday={weekday}: {status}")

        # 2) Fetch open slots for the next 14 days.
        today = date.today()
        horizon = today + timedelta(days=14)
        resp = await client.get(
            f"{API_URL}/api/scheduling/slots",
            headers=headers,
            params={"clinician_id": clinician_id, "from": today.isoformat(), "to": horizon.isoformat()},
        )
        slots = resp.json().get("slots", [])
        print(f"\n{len(slots)} open slots in the next 14 days")

        if not slots:
            print("No slots available — skipping appointment booking")
            return

        # 3) Book appointments for a spread of patients across some slots.
        engine = create_async_engine(settings.database_url, echo=False)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            patients = (await session.scalars(select(Patient))).all()

        booked = 0
        modes = ["in_person", "telehealth"]
        # One appointment per business day-ish, spread across the morning slots.
        chosen_slots = slots[::3][:12]  # every 3rd slot, up to 12 appointments

        for i, slot in enumerate(chosen_slots):
            patient = patients[i % len(patients)]
            mode = modes[i % 2]
            start_at = slot["start_at"]
            if not start_at.endswith("Z") and "+" not in start_at:
                start_at += "Z"
            resp = await client.post(
                f"{API_URL}/api/scheduling/appointments",
                headers=headers,
                json={
                    "clinician_id": clinician_id,
                    "patient_id": patient.id,
                    "start_at": start_at,
                    "mode": mode,
                },
            )
            if resp.status_code == 201:
                booked += 1
                print(f"  ✓ {patient.name} @ {slot['start_at']} ({mode})")
            else:
                print(f"  ✗ {patient.name} @ {slot['start_at']}: {resp.status_code} {resp.text[:80]}")

        await engine.dispose()
        print(f"\n✓ {booked} appointments booked")


if __name__ == "__main__":
    asyncio.run(main())
