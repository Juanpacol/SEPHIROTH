# ADR-014 — Column-level PHI encryption

**Status:** Accepted · **Date:** 2026-09-04

## Context

A security audit flagged clinical data (`ClinicalNote.content`, `Patient`'s
conditions/medications/allergies/lab_results) stored as plain rows, relying
entirely on disk-level encryption (unverified, and outside this app's
control on Supabase).

## Decision

Application-level, transparent column encryption: `core/crypto.py`'s
`EncryptedText`/`EncryptedJSON` are SQLAlchemy `TypeDecorator`s (Fernet —
AES-128-CBC + HMAC, authenticated) wrapping `ClinicalNote.content` and
`Patient.{conditions,medications,allergies,lab_results}`. Every existing
`select()`/attribute access keeps working unchanged; encryption happens on
the way to the driver, decryption on the way back. Confirmed before
encrypting: nothing in this codebase filters on these columns by value in
SQL (`grep`'d for `where(Patient.` across the app) — they're always fetched
by id/status and processed in Python, so opaque ciphertext at rest costs
nothing at the query layer.

`phi_encryption_key` (`platform/core/config.py`) follows the same
fail-fast posture as `jwt_secret`: a committed, working default for
dev/test, rejected outside `development`/`test`. `migrations/versions/*_phi_columns_to_text_for_encryption.py`
converts the `Patient` columns from native Postgres `json` to `text` (a
schema-only change — it does NOT encrypt existing rows); `scripts/encrypt_existing_phi.py`
is the one-time backfill that actually re-encrypts what's already there
(take a backup first).

## A bug found while building this, and what it changed

Re-running the backfill script with a *different* key than the data was
already encrypted under silently treated the still-valid ciphertext as
"legacy unmigrated plaintext" (the original fallback caught every
`InvalidToken`, not just genuine legacy rows), re-encrypted that ciphertext
as if it were the real value, and permanently destroyed the underlying data
— it happened once against local seed data while building this feature.
Fixed by having `EncryptedText`/`EncryptedJSON` check whether the
undecryptable value looks like a Fernet token (`gAAAAA` prefix) before
assuming it's legacy plaintext: a token-shaped value that fails to decrypt
now raises `_KeyMismatch` loudly instead of being silently swallowed.
`tests/test_crypto.py` locks this in — see its module docstring.

## Consequences

- Rotating `phi_encryption_key` makes every already-encrypted row
  unreadable until re-encrypted under the new key — there is no
  key-rotation tool yet; changing it requires a planned re-encrypt pass
  (decrypt-under-old, re-run the backfill under the new key).
- A row written before a real key was configured stays plaintext at rest
  until `scripts/encrypt_existing_phi.py` runs — reads still work
  (`EncryptedText`/`EncryptedJSON`'s legacy-plaintext fallback), so rollout
  doesn't require a maintenance window, only the backfill to actually close
  the gap.
