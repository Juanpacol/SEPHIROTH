"""patients.{conditions,medications,allergies,lab_results} json -> text (PHI encryption)

`core/crypto.py::EncryptedJSON` stores ciphertext (base64 text), which a
native Postgres `json` column can't hold — this only changes the column's
storage type; it does NOT encrypt existing rows. Existing values remain
plain-text JSON in a text column after this migration (still readable —
`EncryptedJSON.process_result_value` falls back to a plain `json.loads` on
an `InvalidToken`); only rows written *after* the app boots with
`phi_encryption_key` configured are actually encrypted. Run the standalone
backfill (`scripts/encrypt_existing_phi.py` — take a DB backup first) to
encrypt everything already there.

`clinical_notes.content` needs no migration: it was already `Text`.

Revision ID: 11a57df03c4f
Revises: 19507206caee
Create Date: 2026-09-04 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "11a57df03c4f"
down_revision: Union[str, Sequence[str], None] = "19507206caee"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = ["conditions", "medications", "allergies", "lab_results"]


def upgrade() -> None:
    """Upgrade schema."""
    for column in _COLUMNS:
        op.alter_column(
            "patients",
            column,
            type_=sa.Text(),
            postgresql_using=f"{column}::text",
        )


def downgrade() -> None:
    """Downgrade schema.

    Only safe if every row's value is still plain JSON text (i.e. nothing
    has been encrypted since upgrading) — a ciphertext value is not valid
    JSON and this cast will fail loudly rather than silently corrupt data.
    """
    for column in _COLUMNS:
        op.alter_column(
            "patients",
            column,
            type_=sa.JSON(),
            postgresql_using=f"{column}::json",
        )
