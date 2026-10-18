"""review access log

AB#15: append-only audit of every read made with the review token. Its own
table because `phi_access_log` needs a user and a patient row, and a token
reader is neither.

Revision ID: 5bf4911a733a
Revises: 900b7eb6f507
Create Date: 2026-10-18 16:13:04.117443

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "5bf4911a733a"
down_revision: Union[str, Sequence[str], None] = "900b7eb6f507"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "review_access_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("token_fingerprint", sa.String(length=16), nullable=False),
        sa.Column("route", sa.String(length=200), nullable=False),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("filters", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_review_access_log_created_at"), "review_access_log", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_review_access_log_token_fingerprint"),
        "review_access_log",
        ["token_fingerprint"],
        unique=False,
    )
    op.create_index(op.f("ix_review_access_log_trace_id"), "review_access_log", ["trace_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_review_access_log_trace_id"), table_name="review_access_log")
    op.drop_index(op.f("ix_review_access_log_token_fingerprint"), table_name="review_access_log")
    op.drop_index(op.f("ix_review_access_log_created_at"), table_name="review_access_log")
    op.drop_table("review_access_log")
