#!/usr/bin/env python3
"""Test workflow automation with generated patients."""

import asyncio
import sys
from datetime import datetime, timezone
from uuid import uuid4

sys.path.insert(0, ".")
sys.path.insert(0, "platform")

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from core.config import settings
from data.schemas import Patient, Workflow, WorkflowStep
import api.workflows.definitions  # noqa: F401 - registers step types
from api.workflows.registry import STEP_TYPES


async def create_test_workflows():
    """Create alert_refresh workflows for all patients."""
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Get all patients
        patients = (await session.scalars(select(Patient))).all()
        print(f"Found {len(patients)} patients. Creating workflows...")

        created = 0
        for patient in patients:
            # Check if workflow already exists
            existing = (
                await session.scalars(
                    select(Workflow).where(
                        Workflow.definition_key == "alert_refresh",
                        Workflow.patient_id == patient.id,
                        Workflow.status == "active",
                    )
                )
            ).first()

            if existing:
                print(f"  ⊘ {patient.name} - workflow already exists")
                continue

            # Create workflow
            spec = STEP_TYPES.get("alert_refresh")
            if not spec:
                print(f"  ✗ alert_refresh step type not found")
                continue

            workflow = Workflow(
                id=f"WF-{uuid4().hex[:8]}",
                definition_key="alert_refresh",
                patient_id=patient.id,
                status="active",
                context={},
            )
            session.add(workflow)

            # Create step
            step = WorkflowStep(
                id=f"WS-{uuid4().hex[:8]}",
                workflow_id=workflow.id,
                step_key="refresh",
                step_type="alert_refresh",
                status="pending",
                due_at=now,
                run_after=now,
                max_lateness_seconds=spec.max_lateness_seconds,
                max_attempts=spec.max_attempts,
            )
            session.add(step)
            print(f"  ✓ {patient.name} - workflow created")
            created += 1

        await session.commit()
        print(f"\n✓ {created} workflows created")

    await engine.dispose()


async def main():
    try:
        await create_test_workflows()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
