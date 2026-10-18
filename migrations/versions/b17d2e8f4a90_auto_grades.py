"""auto grades

AB#17: a second model's grade of a sampled consultation, or the recorded
reason it was skipped or failed. `justification` and `review_note` are
encrypted text (ciphertext in a TEXT column).

Revision ID: b17d2e8f4a90
Revises: a16c0d4e7b21
Create Date: 2026-10-18 19:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b17d2e8f4a90"
down_revision: Union[str, Sequence[str], None] = "a16c0d4e7b21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auto_grades",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("consultation_id", sa.String(length=36), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("reason", sa.String(length=30), nullable=True),
        sa.Column("criteria_version", sa.String(length=10), nullable=False),
        sa.Column("grader_provider", sa.String(length=20), nullable=False),
        sa.Column("grader_model", sa.String(length=80), nullable=False),
        sa.Column("scores", sa.JSON(), nullable=False),
        sa.Column("overall", sa.Float(), nullable=True),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("review_status", sa.String(length=10), nullable=True),
        sa.Column("review_outcome", sa.String(length=20), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=False),
        sa.Column("reviewed_by", sa.String(length=36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["consultation_id"], ["consultations.id"]),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("consultation_id", name="uq_auto_grade_consultation"),
    )
    op.create_index(op.f("ix_auto_grades_trace_id"), "auto_grades", ["trace_id"])
    op.create_index(op.f("ix_auto_grades_status"), "auto_grades", ["status"])
    op.create_index(op.f("ix_auto_grades_created_at"), "auto_grades", ["created_at"])
    op.create_index("ix_auto_grades_review", "auto_grades", ["review_status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_auto_grades_review", table_name="auto_grades")
    op.drop_index(op.f("ix_auto_grades_created_at"), table_name="auto_grades")
    op.drop_index(op.f("ix_auto_grades_status"), table_name="auto_grades")
    op.drop_index(op.f("ix_auto_grades_trace_id"), table_name="auto_grades")
    op.drop_table("auto_grades")
