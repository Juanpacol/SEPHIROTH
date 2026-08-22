"""workflow automation substrate (workflows, workflow_steps) + notifications.dedupe_key

Revision ID: a1c9f3d7e6b2
Revises: 742cbbb2465b
Create Date: 2026-08-21 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1c9f3d7e6b2"
down_revision: Union[str, Sequence[str], None] = "742cbbb2465b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "workflows",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("definition_key", sa.String(length=60), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("appointment_id", sa.String(length=36), nullable=True),
        sa.Column("consultation_id", sa.String(length=36), nullable=True),
        sa.Column("alert_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=12), server_default="active", nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('active','completed','cancelled','failed')", name="ck_workflow_status"
        ),
        sa.CheckConstraint(
            "(CASE WHEN appointment_id IS NULL THEN 0 ELSE 1 END"
            " + CASE WHEN consultation_id IS NULL THEN 0 ELSE 1 END"
            " + CASE WHEN alert_id IS NULL THEN 0 ELSE 1 END) <= 1",
            name="ck_workflow_single_anchor",
        ),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"]),
        sa.ForeignKeyConstraint(["consultation_id"], ["consultations.id"]),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workflows_definition_key"), "workflows", ["definition_key"], unique=False)
    op.create_index(op.f("ix_workflows_patient_id"), "workflows", ["patient_id"], unique=False)
    op.create_index(op.f("ix_workflows_status"), "workflows", ["status"], unique=False)
    op.create_index(
        "ix_workflows_patient_definition_status",
        "workflows",
        ["patient_id", "definition_key", "status"],
        unique=False,
    )

    op.create_table(
        "workflow_steps",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workflow_id", sa.String(length=36), nullable=False),
        sa.Column("step_key", sa.String(length=60), nullable=False),
        sa.Column("step_type", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=12), server_default="pending", nullable=False),
        sa.Column("due_at", sa.DateTime(), nullable=False),
        sa.Column("run_after", sa.DateTime(), nullable=False),
        sa.Column("max_lateness_seconds", sa.Integer(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("claimed_by", sa.String(length=40), server_default="", nullable=False),
        sa.Column("last_error", sa.String(length=300), server_default="", nullable=False),
        sa.Column("failure_category", sa.String(length=20), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("executed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','running','succeeded','failed','skipped','superseded','cancelled')",
            name="ck_workflow_step_status",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_workflow_step_attempts_nonneg"),
        sa.CheckConstraint("max_attempts > 0", name="ck_workflow_step_max_attempts_positive"),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_id", "step_key", name="uq_workflow_step_key"),
    )
    op.create_index(op.f("ix_workflow_steps_workflow_id"), "workflow_steps", ["workflow_id"], unique=False)
    op.create_index(op.f("ix_workflow_steps_step_type"), "workflow_steps", ["step_type"], unique=False)
    op.create_index(op.f("ix_workflow_steps_status"), "workflow_steps", ["status"], unique=False)
    op.create_index(op.f("ix_workflow_steps_run_after"), "workflow_steps", ["run_after"], unique=False)
    op.create_index(
        "ix_workflow_steps_status_run_after", "workflow_steps", ["status", "run_after"], unique=False
    )
    op.create_index(
        "ix_workflow_steps_workflow_status", "workflow_steps", ["workflow_id", "status"], unique=False
    )

    op.add_column("notifications", sa.Column("dedupe_key", sa.String(length=120), nullable=True))
    op.create_unique_constraint("uq_notifications_dedupe_key", "notifications", ["dedupe_key"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("uq_notifications_dedupe_key", "notifications", type_="unique")
    op.drop_column("notifications", "dedupe_key")

    op.drop_index("ix_workflow_steps_workflow_status", table_name="workflow_steps")
    op.drop_index("ix_workflow_steps_status_run_after", table_name="workflow_steps")
    op.drop_index(op.f("ix_workflow_steps_run_after"), table_name="workflow_steps")
    op.drop_index(op.f("ix_workflow_steps_status"), table_name="workflow_steps")
    op.drop_index(op.f("ix_workflow_steps_step_type"), table_name="workflow_steps")
    op.drop_index(op.f("ix_workflow_steps_workflow_id"), table_name="workflow_steps")
    op.drop_table("workflow_steps")

    op.drop_index("ix_workflows_patient_definition_status", table_name="workflows")
    op.drop_index(op.f("ix_workflows_status"), table_name="workflows")
    op.drop_index(op.f("ix_workflows_patient_id"), table_name="workflows")
    op.drop_index(op.f("ix_workflows_definition_key"), table_name="workflows")
    op.drop_table("workflows")
