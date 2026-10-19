"""Development and test never reach a remote database by accident (AB#18)."""

import importlib.util
from pathlib import Path

import pytest
import yaml

from core.config import (
    Settings,
    assert_local_database,
    database_host,
    is_local_database_host,
    remote_database_hosts,
)

REPO = Path(__file__).resolve().parents[1]
SUPABASE = "postgresql+asyncpg://postgres.abcdefgh:SuperSecretPw1@aws-0-ca-central-1.pooler.supabase.com:5432/postgres"
LOCAL = "postgresql+asyncpg://clinical_ai:clinical_ai_password@localhost:5433/clinical_ai_db"


@pytest.mark.parametrize(
    "host",
    [
        None,
        "localhost",
        "LOCALHOST",
        "127.0.0.1",
        "::1",
        "postgres",
        "smoke-pg",
        "host.docker.internal",
        "db.local",
        "pg.internal",
        "10.0.0.5",
        "172.20.0.4",
        "192.168.1.9",
        "api.localhost",
    ],
)
def test_these_hosts_are_this_machine_or_its_container_network(host):
    assert is_local_database_host(host)


@pytest.mark.parametrize(
    "host",
    [
        "aws-0-ca-central-1.pooler.supabase.com",
        "db.abcdefgh.supabase.co",
        "pg.example.com",
        "8.8.8.8",
        "1.1.1.1",
    ],
)
def test_these_hosts_are_remote(host):
    assert not is_local_database_host(host)


def test_the_host_is_read_from_the_url_and_sqlite_has_none():
    assert database_host(SUPABASE) == "aws-0-ca-central-1.pooler.supabase.com"
    assert database_host(LOCAL) == "localhost"
    assert database_host("sqlite+aiosqlite://") is None
    assert remote_database_hosts("sqlite+aiosqlite://", None, LOCAL) == []
    assert remote_database_hosts(LOCAL, SUPABASE, SUPABASE) == ["aws-0-ca-central-1.pooler.supabase.com"]


# --- the startup guard ------------------------------------------------------


@pytest.mark.parametrize("environment", ["development", "test"])
def test_dev_and_test_refuse_a_remote_database(environment):
    with pytest.raises(ValueError, match="remote host") as err:
        Settings(environment=environment, database_url=SUPABASE)

    message = str(err.value)
    assert "supabase.com" in message
    assert "SuperSecretPw1" not in message, "the password must never reach the error"
    assert "ALLOW_REMOTE_DB" in message and "inspect_db.py" in message


def test_the_error_does_not_echo_the_url_either():
    with pytest.raises(ValueError) as err:
        Settings(environment="development", database_url=SUPABASE)

    assert "SuperSecretPw1" not in repr(err.value) and "SuperSecretPw1" not in str(err.value.__cause__ or "")


def test_a_remote_migration_url_is_refused_too():
    with pytest.raises(ValueError, match="remote host"):
        Settings(environment="development", database_url=LOCAL, migration_database_url=SUPABASE)


def test_the_remote_override_exists_but_has_to_be_asked_for():
    assert Settings().allow_remote_db is False

    s = Settings(environment="development", database_url=SUPABASE, allow_remote_db=True)

    assert s.database_url == SUPABASE


def test_staging_and_production_are_never_blocked():
    jwt, key = "j" * 40, "k" * 44
    for environment in ("staging", "production"):
        s = Settings(
            environment=environment, database_url=SUPABASE, jwt_secret=jwt, phi_encryption_key=_phi(key)
        )
        assert s.database_url == SUPABASE


def _phi(_):
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode()


def test_local_urls_are_unaffected():
    assert Settings(environment="development", database_url=LOCAL).database_url == LOCAL
    assert (
        Settings(environment="test", database_url="sqlite+aiosqlite://").database_url == "sqlite+aiosqlite://"
    )
    compose = "postgresql+asyncpg://clinical_ai:pw@postgres:5432/clinical_ai_db"
    assert Settings(environment="development", database_url=compose).database_url == compose


# --- the test suite's own guard --------------------------------------------


def test_the_suite_guard_refuses_a_remote_database_whatever_the_override_says():
    assert_local_database(LOCAL, None)
    with pytest.raises(RuntimeError, match="refusing"):
        assert_local_database(LOCAL, SUPABASE)
    # `allow_remote_db` is a Settings field; this function does not read it.
    with pytest.raises(RuntimeError):
        assert_local_database(SUPABASE)


def test_the_running_suite_is_on_a_local_database():
    from core.config import settings

    assert_local_database(settings.database_url, settings.migration_database_url)


# --- files that decide where things point ----------------------------------


def test_docker_compose_does_not_inherit_the_env_files_database_url():
    compose = yaml.safe_load((REPO / "docker-compose.yml").read_text())
    value = compose["services"]["api"]["environment"]["DATABASE_URL"]

    assert "${DATABASE_URL" not in value, "that variable is what a developer's .env holds"
    assert value.startswith("${API_DATABASE_URL:-") and "@postgres:5432/" in value
    assert compose["services"]["api"]["environment"]["ALLOW_REMOTE_DB"].startswith("${API_ALLOW_REMOTE_DB")


def test_no_versioned_file_names_a_production_database_host():
    for name in (".env.example", "docker-compose.yml", "docker-compose.override.yml", "render.yaml"):
        text = (REPO / name).read_text()
        assert "supabase.com" not in text.replace("supabase.com`", ""), name
        assert "pooler.supabase" not in text, name


def test_env_example_points_at_the_local_database():
    line = next(
        ln for ln in (REPO / ".env.example").read_text().splitlines() if ln.startswith("DATABASE_URL=")
    )

    assert "localhost:5433/clinical_ai_db" in line


def test_the_production_connection_file_is_git_ignored():
    ignored = (REPO / ".gitignore").read_text().splitlines()

    assert ".env.*.local" in ignored


# --- inspecting production safely ------------------------------------------


def _load_inspect():
    spec = importlib.util.spec_from_file_location("inspect_db", REPO / "scripts" / "inspect_db.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_inspect_reads_its_own_variable_never_database_url(tmp_path):
    inspect_db = _load_inspect()
    env_file = tmp_path / ".env.production.local"
    env_file.write_text('OTHER=1\nINSPECT_DATABASE_URL="postgresql+asyncpg://ro:pw@h:5432/db"\n')

    assert inspect_db.load_url({}, env_file) == "postgresql+asyncpg://ro:pw@h:5432/db"
    assert inspect_db.load_url({"INSPECT_DATABASE_URL": "x://e"}, env_file) == "x://e"
    with pytest.raises(SystemExit):
        inspect_db.load_url({"DATABASE_URL": SUPABASE}, tmp_path / "missing")


def test_inspect_never_prints_the_password():
    inspect_db = _load_inspect()

    out = inspect_db.describe("postgresql+asyncpg://ro:SuperSecretPw1@host.example.com:5432/postgres")

    assert out == "ro@host.example.com:5432/postgres"


def test_the_read_only_role_script_grants_select_and_nothing_else():
    sql = (REPO / "migrations" / "readonly_role.sql").read_text()
    statements = "\n".join(ln for ln in sql.splitlines() if not ln.strip().startswith("--"))

    assert "GRANT SELECT ON ALL TABLES" in statements
    assert "default_transaction_read_only = on" in statements
    for forbidden in (
        "INSERT",
        "UPDATE",
        "DELETE",
        "TRUNCATE",
        "CREATE TABLE",
        "SUPERUSER",
        "ALL PRIVILEGES",
    ):
        assert forbidden not in statements.replace("CREATE ROLE", "").upper().replace("CREATE ROLE", ""), (
            forbidden
        )
