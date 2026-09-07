"""push subscriptions and deliveries (SPEC-025)

Revision ID: 1d6bcd085233
Revises: f1abc8afd4f8
Create Date: 2026-09-06

Purely additive: two new tables, nothing existing altered.

A deployment that sets no VAPID keys is unaffected by this revision beyond the
two empty tables -- push is disabled, no subscription can be created, and the
tick's dispatch step finds nothing.

No `core.crypto` fixup this time: neither table holds patient content. The
subscription keys authorise sending *to* one browser and are useless without
the VAPID private key, which lives in the environment rather than the database.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1d6bcd085233"
down_revision: Union[str, Sequence[str], None] = "f1abc8afd4f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("endpoint", sa.String(length=500), nullable=False),
        sa.Column("p256dh", sa.String(length=200), nullable=False),
        sa.Column("auth", sa.String(length=100), nullable=False),
        sa.Column("user_agent", sa.String(length=200), server_default="", nullable=False),
        sa.Column("failure_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("disabled_at", sa.DateTime(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("endpoint", name="uq_push_subscription_endpoint"),
    )
    op.create_index(
        "ix_push_subscriptions_user_active", "push_subscriptions", ["user_id", "disabled_at"], unique=False
    )
    op.create_index(op.f("ix_push_subscriptions_user_id"), "push_subscriptions", ["user_id"], unique=False)
    op.create_table(
        "push_deliveries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("subscription_id", sa.String(length=36), nullable=False),
        sa.Column("notification_id", sa.String(length=36), nullable=False),
        sa.Column("url", sa.String(length=200), server_default="", nullable=False),
        sa.Column("status", sa.String(length=10), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("send_after", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_error", sa.String(length=200), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('pending','sent','failed','dropped')", name="ck_push_delivery_status"),
        sa.ForeignKeyConstraint(
            ["notification_id"],
            ["notifications.id"],
        ),
        sa.ForeignKeyConstraint(["subscription_id"], ["push_subscriptions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subscription_id", "notification_id", name="uq_push_delivery"),
    )
    op.create_index("ix_push_deliveries_due", "push_deliveries", ["status", "send_after"], unique=False)
    op.create_index(
        op.f("ix_push_deliveries_notification_id"), "push_deliveries", ["notification_id"], unique=False
    )
    op.create_index(op.f("ix_push_deliveries_status"), "push_deliveries", ["status"], unique=False)
    op.create_index(
        op.f("ix_push_deliveries_subscription_id"), "push_deliveries", ["subscription_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_push_deliveries_subscription_id"), table_name="push_deliveries")
    op.drop_index(op.f("ix_push_deliveries_status"), table_name="push_deliveries")
    op.drop_index(op.f("ix_push_deliveries_notification_id"), table_name="push_deliveries")
    op.drop_index("ix_push_deliveries_due", table_name="push_deliveries")
    op.drop_table("push_deliveries")
    op.drop_index(op.f("ix_push_subscriptions_user_id"), table_name="push_subscriptions")
    op.drop_index("ix_push_subscriptions_user_active", table_name="push_subscriptions")
    op.drop_table("push_subscriptions")
