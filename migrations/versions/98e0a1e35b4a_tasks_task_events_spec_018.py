"""tasks + task_events (SPEC-018)

Revision ID: 98e0a1e35b4a
Revises: 11a57df03c4f
Create Date: 2026-09-06

Purely additive: two new tables, nothing altered, nothing backfilled. The
backfill of existing open alerts and pending approvals is
`scripts/backfill_tasks.py`, deliberately not part of this migration -- it
needs the SLA table and the adapter registry, which are application code a
migration must not import, and it is safely re-runnable because every insert
goes through `create_task`'s dedupe.

`Task.detail`/`Task.context`/`TaskEvent.note` are `EncryptedText`/
`EncryptedJSON` in the ORM (ADR-014), which are `TypeDecorator`s over `Text` --
the stored column is TEXT ciphertext either way, so this migration says
`sa.Text()` and does not import application code. Autogenerate emitted
`core.crypto.EncryptedText()` with no import for it, the same fixup
`docs/04-development/setup.md` warns about.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "98e0a1e35b4a"
down_revision: Union[str, Sequence[str], None] = "11a57df03c4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("dedupe_key", sa.String(length=160), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=True),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("context", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=12), server_default="open", nullable=False),
        sa.Column("assigned_to_user_id", sa.String(length=36), nullable=True),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("snoozed_until", sa.DateTime(), nullable=True),
        sa.Column("escalated_at", sa.DateTime(), nullable=True),
        sa.Column("escalation_level", sa.Integer(), server_default="0", nullable=False),
        sa.Column("dismiss_reason", sa.String(length=300), nullable=False),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("closed_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("severity IN ('critical','high','medium','low')", name="ck_task_severity"),
        sa.CheckConstraint(
            "source_type IN ('alert','approval','followup','result','appointment',"
            "'automation','consultation','deteriorating','interaction')",
            name="ck_task_source_type",
        ),
        sa.CheckConstraint(
            "status IN ('open','in_progress','snoozed','done','dismissed','superseded')",
            name="ck_task_status",
        ),
        sa.CheckConstraint(
            "status NOT IN ('done','dismissed') OR closed_by IS NOT NULL",
            name="ck_task_closed_requires_actor",
        ),
        sa.ForeignKeyConstraint(["assigned_to_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["closed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key", name="uq_task_dedupe_key"),
    )
    op.create_index("ix_tasks_assigned_status", "tasks", ["assigned_to_user_id", "status"])
    op.create_index(op.f("ix_tasks_assigned_to_user_id"), "tasks", ["assigned_to_user_id"])
    op.create_index(op.f("ix_tasks_category"), "tasks", ["category"])
    op.create_index(op.f("ix_tasks_created_at"), "tasks", ["created_at"])
    op.create_index(op.f("ix_tasks_patient_id"), "tasks", ["patient_id"])
    op.create_index(op.f("ix_tasks_severity"), "tasks", ["severity"])
    op.create_index("ix_tasks_source", "tasks", ["source_type", "source_id"])
    op.create_index(op.f("ix_tasks_source_type"), "tasks", ["source_type"])
    op.create_index(op.f("ix_tasks_status"), "tasks", ["status"])
    op.create_index("ix_tasks_status_due", "tasks", ["status", "due_at"])

    op.create_table(
        "task_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=20), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("from_status", sa.String(length=12), nullable=True),
        sa.Column("to_status", sa.String(length=12), nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('created','claimed','assigned','snoozed','resumed','escalated',"
            "'completed','dismissed','superseded','reopened','commented')",
            name="ck_task_event_type",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_task_events_created_at"), "task_events", ["created_at"])
    op.create_index("ix_task_events_task_created", "task_events", ["task_id", "created_at"])
    op.create_index(op.f("ix_task_events_task_id"), "task_events", ["task_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_task_events_task_id"), table_name="task_events")
    op.drop_index("ix_task_events_task_created", table_name="task_events")
    op.drop_index(op.f("ix_task_events_created_at"), table_name="task_events")
    op.drop_table("task_events")
    op.drop_index("ix_tasks_status_due", table_name="tasks")
    op.drop_index(op.f("ix_tasks_status"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_source_type"), table_name="tasks")
    op.drop_index("ix_tasks_source", table_name="tasks")
    op.drop_index(op.f("ix_tasks_severity"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_patient_id"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_created_at"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_category"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_assigned_to_user_id"), table_name="tasks")
    op.drop_index("ix_tasks_assigned_status", table_name="tasks")
    op.drop_table("tasks")
