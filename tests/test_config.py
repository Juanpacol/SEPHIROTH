"""JWT secret / PHI encryption key fail-fast: staging/production reject
known-insecure or malformed values."""

import secrets

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from core.config import DEFAULT_JWT_SECRET, DEFAULT_PHI_ENCRYPTION_KEY, Settings

_STRONG_PHI_KEY = Fernet.generate_key().decode()


def test_development_allows_default_secret():
    s = Settings(_env_file=None, environment="development")
    assert s.jwt_secret == DEFAULT_JWT_SECRET


def test_test_env_allows_default_secret():
    s = Settings(_env_file=None, environment="test")
    assert s.jwt_secret == DEFAULT_JWT_SECRET


def test_production_rejects_default_secret():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="production", jwt_secret=DEFAULT_JWT_SECRET)


def test_staging_rejects_default_secret():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="staging", jwt_secret=DEFAULT_JWT_SECRET)


def test_production_rejects_short_secret():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="production", jwt_secret="a" * 31)


def test_production_rejects_known_insecure_value():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="production", jwt_secret="change-me-in-production")


def test_production_accepts_strong_secret():
    s = Settings(
        _env_file=None,
        environment="production",
        jwt_secret=secrets.token_hex(32),
        phi_encryption_key=_STRONG_PHI_KEY,
    )
    assert len(s.jwt_secret) >= 32


def test_development_allows_default_phi_key():
    s = Settings(_env_file=None, environment="development")
    assert s.phi_encryption_key == DEFAULT_PHI_ENCRYPTION_KEY


def test_production_rejects_default_phi_key():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="production",
            jwt_secret=secrets.token_hex(32),
            phi_encryption_key=DEFAULT_PHI_ENCRYPTION_KEY,
        )


def test_production_rejects_malformed_phi_key():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="production",
            jwt_secret=secrets.token_hex(32),
            phi_encryption_key="not-a-real-fernet-key",
        )


def test_production_accepts_valid_phi_key():
    s = Settings(
        _env_file=None,
        environment="production",
        jwt_secret=secrets.token_hex(32),
        phi_encryption_key=_STRONG_PHI_KEY,
    )
    assert s.phi_encryption_key == _STRONG_PHI_KEY
