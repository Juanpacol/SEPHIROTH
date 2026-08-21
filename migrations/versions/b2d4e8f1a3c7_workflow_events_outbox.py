"""workflow_events outbox table (SPEC-010)

Revision ID: b2d4e8f1a3c7
Revises: a1c9f3d7e6b2
Create Date: 2026-08-21 01:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2d4e8f1a3c7"
down_revision: Union[str, Sequence[str], None] = "a1c9f3d7e6b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "workflow_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=14), server_default="pending", nullable=False),
        sa.Column("dispatched_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','dispatched','no_subscriber')", name="ck_workflow_event_status"
        ),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workflow_events_event_type"), "workflow_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_workflow_events_patient_id"), "workflow_events", ["patient_id"], unique=False)
    op.create_index(op.f("ix_workflow_events_status"), "workflow_events", ["status"], unique=False)
    op.create_index(op.f("ix_workflow_events_created_at"), "workflow_events", ["created_at"], unique=False)
    op.create_index(
        "ix_workflow_events_status_created", "workflow_events", ["status", "created_at"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_workflow_events_status_created", table_name="workflow_events")
    op.drop_index(op.f("ix_workflow_events_created_at"), table_name="workflow_events")
    op.drop_index(op.f("ix_workflow_events_status"), table_name="workflow_events")
    op.drop_index(op.f("ix_workflow_events_patient_id"), table_name="workflow_events")
    op.drop_index(op.f("ix_workflow_events_event_type"), table_name="workflow_events")
    op.drop_table("workflow_events")
