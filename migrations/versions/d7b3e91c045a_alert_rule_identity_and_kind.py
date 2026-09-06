"""alerts.rule_key + alerts.kind (SPEC-021)

Revision ID: d7b3e91c045a
Revises: c4f1a86d2e70
Create Date: 2026-09-06

Purely additive. Both columns are new; nothing is altered and nothing is
backfilled.

`rule_key` is deliberately left NULL on existing rows. It is a machine
identity, and the only thing available to fill it with would be the display
title those rows already carry -- inventing identities that were never real,
and inventing them wrong the moment a label is reworded. `alerts.py` handles
the mixed population directly: a row with a `rule_key` dedupes on it, a row
without one keeps the old `(category, title)` comparison until it is resolved.

`kind` defaults to `clinical` for the same population, which is what every
existing alert is: the only administrative producer (the unconfirmed-appointment
check) is introduced by this same phase.

Written by hand -- the local Postgres was unavailable -- so the statements were
derived from the model diff. `tests/test_alembic_migration.py` is the drift
guard and self-skips without a database.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7b3e91c045a"
down_revision: Union[str, Sequence[str], None] = "c4f1a86d2e70"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("alerts", sa.Column("rule_key", sa.String(length=120), nullable=True))
    op.add_column(
        "alerts",
        sa.Column("kind", sa.String(length=20), server_default="clinical", nullable=False),
    )
    op.create_index(op.f("ix_alerts_rule_key"), "alerts", ["rule_key"])
    op.create_index(op.f("ix_alerts_kind"), "alerts", ["kind"])
    op.create_index("ix_alerts_patient_rule", "alerts", ["patient_id", "rule_key", "status"])
    op.create_check_constraint("ck_alert_kind", "alerts", "kind IN ('clinical','administrative')")


def downgrade() -> None:
    op.drop_constraint("ck_alert_kind", "alerts", type_="check")
    op.drop_index("ix_alerts_patient_rule", table_name="alerts")
    op.drop_index(op.f("ix_alerts_kind"), table_name="alerts")
    op.drop_index(op.f("ix_alerts_rule_key"), table_name="alerts")
    op.drop_column("alerts", "kind")
    op.drop_column("alerts", "rule_key")
