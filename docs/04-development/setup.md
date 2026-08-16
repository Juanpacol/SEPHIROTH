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
3. Register the server in `SERVERS` in `intelligence/mcp/registry.py`.
4. Add the tool name to the `allowed_tools` of every agent permitted to call it.

Step 4 is not optional. `allowed_tools` is enforced at dispatch by
`MCPRegistry.scoped_executor()`; a tool absent from an agent's whitelist returns
`{"error": "Tool not authorized for this agent: ..."}` instead of running.

### Add an agent

1. Subclass `MCPAgent` in `intelligence/agents/__init__.py`.
2. Set `name`, `role_prompt`, and `allowed_tools`.
   The attribute is **`role_prompt`**, not `system_prompt`.
3. Wire it into `intelligence/agents/workflow.py`.
4. Add an entry to `_ACTION_TEMPLATES` / `_NO_TOOL_ACTIONS` in
   `intelligence/agents/explainability.py`.

Step 4 is easy to miss and degrades **historical** consultations: `explanation`
is rebuilt on read rather than persisted, so a missing template changes how past
consultations render in history and PDF export.

```python
class PathologyAgent(MCPAgent):
    name = "pathology"
    role_prompt = "You are the pathology specialist..."
    allowed_tools = ["analyze_specimen"]
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

## Vendored code

`references/` holds cloned open-source projects for reference and is read-only.
`intelligence/medical-imaging/{networks,transforms}` is a vendored copy of MONAI
and should become a pip dependency rather than maintained in-repo.

`intelligence/nlp/{ner,pipeline,preprocessing}` is vendored MedCAT that was
never wired into anything — the entity extraction actually in use is the
lexicon-based extractor in `intelligence/mcp/nlp_server.py`.
