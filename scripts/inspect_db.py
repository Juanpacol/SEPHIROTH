#!/usr/bin/env python3
"""Look at a database without being able to change it (AB#18).

The safe way to see production. It connects with a read-only role
(`migrations/readonly_role.sql`), refuses any role that could write, opens a
read-only transaction anyway, and prints counts and versions -- never row
contents.

The connection string comes from `INSPECT_DATABASE_URL`, in the environment or
in `.env.production.local` (git-ignored). It is deliberately a different name
from `DATABASE_URL`: the app and docker compose read that one, and this tool
must never inherit it.

Usage:
    python scripts/inspect_db.py
    INSPECT_DATABASE_URL=postgresql+asyncpg://clinical_ai_readonly:...@host:5432/postgres \\
        python scripts/inspect_db.py
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / ".env.production.local"
URL_VAR = "INSPECT_DATABASE_URL"
#: Counted when present. Names only: they are interpolated, never user input.
TABLES = (
    "users",
    "patients",
    "consultations",
    "response_ratings",
    "auto_grades",
    "review_access_log",
    "alerts",
    "appointments",
)
WRITE_PRIVILEGES = "INSERT,UPDATE,DELETE,TRUNCATE"


class NotReadOnly(RuntimeError):
    """The role in use could change data."""


def load_url(environ: Optional[dict] = None, env_file: Path = ENV_FILE) -> str:
    environ = os.environ if environ is None else environ
    if environ.get(URL_VAR):
        return environ[URL_VAR]
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip() == URL_VAR and value.strip():
                return value.strip().strip('"').strip("'")
    raise SystemExit(
        f"{URL_VAR} is not set (environment or {env_file.name}). "
        "See docs/05-operations/database-environments.md."
    )


def describe(url: str) -> str:
    """`user@host/db` with the password removed, for printing."""
    return re.sub(r"//([^:@/]+)(?::[^@]*)?@", r"//\1@", url).split("//", 1)[-1]


async def assert_read_only(conn: AsyncConnection) -> None:
    """Refuse a role that can write. A refusal here is the point of the tool:
    the owner role must not be usable by mistake."""
    superuser = await conn.scalar(text("select rolsuper from pg_roles where rolname = current_user"))
    if superuser:
        raise NotReadOnly("this role is a superuser")
    writable = (
        (
            await conn.execute(
                text(
                    "select table_name from information_schema.tables where table_schema = 'public' "
                    "and table_type = 'BASE TABLE' and has_table_privilege(current_user, "
                    "quote_ident(table_schema) || '.' || quote_ident(table_name), :privs)"
                ),
                {"privs": WRITE_PRIVILEGES},
            )
        )
        .scalars()
        .all()
    )
    if writable:
        raise NotReadOnly(f"this role can write to {len(writable)} table(s), e.g. {writable[0]}")
    can_create = await conn.scalar(text("select has_schema_privilege(current_user, 'public', 'CREATE')"))
    if can_create:
        raise NotReadOnly("this role can create objects in schema public")


async def inspect(url: str) -> dict:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SET TRANSACTION READ ONLY"))
            await assert_read_only(conn)
            out: dict = {"database": await conn.scalar(text("select current_database()"))}
            out["alembic"] = await conn.scalar(text("select version_num from alembic_version"))
            present = set(
                (
                    await conn.execute(text("select tablename from pg_tables where schemaname = 'public'"))
                ).scalars()
            )
            for table in TABLES:
                if table in present:
                    out[table] = await conn.scalar(text(f"select count(*) from {table}"))  # nosec B608 -- fixed names
            out["last_consultation"] = (
                await conn.scalar(text("select max(created_at) from consultations"))
                if "consultations" in present
                else None
            )
            return out
    finally:
        await engine.dispose()


def main() -> int:
    url = load_url()
    print(f"inspecting {describe(url)} (read-only)")
    try:
        result = asyncio.run(inspect(url))
    except NotReadOnly as exc:
        print(f"refused: {exc}. Use the read-only role (migrations/readonly_role.sql).", file=sys.stderr)
        return 2
    for key, value in result.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
