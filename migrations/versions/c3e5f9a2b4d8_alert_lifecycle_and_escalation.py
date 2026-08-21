"""alert assignment/due_at/escalated_at columns (SPEC-011)

Revision ID: c3e5f9a2b4d8
Revises: b2d4e8f1a3c7
Create Date: 2026-08-21 02:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3e5f9a2b4d8"
down_revision: Union[str, Sequence[str], None] = "b2d4e8f1a3c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("alerts", sa.Column("assigned_to_user_id", sa.String(length=36), nullable=True))
    op.add_column("alerts", sa.Column("due_at", sa.DateTime(), nullable=True))
    op.add_column("alerts", sa.Column("escalated_at", sa.DateTime(), nullable=True))
    op.create_index(
        op.f("ix_alerts_assigned_to_user_id"), "alerts", ["assigned_to_user_id"], unique=False
    )
    op.create_foreign_key(
        "fk_alerts_assigned_to_user_id_users", "alerts", "users", ["assigned_to_user_id"], ["id"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_alerts_assigned_to_user_id_users", "alerts", type_="foreignkey")
    op.drop_index(op.f("ix_alerts_assigned_to_user_id"), table_name="alerts")
    op.drop_column("alerts", "escalated_at")
    op.drop_column("alerts", "due_at")
    op.drop_column("alerts", "assigned_to_user_id")
