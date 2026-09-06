"""Column-level encryption for PHI fields (`data/schemas/__init__.py`'s
`ClinicalNote.content` and `Patient.{conditions,medications,allergies,lab_results}`).

Symmetric (Fernet: AES-128-CBC + HMAC, authenticated) rather than relying
solely on disk-level encryption — a backup, a misconfigured replica, or a
compromised storage layer would otherwise expose clinical text/data as plain
rows. Application-transparent: `EncryptedText`/`EncryptedJSON` are SQLAlchemy
`TypeDecorator`s, so every existing `select()`/`.content`/`.lab_results`
access keeps working unchanged — encryption happens on the way to the driver,
decryption on the way back, never something a router/service has to do
itself. Nothing here is ever queried by value in SQL (`grep`'d before this
was added — see ADR-014), so opaque ciphertext at rest costs nothing at the
query layer.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Optional

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from core.config import settings


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    return Fernet(settings.phi_encryption_key.encode())


def encrypt_str(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_str(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


# Every Fernet token starts with this exact 6-char base64 prefix — byte 0 is
# a fixed 0x80 version marker, and this is fixed enough in practice to tell
# "ciphertext under some key" apart from "legacy plaintext that predates
# encryption". The distinction matters: a value that LOOKS like a token but
# fails to decrypt means a KEY MISMATCH (wrong/rotated `phi_encryption_key`)
# — silently treating that as plaintext would re-encrypt garbage on the next
# write, permanently destroying the real data (this happened once locally
# while building this feature; see ADR-014). A value that does NOT look like
# a token is legitimately unmigrated legacy data, safe to hand back as-is.
_FERNET_TOKEN_PREFIX = "gAAAAA"


class _KeyMismatch(RuntimeError):
    """Raised instead of silently returning ciphertext when a value looks
    like a Fernet token but doesn't decrypt under the configured key."""


class EncryptedText(TypeDecorator):
    """Stores a plain string as Fernet ciphertext (base64 text, so any
    `TEXT` column can hold it — no schema-level size assumption changes)."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Optional[str], dialect) -> Optional[str]:
        if value is None:
            return None
        return encrypt_str(value)

    def process_result_value(self, value: Optional[str], dialect) -> Optional[str]:
        if value is None:
            return None
        try:
            return decrypt_str(value)
        except InvalidToken:
            if value.startswith(_FERNET_TOKEN_PREFIX):
                raise _KeyMismatch(
                    "A value looks Fernet-encrypted but did not decrypt under the "
                    "configured phi_encryption_key — this is a wrong/rotated key, "
                    "not unmigrated legacy data. Refusing to guess; fix the key "
                    "before reading (and never write) this row."
                ) from None
            # A row written before encryption was enabled — genuinely plain
            # text, safe to hand back as-is. The one-time backfill script
            # (scripts/encrypt_existing_phi.py) is what closes this gap.
            return value


class EncryptedJSON(TypeDecorator):
    """`EncryptedText` for a JSON-shaped column (`Patient.conditions` et
    al.): serialize to a JSON string, encrypt that, and reverse on read —
    `Base.metadata`'s column stays `Text` at the DB level, never a database
    JSON type, since a database JSON column can't hold opaque ciphertext."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect) -> Optional[str]:
        if value is None:
            return None
        return encrypt_str(json.dumps(value))

    def process_result_value(self, value: Optional[str], dialect) -> Any:
        if value is None:
            return None
        try:
            return json.loads(decrypt_str(value))
        except InvalidToken:
            if value.startswith(_FERNET_TOKEN_PREFIX):
                raise _KeyMismatch(
                    "A value looks Fernet-encrypted but did not decrypt under the "
                    "configured phi_encryption_key — this is a wrong/rotated key, "
                    "not unmigrated legacy data. Refusing to guess; fix the key "
                    "before reading (and never write) this row."
                ) from None
            # Same unmigrated-row fallback as EncryptedText. A legacy JSON
            # column's raw value is already the right Python shape via the
            # driver's own JSON decoding, so just hand it back as-is.
            try:
                return json.loads(value) if isinstance(value, str) else value
            except (TypeError, ValueError):
                return value
