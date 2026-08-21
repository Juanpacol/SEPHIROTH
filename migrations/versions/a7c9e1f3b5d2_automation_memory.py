"""automation_memory -- namespaced operational preferences (SPEC-015)

Revision ID: a7c9e1f3b5d2
Revises: f6b8d3e1a4c9
Create Date: 2026-08-21 06:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c9e1f3b5d2"
down_revision: Union[str, Sequence[str], None] = "f6b8d3e1a4c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "automation_memory",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scope", sa.String(length=10), nullable=False),
        sa.Column("scope_id", sa.String(length=36), nullable=False),
        sa.Column("key", sa.String(length=60), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("scope IN ('clinic','user','patient')", name="ck_automation_memory_scope"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope", "scope_id", "key", name="uq_automation_memory_scope_key"),
    )
    op.create_index(op.f("ix_automation_memory_scope"), "automation_memory", ["scope"], unique=False)
    op.create_index(op.f("ix_automation_memory_scope_id"), "automation_memory", ["scope_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_automation_memory_scope_id"), table_name="automation_memory")
    op.drop_index(op.f("ix_automation_memory_scope"), table_name="automation_memory")
    op.drop_table("automation_memory")
