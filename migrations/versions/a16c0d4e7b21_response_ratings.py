"""response ratings

AB#16: a clinician's useful / not-useful verdict on a consultation's answer,
with the review-queue state for the "not useful" ones. `comment` and
`review_note` are encrypted text (ciphertext in a TEXT column), like the other
PHI columns.

Revision ID: a16c0d4e7b21
Revises: 5bf4911a733a
Create Date: 2026-10-18 17:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a16c0d4e7b21"
down_revision: Union[str, Sequence[str], None] = "5bf4911a733a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "response_ratings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("consultation_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("value", sa.String(length=4), nullable=False),
        sa.Column("reason", sa.String(length=20), nullable=True),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("review_status", sa.String(length=10), nullable=True),
        sa.Column("review_outcome", sa.String(length=20), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=False),
        sa.Column("reviewed_by", sa.String(length=36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["consultation_id"], ["consultations.id"]),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("consultation_id", "user_id", name="uq_response_rating_consultation_user"),
    )
    op.create_index(op.f("ix_response_ratings_consultation_id"), "response_ratings", ["consultation_id"])
    op.create_index(op.f("ix_response_ratings_user_id"), "response_ratings", ["user_id"])
    op.create_index(op.f("ix_response_ratings_trace_id"), "response_ratings", ["trace_id"])
    op.create_index("ix_response_ratings_review", "response_ratings", ["review_status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_response_ratings_review", table_name="response_ratings")
    op.drop_index(op.f("ix_response_ratings_trace_id"), table_name="response_ratings")
    op.drop_index(op.f("ix_response_ratings_user_id"), table_name="response_ratings")
    op.drop_index(op.f("ix_response_ratings_consultation_id"), table_name="response_ratings")
    op.drop_table("response_ratings")
