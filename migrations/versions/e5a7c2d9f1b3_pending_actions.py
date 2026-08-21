"""pending_actions -- human-in-the-loop approval gate (SPEC-013)

Revision ID: e5a7c2d9f1b3
Revises: d4f6a1c3e5b9
Create Date: 2026-08-21 04:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5a7c2d9f1b3"
down_revision: Union[str, Sequence[str], None] = "d4f6a1c3e5b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "pending_actions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workflow_step_id", sa.String(length=36), nullable=True),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("action_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=12), server_default="pending", nullable=False),
        sa.Column("draft_text", sa.Text(), nullable=False),
        sa.Column("draft_source", sa.String(length=10), server_default="template", nullable=False),
        sa.Column("draft_model", sa.String(length=64), nullable=True),
        sa.Column("final_text", sa.Text(), nullable=False),
        sa.Column("proposed_payload", sa.JSON(), nullable=False),
        sa.Column("assigned_to_user_id", sa.String(length=36), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("reviewed_by", sa.String(length=36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("reject_reason", sa.String(length=300), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('pending','approved','rejected','expired')", name="ck_pending_action_status"),
        sa.CheckConstraint("draft_source IN ('template','llm')", name="ck_pending_action_draft_source"),
        sa.CheckConstraint(
            "status NOT IN ('approved','rejected') OR reviewed_by IS NOT NULL",
            name="ck_pending_action_requires_reviewer",
        ),
        sa.ForeignKeyConstraint(["workflow_step_id"], ["workflow_steps.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.ForeignKeyConstraint(["assigned_to_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_step_id", name="uq_pending_action_workflow_step"),
    )
    op.create_index(op.f("ix_pending_actions_patient_id"), "pending_actions", ["patient_id"], unique=False)
    op.create_index(op.f("ix_pending_actions_action_type"), "pending_actions", ["action_type"], unique=False)
    op.create_index(op.f("ix_pending_actions_status"), "pending_actions", ["status"], unique=False)
    op.create_index(
        op.f("ix_pending_actions_assigned_to_user_id"), "pending_actions", ["assigned_to_user_id"], unique=False
    )
    op.create_index(op.f("ix_pending_actions_expires_at"), "pending_actions", ["expires_at"], unique=False)
    op.create_index(op.f("ix_pending_actions_created_at"), "pending_actions", ["created_at"], unique=False)
    op.create_index(
        "ix_pending_actions_status_created", "pending_actions", ["status", "created_at"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_pending_actions_status_created", table_name="pending_actions")
    op.drop_index(op.f("ix_pending_actions_created_at"), table_name="pending_actions")
    op.drop_index(op.f("ix_pending_actions_expires_at"), table_name="pending_actions")
    op.drop_index(op.f("ix_pending_actions_assigned_to_user_id"), table_name="pending_actions")
    op.drop_index(op.f("ix_pending_actions_status"), table_name="pending_actions")
    op.drop_index(op.f("ix_pending_actions_action_type"), table_name="pending_actions")
    op.drop_index(op.f("ix_pending_actions_patient_id"), table_name="pending_actions")
    op.drop_table("pending_actions")
