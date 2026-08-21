"""appointments.confirmed_at / confirmed_by_user_id (SPEC-012)

Revision ID: d4f6a1c3e5b9
Revises: c3e5f9a2b4d8
Create Date: 2026-08-21 03:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4f6a1c3e5b9"
down_revision: Union[str, Sequence[str], None] = "c3e5f9a2b4d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("appointments", sa.Column("confirmed_at", sa.DateTime(), nullable=True))
    op.add_column("appointments", sa.Column("confirmed_by_user_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_appointments_confirmed_by_user_id_users",
        "appointments",
        "users",
        ["confirmed_by_user_id"],
        ["id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_appointments_confirmed_by_user_id_users", "appointments", type_="foreignkey")
    op.drop_column("appointments", "confirmed_by_user_id")
    op.drop_column("appointments", "confirmed_at")
