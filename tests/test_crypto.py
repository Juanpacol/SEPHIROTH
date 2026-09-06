"""core/crypto.py — EncryptedText/EncryptedJSON round-trip and the
key-mismatch guard (a real bug hit once while building this: silently
falling back to "legacy plaintext" on ANY decrypt failure re-encrypted
already-ciphertext data as garbage on the next write — see ADR-014)."""

from cryptography.fernet import Fernet

from core.crypto import EncryptedJSON, EncryptedText, _KeyMismatch, encrypt_str


def test_encrypted_text_round_trip(monkeypatch):
    import core.crypto as crypto_module

    monkeypatch.setattr(crypto_module.settings, "phi_encryption_key", Fernet.generate_key().decode())
    crypto_module._fernet.cache_clear()

    col = EncryptedText()
    bound = col.process_bind_param("clinical note text", None)
    assert bound != "clinical note text"
    assert col.process_result_value(bound, None) == "clinical note text"


def test_encrypted_json_round_trip(monkeypatch):
    import core.crypto as crypto_module

    monkeypatch.setattr(crypto_module.settings, "phi_encryption_key", Fernet.generate_key().decode())
    crypto_module._fernet.cache_clear()

    col = EncryptedJSON()
    bound = col.process_bind_param(["Type 2 Diabetes", "Hypertension"], None)
    assert col.process_result_value(bound, None) == ["Type 2 Diabetes", "Hypertension"]


def test_encrypted_text_treats_non_token_as_legacy_plaintext(monkeypatch):
    import core.crypto as crypto_module

    monkeypatch.setattr(crypto_module.settings, "phi_encryption_key", Fernet.generate_key().decode())
    crypto_module._fernet.cache_clear()

    col = EncryptedText()
    plaintext = "a pre-encryption plaintext note"
    assert col.process_result_value(plaintext, None) == plaintext


def test_encrypted_json_treats_legacy_json_text_as_plaintext(monkeypatch):
    import core.crypto as crypto_module

    monkeypatch.setattr(crypto_module.settings, "phi_encryption_key", Fernet.generate_key().decode())
    crypto_module._fernet.cache_clear()

    col = EncryptedJSON()
    assert col.process_result_value('["Type 2 Diabetes"]', None) == ["Type 2 Diabetes"]


def test_encrypted_text_raises_on_key_mismatch_instead_of_returning_ciphertext(monkeypatch):
    """The bug this guards: a value that IS a Fernet token but was
    encrypted under a DIFFERENT key must never be silently handed back as
    if it were legacy plaintext — that ciphertext-as-plaintext would get
    re-encrypted on the next write, permanently destroying the real data."""
    import core.crypto as crypto_module

    monkeypatch.setattr(crypto_module.settings, "phi_encryption_key", Fernet.generate_key().decode())
    crypto_module._fernet.cache_clear()
    token_under_key_a = encrypt_str("real patient data")

    monkeypatch.setattr(crypto_module.settings, "phi_encryption_key", Fernet.generate_key().decode())
    crypto_module._fernet.cache_clear()

    col = EncryptedText()
    try:
        col.process_result_value(token_under_key_a, None)
        assert False, "expected _KeyMismatch"
    except _KeyMismatch:
        pass


def test_encrypted_json_raises_on_key_mismatch_instead_of_returning_ciphertext(monkeypatch):
    import core.crypto as crypto_module

    monkeypatch.setattr(crypto_module.settings, "phi_encryption_key", Fernet.generate_key().decode())
    crypto_module._fernet.cache_clear()
    token_under_key_a = encrypt_str('["real", "patient", "data"]')

    monkeypatch.setattr(crypto_module.settings, "phi_encryption_key", Fernet.generate_key().decode())
    crypto_module._fernet.cache_clear()

    col = EncryptedJSON()
    try:
        col.process_result_value(token_under_key_a, None)
        assert False, "expected _KeyMismatch"
    except _KeyMismatch:
        pass
