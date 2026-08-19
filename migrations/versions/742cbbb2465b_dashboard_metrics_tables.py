"""dashboard metrics tables (alerts, lab_results, medication_orders, imaging_studies, ai_evaluations)

Revision ID: 742cbbb2465b
Revises: 91538cb9b156
Create Date: 2026-08-19 15:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "742cbbb2465b"
down_revision: Union[str, Sequence[str], None] = "91538cb9b156"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "alerts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=10), server_default="active", nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=60), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("reviewed_by", sa.String(length=36), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "category IN ('medication','lab','imaging','ai','clinical')", name="ck_alert_category"
        ),
        sa.CheckConstraint("severity IN ('critical','high','medium','low')", name="ck_alert_severity"),
        sa.CheckConstraint("status IN ('active','reviewed','resolved')", name="ck_alert_status"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_alerts_patient_id"), "alerts", ["patient_id"], unique=False)
    op.create_index(op.f("ix_alerts_status"), "alerts", ["status"], unique=False)
    op.create_index(op.f("ix_alerts_created_at"), "alerts", ["created_at"], unique=False)
    op.create_index("ix_alerts_status_severity", "alerts", ["status", "severity"], unique=False)

    op.create_table(
        "lab_results",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("test_name", sa.String(length=60), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=20), server_default="", nullable=False),
        sa.Column("reference_low", sa.Float(), nullable=True),
        sa.Column("reference_high", sa.Float(), nullable=True),
        sa.Column("is_abnormal", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_critical", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("taken_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_lab_results_patient_id"), "lab_results", ["patient_id"], unique=False)
    op.create_index(op.f("ix_lab_results_taken_at"), "lab_results", ["taken_at"], unique=False)
    op.create_index(
        "ix_lab_results_patient_test_taken", "lab_results", ["patient_id", "test_name", "taken_at"], unique=False
    )

    op.create_table(
        "medication_orders",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("dose", sa.String(length=60), server_default="", nullable=False),
        sa.Column("route", sa.String(length=30), server_default="", nullable=False),
        sa.Column("frequency", sa.String(length=60), server_default="", nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("is_high_risk", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("status", sa.String(length=15), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('active','discontinued')", name="ck_medication_order_status"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_medication_orders_patient_id"), "medication_orders", ["patient_id"], unique=False)
    op.create_index(op.f("ix_medication_orders_status"), "medication_orders", ["status"], unique=False)

    op.create_table(
        "imaging_studies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("modality", sa.String(length=20), nullable=False),
        sa.Column("body_part", sa.String(length=60), nullable=False),
        sa.Column("study_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=10), server_default="pending", nullable=False),
        sa.Column("finding_summary", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(length=10), server_default="none", nullable=False),
        sa.Column("is_new_finding", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("analyzed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('pending','analyzed')", name="ck_imaging_study_status"),
        sa.CheckConstraint("severity IN ('critical','review','none')", name="ck_imaging_study_severity"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_imaging_studies_patient_id"), "imaging_studies", ["patient_id"], unique=False)
    op.create_index(op.f("ix_imaging_studies_status"), "imaging_studies", ["status"], unique=False)

    op.create_table(
        "ai_evaluations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=True),
        sa.Column("consultation_id", sa.String(length=36), nullable=True),
        sa.Column("eval_type", sa.String(length=40), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("requires_human_review", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("reviewed_by_clinician", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("clinician_modified", sa.Boolean(), nullable=True),
        sa.Column("clinician_rejected", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.ForeignKeyConstraint(["consultation_id"], ["consultations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ai_evaluations_patient_id"), "ai_evaluations", ["patient_id"], unique=False)
    op.create_index(
        op.f("ix_ai_evaluations_consultation_id"), "ai_evaluations", ["consultation_id"], unique=False
    )
    op.create_index(op.f("ix_ai_evaluations_created_at"), "ai_evaluations", ["created_at"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("ai_evaluations")
    op.drop_table("imaging_studies")
    op.drop_table("medication_orders")
    op.drop_table("lab_results")
    op.drop_table("alerts")
