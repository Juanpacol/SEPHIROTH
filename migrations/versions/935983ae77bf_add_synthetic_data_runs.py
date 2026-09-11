"""add synthetic_data_runs

Revision ID: 935983ae77bf
Revises: 65f4c9113b25
Create Date: 2026-09-10

Additive-only: one new table, no data change. `synthetic_data_runs` is the
once-per-day idempotency guard for the daily synthetic-data pipeline
(`sephiroth.safety.synthetic_daily`) — `completed_at` stays null until every
downstream step of that day's run succeeds, so a row that exists but never
completed means "retry," not "already done."
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "935983ae77bf"
down_revision: Union[str, Sequence[str], None] = "65f4c9113b25"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "synthetic_data_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_date", sa.Date(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("labs_inserted", sa.Integer(), server_default="0", nullable=False),
        sa.Column("alerts_created", sa.Integer(), server_default="0", nullable=False),
        sa.Column("patients_touched", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_date", name="uq_synthetic_data_runs_run_date"),
    )


def downgrade() -> None:
    op.drop_table("synthetic_data_runs")
