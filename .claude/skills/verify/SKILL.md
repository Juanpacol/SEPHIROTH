---
name: verify
description: Launch SEPHIROTH locally and smoke-test the core flow (health, auth, one consultation) — this repo's project verify skill, with this machine's port/venv quirks baked in.
---

# Launching and verifying SEPHIROTH locally

This machine runs other Docker stacks that squat the default ports — always use the ports below, not the framework defaults.

## Port map (this machine)

| Service | Default | Actual (this machine) |
|---|---|---|
| Ollama | 11434 | **11435** |
| Postgres | 5432 | **5433** |
| Backend | 8000 | 8000 (but always hit `127.0.0.1`, not `localhost` — IPv4 only) |
| Frontend | 3000 | **3100** |

These are set in `.env` (gitignored) and read by `platform/core/config.py`. If `.env` is missing, recreate it from `.env.example` and override `OLLAMA_HOST=http://127.0.0.1:11435` and `DATABASE_URL=...localhost:5433/...`.

## Launch sequence

```bash
cd clinical-ai-copilot

# 1. Ollama (native, Metal GPU — NOT Docker, which would run qwen3:8b on CPU)
OLLAMA_HOST=127.0.0.1:11435 ollama serve &
curl -s -m 3 http://127.0.0.1:11435/api/tags   # confirm reachable + qwen3:8b present

# 2. Postgres
docker compose up -d postgres

# 3. Backend (platform/ is on PYTHONPATH, not a package — see CLAUDE.md)
PYTHONPATH=.:platform .venv/bin/uvicorn api.main:app --reload --port 8000 &
curl -s http://127.0.0.1:8000/health

# 4. Frontend
cd platform/frontend && npm run dev -- --port 3100 &
```

If `.venv` doesn't exist yet: `python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt` (system `python3` is 3.9 — too old).

## Smoke test

```bash
# Health
curl -s http://127.0.0.1:8000/health

# Register + capture token
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/auth/register -H "Content-Type: application/json" \
  -d '{"email": "verify@test.local", "name": "Verify Bot", "password": "verifypass123"}' \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

# One real consultation through the full multi-agent workflow
curl -s -X POST http://127.0.0.1:8000/api/agents/consult \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "What A1C goal is appropriate for a nonpregnant adult with type 2 diabetes?"}' \
  | python3 -m json.tool
```

Confirm the response has a non-empty `answer`, `citation_report.fabricated == []` (or explains why not), and `agents_involved` includes `"evidence"`.

## If something's wrong

- **Backend 503 on /consult**: Ollama isn't reachable at the configured host, or the model isn't pulled. Error message names the exact `ollama pull <model>` command to run.
- **Slow inference**: check you're not accidentally talking to a Dockerized Ollama on 11434 (CPU-only on macOS, ~3× slower than native Metal on 11435).
- **Import errors on backend start**: confirm `platform/` has no `__init__.py` at its root (it would shadow the stdlib `platform` module) and that `PYTHONPATH=.:platform` is set.
