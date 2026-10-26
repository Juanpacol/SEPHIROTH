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

`scripts/dev.sh up` (see "Local LLM (Ollama) instead of Gemini" below) brings
up the whole stack — Postgres, the API, the frontend, and, for the `local`
profile, this project's own native Ollama — in one command via Docker. The
three-terminal flow below is the bare-metal alternative: slower to set up
once, but `--reload`/Next.js hot-reload make it the faster loop for active
backend/frontend iteration.

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

### Local LLM (Ollama) instead of Gemini

`scripts/dev.sh` is the one entry point for the whole local stack, in either
of two **profiles** (`config/profiles/local.env` / `cloud.env` — non-secret
provider/model/timeout defaults; `.env` holds only secrets, loaded on top):

```bash
ollama pull qwen3:8b            # or whatever local.env's OLLAMA_MODEL is
ollama pull qwen2.5vl:3b        # or whatever local.env's OLLAMA_VISION_MODEL is
                                 # (nomic-embed-text, used for RAG retrieval, is
                                 # pulled automatically by `up local` if missing —
                                 # see `start_ollama` in scripts/dev.sh)
scripts/dev.sh up local         # Postgres + this project's OWN native
                                 # `ollama serve` (port 11435, never 11434 —
                                 # see local.env's comment) + API + frontend
scripts/dev.sh doctor           # real chat + vision call, not just "configured"
scripts/dev.sh down             # stops everything dev.sh started; leaves an
                                 # ollama serve it only *reused* running
```

`scripts/dev.sh up cloud` runs the same stack against Gemini instead —
useful to A/B a change against both without hand-editing `.env` between
runs. `scripts/dev.sh status` shows what's up without the deep LLM probe;
`doctor` is the same plus one real round-trip per model, so it costs an
extra few seconds.

Ollama runs as a **native** process the script starts itself, not a Docker
Compose service — on Apple Silicon that's the difference between the GPU
(Metal) answering a request and the CPU doing it, and a container gets no
Metal access at all. It's given its own port (11435 by default) specifically
so it never collides with, or gets silently pointed at, some other Ollama
instance already running on this machine for an unrelated project — a real
failure mode before this existed: two different projects' `ollama serve`
both wanted the default 11434, and whichever one didn't lose the race looked
to the other like "the model never responds."

Two local models kept resident at once (`OLLAMA_KEEP_ALIVE=-1`, set by
`dev.sh`) need real memory — budget roughly 6GB for an 8B chat model and 3GB
for a 3B vision model, on top of whatever Postgres/Node/the browser are
already using. On a machine with 16GB total, that is tight enough that disk
swapping (not a crash, not an error) is a realistic explanation for a request
that "never responds" rather than returning quickly or failing outright.
`scripts/dev.sh doctor` (or `GET /health/ready?deep=1` directly) is the
concrete reading to reach for before guessing further — unlike the bare
`llm: "configured"` check (true even when Ollama is down or swapping, since
it does no I/O), `deep=1` makes the same real chat/vision call `/consult`
would and reports which model actually answered. For memory pressure
specifically, pair it with `ollama ps` (loaded models and whether they're
thrashing) and the API logs around the failing request.

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
   disclaimer + `role_prompt` + tool catalog. Add it to the `AGENTS` dict too.
2. Give `src/sephiroth/runtime/intent_router.py` a way to route to it — a
   keyword rule in `_FAST_RULES`, a context-tier signal in `_from_context`,
   or rely on the LLM classification tier (it already enumerates every name
   in `AGENTS`). There is no separate planner to register with since
   `SPEC-029` (Phase 14) removed the multi-agent fan-out — a consultation
   always routes to exactly one specialist.
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

> Looking at production, and the read-only role for it: `docs/05-operations/database-environments.md`.

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
