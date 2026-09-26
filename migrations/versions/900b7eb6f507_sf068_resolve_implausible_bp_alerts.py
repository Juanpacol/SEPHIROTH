"""resolve implausible blood-pressure alerts

SF068: the synthetic daily job parsed "131.4 mm[Hg]" as 1314, so active
risk-engine alerts exist with details like "BP 1314/653 (≥ 160/100)". The
risk engine no longer raises these, but an already-persisted alert stays
active until someone closes it. This resolves only alerts whose recorded
reading no body could produce (systolic outside 40-300 or diastolic outside
20-200, the `VITAL_SPECS` physiological ranges, copied here so the migration
never changes when app code does). A plausible reading is never touched:
auto-resolving a real alert is a clinician's call (`alerts.py`).

Data-only, no schema change. Downgrade is a no-op: re-opening alerts for
readings that never happened would reintroduce the bug.

Revision ID: 900b7eb6f507
Revises: 32224bacb219
Create Date: 2026-09-26 14:00:00.000000

"""

import re
from datetime import datetime, timezone
from typing import Optional, Sequence, Tuple, Union

import sqlalchemy as sa
from alembic import op

revision: str = "900b7eb6f507"
down_revision: Union[str, Sequence[str], None] = "32224bacb219"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BP_DETAIL_RE = re.compile(r"BP\s+(-?\d+(?:\.\d+)?)\s*/\s*(-?\d+(?:\.\d+)?)")
_SYSTOLIC_RANGE = (40.0, 300.0)
_DIASTOLIC_RANGE = (20.0, 200.0)


def _reading(detail: Optional[str]) -> Optional[Tuple[float, float]]:
    match = _BP_DETAIL_RE.search(detail or "")
    return (float(match.group(1)), float(match.group(2))) if match else None


def is_implausible_bp_detail(detail: Optional[str]) -> bool:
    reading = _reading(detail)
    if reading is None:
        return False
    systolic, diastolic = reading
    return not (
        _SYSTOLIC_RANGE[0] <= systolic <= _SYSTOLIC_RANGE[1]
        and _DIASTOLIC_RANGE[0] <= diastolic <= _DIASTOLIC_RANGE[1]
    )


def resolve_implausible_bp_alerts(conn: sa.engine.Connection) -> int:
    rows = conn.execute(
        sa.text(
            "SELECT id, detail FROM alerts "
            "WHERE source = 'risk_engine' AND status = 'active' AND title = 'Hypertensive range'"
        )
    ).all()
    ids = [row.id for row in rows if is_implausible_bp_detail(row.detail)]
    if not ids:
        return 0
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    conn.execute(
        sa.text("UPDATE alerts SET status = 'resolved', resolved_at = :now WHERE id IN :ids").bindparams(
            sa.bindparam("ids", expanding=True)
        ),
        {"now": now, "ids": ids},
    )
    return len(ids)


def upgrade() -> None:
    resolve_implausible_bp_alerts(op.get_bind())


def downgrade() -> None:
    pass
