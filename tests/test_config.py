"""JWT secret fail-fast: staging/production reject known-insecure secrets."""

import secrets

import pytest
from pydantic import ValidationError

from core.config import DEFAULT_JWT_SECRET, Settings


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
    s = Settings(_env_file=None, environment="production", jwt_secret=secrets.token_hex(32))
    assert len(s.jwt_secret) >= 32
