#!/usr/bin/env python3
"""One-time backfill: encrypt PHI rows written before `phi_encryption_key`
was configured (`core/crypto.py`, ADR-014).

`EncryptedJSON`/`EncryptedText` encrypt every new write automatically, but a
row written before that had a real key falls back to plain JSON/text on
read (`InvalidToken` in `process_result_value`) — this script re-saves every
such row through the ORM once, so the ciphertext path takes over for
everything, not just new data.

Usage:
    PYTHONPATH=.:platform .venv/bin/python scripts/encrypt_existing_phi.py [--dry-run]

**Take a database backup before running this against a database with real
data** (a mistake here is a write, not a read — see the module docstring on
`migrations/versions/*_phi_columns_to_text_for_encryption.py`). Safe to
re-run: an already-encrypted row round-trips through the ORM unchanged.
"""

import argparse
import asyncio
import sys

sys.path.insert(0, ".")
sys.path.insert(0, "platform")

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from core.config import DEFAULT_PHI_ENCRYPTION_KEY, settings
from core.db import SessionLocal
from data.schemas import ClinicalNote, Patient


async def main(dry_run: bool) -> None:
    # The dev-default key is fine for local/test data (same posture as
    # DEFAULT_JWT_SECRET) — `Settings._check_phi_encryption_key` already
    # refuses to boot with it outside development/test, so this only needs
    # to guard against running unset/malformed in a real environment.
    if settings.environment not in ("development", "test") and (
        settings.phi_encryption_key == DEFAULT_PHI_ENCRYPTION_KEY
    ):
        print(
            "Refusing to run: phi_encryption_key is still the built-in dev default "
            f"in environment={settings.environment!r}. Set a real key first.",
            file=sys.stderr,
        )
        sys.exit(1)

    async with SessionLocal() as session:
        patients = (await session.scalars(select(Patient))).all()
        notes = (await session.scalars(select(ClinicalNote))).all()

        print(f"{len(patients)} patients, {len(notes)} clinical notes to re-save.")
        if dry_run:
            print("--dry-run: no writes made.")
            return

        # Force a dirty flag on every column regardless of SQLAlchemy's
        # equality-based change tracking (a plain `obj.attr = obj.attr`
        # re-assignment can be a no-op UPDATE-wise) — the SELECT above
        # already ran these through EncryptedJSON/EncryptedText on the way
        # in (plaintext or ciphertext, transparently), so an UPDATE runs
        # process_bind_param again — real encryption, every time.
        for patient in patients:
            for field in ("conditions", "medications", "allergies", "lab_results"):
                flag_modified(patient, field)
        for note in notes:
            flag_modified(note, "content")

        await session.commit()
        print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report row counts, write nothing.")
    args = parser.parse_args()
    asyncio.run(main(args.dry_run))
