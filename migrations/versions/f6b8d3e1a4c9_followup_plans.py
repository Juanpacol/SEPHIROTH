"""followup_plans + workflows.followup_plan_id (SPEC-014)

Revision ID: f6b8d3e1a4c9
Revises: e5a7c2d9f1b3
Create Date: 2026-08-21 05:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6b8d3e1a4c9"
down_revision: Union[str, Sequence[str], None] = "e5a7c2d9f1b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "followup_plans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("consultation_id", sa.String(length=36), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=12), server_default="active", nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("status IN ('active','completed','cancelled')", name="ck_followup_plan_status"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.ForeignKeyConstraint(["consultation_id"], ["consultations.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_followup_plans_patient_id"), "followup_plans", ["patient_id"], unique=False)
    op.create_index(op.f("ix_followup_plans_status"), "followup_plans", ["status"], unique=False)

    op.add_column("workflows", sa.Column("followup_plan_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_workflows_followup_plan_id_followup_plans",
        "workflows",
        "followup_plans",
        ["followup_plan_id"],
        ["id"],
    )
    op.drop_constraint("ck_workflow_single_anchor", "workflows", type_="check")
    op.create_check_constraint(
        "ck_workflow_single_anchor",
        "workflows",
        "(CASE WHEN appointment_id IS NULL THEN 0 ELSE 1 END"
        " + CASE WHEN consultation_id IS NULL THEN 0 ELSE 1 END"
        " + CASE WHEN alert_id IS NULL THEN 0 ELSE 1 END"
        " + CASE WHEN followup_plan_id IS NULL THEN 0 ELSE 1 END) <= 1",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_workflow_single_anchor", "workflows", type_="check")
    op.create_check_constraint(
        "ck_workflow_single_anchor",
        "workflows",
        "(CASE WHEN appointment_id IS NULL THEN 0 ELSE 1 END"
        " + CASE WHEN consultation_id IS NULL THEN 0 ELSE 1 END"
        " + CASE WHEN alert_id IS NULL THEN 0 ELSE 1 END) <= 1",
    )
    op.drop_constraint("fk_workflows_followup_plan_id_followup_plans", "workflows", type_="foreignkey")
    op.drop_column("workflows", "followup_plan_id")

    op.drop_index(op.f("ix_followup_plans_status"), table_name="followup_plans")
    op.drop_index(op.f("ix_followup_plans_patient_id"), table_name="followup_plans")
    op.drop_table("followup_plans")
