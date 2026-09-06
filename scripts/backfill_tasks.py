#!/usr/bin/env python3
"""One-time backfill: file the work that already exists as tasks (SPEC-018).

`tasks` is created empty. Every alert raised and every approval left pending
before the table existed has no row in it, so switching `enable_task_inbox` on
against a fresh table would show a clinician an empty inbox and call it
"nothing to do" — which is worse than the derived list it replaced, because it
looks authoritative.

Deliberately a script and not part of the Alembic migration. It needs the SLA
table and the adapter registry, which are application code a migration must not
import; and a migration that half-succeeds leaves a schema change and a data
change entangled. Safe to re-run: every insert goes through
`create_task`, whose `dedupe_key` makes a second pass a no-op.

Derived work — worsening trends, drug interactions, unreviewed results — is
NOT backfilled here. The tick's `sync_derived_tasks` re-derives all of it from
current data within five minutes of the flag going on, and doing it twice would
only risk two versions of the same rule disagreeing.

Usage:
    PYTHONPATH=.:platform .venv/bin/python scripts/backfill_tasks.py [--dry-run]
"""

import argparse
import asyncio
import sys

sys.path.insert(0, ".")
sys.path.insert(0, "platform")

from sqlalchemy import select  # noqa: E402

from api.services import task_service  # noqa: E402
from core.db import SessionLocal  # noqa: E402
from data.schemas import Alert, PendingAction  # noqa: E402


async def main(dry_run: bool) -> None:
    async with SessionLocal() as session:
        alerts = (await session.scalars(select(Alert).where(Alert.status.in_(("active", "reviewed"))))).all()
        approvals = (
            await session.scalars(select(PendingAction).where(PendingAction.status == "pending"))
        ).all()

        print(f"{len(alerts)} open alerts, {len(approvals)} pending approvals to file.")
        if dry_run:
            print("--dry-run: no writes made.")
            return

        created = 0
        for alert in alerts:
            _, was_created = await task_service.create_task(
                session,
                source_type="alert",
                source_id=alert.id,
                category="alert",
                severity=alert.severity,
                title=alert.title,
                detail=alert.detail or "",
                patient_id=alert.patient_id,
                dedupe_key=f"alert:{alert.id}",
                context={"alert_category": alert.category, "source": alert.source},
                # The task inherits the alert's own age, so an alert that has
                # been open for two days is immediately overdue rather than
                # looking like it was raised just now.
                now=alert.created_at,
            )
            created += 1 if was_created else 0

        for action in approvals:
            _, was_created = await task_service.create_task(
                session,
                source_type="approval",
                source_id=action.id,
                category="approval",
                severity="medium",
                title="Mensaje al paciente esperando aprobación",
                patient_id=action.patient_id,
                dedupe_key=f"approval:{action.id}",
                context={"action_type": action.action_type},
                source_deadline=action.expires_at,
                now=action.created_at,
            )
            created += 1 if was_created else 0

        await session.commit()
        print(f"Done. {created} task(s) created; the rest already existed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report counts, write nothing.")
    args = parser.parse_args()
    asyncio.run(main(args.dry_run))
