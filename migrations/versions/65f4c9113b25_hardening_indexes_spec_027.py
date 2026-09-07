"""hardening indexes (SPEC-027)

Revision ID: 65f4c9113b25
Revises: 1d6bcd085233
Create Date: 2026-09-06

Two indexes, no data change.

Both cover a filter-plus-order the application already performs.
`consultations` had `user_id` indexed and `created_at` not, so listing a
clinician's history sorted every consultation they had ever run;
`timeline_events` had `patient_id` alone, so every timeline load sorted the
patient's whole history.

Deliberately not in this revision: anything on a table nobody has profiled.
An index costs every write, and a guess costs it forever (SPEC-027 NG-4).
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "65f4c9113b25"
down_revision: Union[str, Sequence[str], None] = "1d6bcd085233"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_consultations_user_created", "consultations", ["user_id", "created_at"], unique=False)
    op.create_index(
        "ix_timeline_events_patient_date", "timeline_events", ["patient_id", "date"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_timeline_events_patient_date", table_name="timeline_events")
    op.drop_index("ix_consultations_user_created", table_name="consultations")
