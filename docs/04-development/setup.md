# Development setup

> Replaces the former `docs/INTEGRATION_GUIDE.md`, which described a structure
> the repository never had. Everything below is verified against the code.

## Prerequisites

- Python **3.11** (the system `python3` on macOS is 3.9 — too old)
- Node 20 for the frontend
- Docker, for Postgres with the `pgvector` extension

## One-time setup

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e .          # puts src/sephiroth on the path
cd platform/frontend && npm install && cd ../..

# Free Gemini key: https://aistudio.google.com/apikey
echo 'GEMINI_API_KEY=your-key-here' >> .env
```

The editable install matters: `pythonpath` in `pyproject.toml` only affects
pytest. `pip install -e .` is what makes `import sephiroth` work under uvicorn,
`python -m`, and inside Docker. See `docs/00-migration-charter.md` §4.

## Running

```bash
# Terminal 1 — Postgres (host port 5433; 5432 is taken on this machine)
docker compose up -d postgres

# Terminal 2 — API. Runs `alembic upgrade head` and seeds P001/P002 on first boot.
PYTHONPATH=.:platform .venv/bin/uvicorn api.main:app --reload --port 8000

# Terminal 3 — frontend, proxies /api/* to the backend
cd platform/frontend && npm run dev -- --port 3100
```

Always test the backend via `http://127.0.0.1:8000` (IPv4). Frontend is on
**3100** and Postgres on **5433**, because the defaults are occupied by another
project's containers on this machine.

`platform/` must **not** be a Python package — a root `__init__.py` there would
shadow the stdlib `platform` module. It goes on `PYTHONPATH` instead, so its
subpackages import as top-level (`from core.config import settings`).

## Extending the system

### Add an MCP tool

1. Create `intelligence/mcp/my_server.py` with a FastMCP app.
2. Declare tools with `@mcp.tool`, delegating to an implementation under
   `intelligence/` or `data/`.
3. Register the server in `SERVERS` in `src/sephiroth/tools/servers.py`.
4. Add the tool name to the `allowed_tools` of every agent capability permitted to call it.

Step 4 is not optional. `allowed_tools` is enforced at dispatch by
`ToolRuntime.scoped_executor()`; a tool absent from an agent's whitelist returns
`{"error": "Tool not authorized for this agent: ..."}` instead of running.

### Add an agent

1. Add an `AgentCapability` record to `src/sephiroth/runtime/registry.py` —
   `id`, `role_prompt`, and `tools`. The field is **`role_prompt`**, not
   `system_prompt`; the system prompt is assembled in `agent.py` from the
   disclaimer + `role_prompt` + tool catalog.
2. Select it from `route_specialists` in `src/sephiroth/runtime/planner.py`.
3. Add an entry to `_ACTION_TEMPLATES` / `_NO_TOOL_ACTIONS` in
   `src/sephiroth/telemetry/explain.py`.

Step 3 is easy to miss and degrades **historical** consultations: `explanation`
is rebuilt on read rather than persisted, so a missing template changes how past
consultations render in history and PDF export.

```python
PATHOLOGY = AgentCapability(
    id="pathology",
    role_prompt="You are the pathology specialist...",
    tools=["analyze_specimen"],
)
```

### Add an API endpoint

1. Create a router in `platform/api/routers/`.
2. Include it in `platform/api/main.py`.
3. Protect it with `Depends(get_current_user)` unless it is deliberately public.

### Change a database model

Models live in `data/schemas/__init__.py`. Generate migrations against a
**fresh local Postgres**, never against Supabase:

```bash
docker compose down -v postgres && docker compose up -d postgres
DATABASE_URL=postgresql+asyncpg://clinical_ai:clinical_ai_password@localhost:5433/clinical_ai_db \
  PYTHONPATH=.:platform .venv/bin/alembic revision --autogenerate -m "describe the change"
```

Review the generated file — autogenerate does not emit `CREATE EXTENSION` and
does not always get `pgvector.sqlalchemy.Vector` right on the first pass.
`tests/test_alembic_migration.py` is the drift guard; it self-skips when no
local Postgres is reachable.

## Database roles

By default (zero-config local dev) the app connects as `clinical_ai`, the
same role that owns the schema and runs migrations — fine for a laptop, not
for anything shared. To run the app as a least-privilege role instead:

1. Run `migrations/roles.sql` once, connected as the owner role
   (`psql`/Supabase's SQL editor). It creates `clinical_ai_app` — `SELECT`/
   `INSERT`/`UPDATE`/`DELETE` on every table, no `CREATE`/`ALTER`/`DROP`,
   no ownership — and is idempotent (safe to re-run after a schema change,
   since `ALTER DEFAULT PRIVILEGES` covers tables the owner creates later).
2. Point `DATABASE_URL` at `clinical_ai_app`'s connection string instead of
   the owner's.
3. Set `MIGRATION_DATABASE_URL` to the owner role's connection string, so
   `init_db()`'s `alembic upgrade head` on boot (`platform/core/db.py`) still
   has somewhere to run DDL from — `migrations/env.py` prefers it over
   `DATABASE_URL` whenever it's set.

**Local Postgres**: the owner role is `clinical_ai`, the database is
`clinical_ai_db` — `roles.sql` already targets these, no edits needed.

**Supabase**: the owner role is `postgres`, the database is `postgres` —
edit `roles.sql`'s two `ALTER DEFAULT PRIVILEGES FOR ROLE clinical_ai`
lines and its `GRANT CONNECT ON DATABASE clinical_ai_db` line to match
before running it in the SQL editor, then use `clinical_ai_app`'s password
(the one you set in the script) with Supabase's Session pooler host/port
for `DATABASE_URL`, and the existing owner connection string for
`MIGRATION_DATABASE_URL`.

## Vendored code

`references/` holds cloned open-source projects for reference and is read-only.
`intelligence/medical-imaging/{networks,transforms}` is a vendored copy of MONAI
and should become a pip dependency rather than maintained in-repo.

`intelligence/nlp/{ner,pipeline,preprocessing}` is vendored MedCAT that was
never wired into anything — the entity extraction actually in use is the
lexicon-based extractor in `intelligence/mcp/nlp_server.py`.
