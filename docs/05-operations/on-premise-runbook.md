# On-premise deployment

For a clinic that cannot send patient data to a model vendor. Everything runs
on one machine on the clinic's own network: Postgres, the API, and the model.

This is the deployment SPEC-022 made the default. `LLM_PROVIDER` defaults to
`ollama` and `AI_ALLOW_PHI` defaults to `false`, so an installation that
follows this document and sets nothing else sends nothing anywhere.

> This removes one specific exposure — clinical content reaching a third-party
> model. It is not a compliance programme. Disk encryption, backups, physical
> access, staff training and a signed risk assessment are separate work, and
> nothing in this file substitutes for them.

## What you need

| | Minimum | Comfortable |
|---|---|---|
| CPU | 8 cores | 12+ cores |
| RAM | 16 GB | 32 GB |
| Disk | 60 GB free | 120 GB SSD |
| GPU | none (CPU works, slowly) | any NVIDIA card with 12 GB+ VRAM |

Docker and Docker Compose. Nothing else — the model, the database and the
application all arrive as images.

## Choosing a model

`qwen2.5:14b` is the default because it is the smallest model tested here that
handles multi-round tool calling reliably, which the consultation path needs.
Smaller models are faster and give something up; the table says what.

| Model | Disk | RAM in use | What you lose |
|---|---|---|---|
| `qwen2.5:14b` (default) | ~9 GB | ~11 GB | — |
| `qwen2.5:7b` | ~4.7 GB | ~6 GB | Tool calling gets less reliable on multi-step questions; more consultations abstain |
| `qwen2.5:3b` | ~2 GB | ~3 GB | Tool calling is unreliable. Usable for drafting and timeline extraction, not for consultations |
| `llama3.1:8b` | ~4.7 GB | ~6 GB | Comparable to 7b; different failure modes on clinical phrasing |

Embeddings are a separate model: `nomic-embed-text` (~275 MB). It must match
the model the committed RAG artifact was built with — vectors from two
embedding models are not comparable, and mixing them corrupts retrieval
silently rather than failing.

**On CPU, expect 20–60 seconds for a consultation** with the 14B model. On a
GPU with enough VRAM, a few seconds. Neither is wrong; know which one you have
before promising a clinician anything.

## Install

```bash
git clone <this repository> && cd clinical-ai-copilot

cat > .env <<'EOF'
JWT_SECRET=<openssl rand -hex 32>
PHI_ENCRYPTION_KEY=<openssl rand -hex 32>
POSTGRES_PASSWORD=<a real password>
ENVIRONMENT=production
EOF
chmod 600 .env
```

Pull the models before the first full start. This downloads several gigabytes
and is deliberately a step you run and watch, not something that happens
silently on boot:

```bash
docker compose -f docker-compose.local.yml up -d ollama
docker compose -f docker-compose.local.yml exec ollama ollama pull qwen2.5:14b
docker compose -f docker-compose.local.yml exec ollama ollama pull nomic-embed-text
```

Then start everything:

```bash
docker compose -f docker-compose.local.yml up -d
```

Migrations run on boot (`init_db()` calls `alembic upgrade head`), so there is
no separate schema step.

## Verify

Three checks, in this order. Each one answers a question the others do not.

**1. Does the application know what it is running?**

```bash
curl -s http://localhost:8000/health | python3 -m json.tool
```

Expect `"provider": "ollama"`, `"local_only": true`, and the model you pulled.
If it says `gemini`, `LLM_PROVIDER` is set somewhere — check `.env` and the
environment of the container.

**2. Is the model actually reachable?**

```bash
curl -s http://localhost:8000/health/ready | python3 -m json.tool
```

`checks.llm` should be `ok`. `unreachable` means the container is up but the
model is not answering — usually a pull that has not finished.

**3. Does the deployment refuse to leak?**

The one that matters. Log in as a clinician and open the AI status page, or:

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/agents/status | python3 -m json.tool
```

`system.local_only` must be `true` and `system.phi_allowed` must be `false`.
Together those mean: the model is on this machine, and even if someone
repoints it at a hosted endpoint, patient content will be refused rather than
sent.

To see the refusal working, set `LLM_PROVIDER=gemini` temporarily and try a
consultation: it returns `503` naming the provider, and the clinical note
timeline still extracts (via the deterministic lexicon). Put it back.

## When the model is down

By design, not much breaks:

- **Drug-interaction and guideline questions still answer.** They read a local
  table and the guideline corpus; no model was ever involved.
- **Follow-up messages keep their template draft.** A clinician can review and
  send what is on the row.
- **Clinical notes still produce a timeline**, from the deterministic lexicon
  rather than the model.
- **Consultations return 503**, naming Ollama and the model, with the command
  to check.

The API stays in rotation while the model is down — `/health/ready` reports
`llm: unreachable` but `status: ready`, because losing the model degrades
features while losing the database does not.

## Backups

Two volumes, and only one of them matters.

```bash
# The one that matters: patient data.
docker compose -f docker-compose.local.yml exec postgres \
  pg_dump -U clinical_ai clinical_ai_db | gzip > backup-$(date +%F).sql.gz
```

`ollama_models` holds downloaded weights. Do not back it up — it is several
gigabytes of files that can be re-pulled in minutes.

**The dump is PHI.** Columns encrypted at rest (`ClinicalNote.content`, the
`Patient` clinical fields — ADR-014) stay ciphertext inside it, so the dump is
useless without `PHI_ENCRYPTION_KEY`. Which also means: **a backup without that
key is not a backup.** Store the key somewhere the dump is not.

Restore:

```bash
gunzip -c backup-2026-09-06.sql.gz | \
  docker compose -f docker-compose.local.yml exec -T postgres psql -U clinical_ai clinical_ai_db
```

## Upgrading

```bash
git pull
docker compose -f docker-compose.local.yml build api
docker compose -f docker-compose.local.yml up -d api
```

Take a database dump first. Migrations run automatically on boot and are not
reversed automatically.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `/health` says `provider: gemini` | `LLM_PROVIDER` set in `.env` or the shell | Unset it; the default is `ollama` |
| `checks.llm: unreachable` | model not pulled, or still pulling | `docker compose -f docker-compose.local.yml exec ollama ollama list` |
| Consultations time out | CPU inference on a 14B model | Raise `OLLAMA_TIMEOUT_SECONDS`, or move to a smaller model from the table above |
| `model 'x' not found` in logs | pulled a different tag than `OLLAMA_MODEL` | Match the two exactly, tag included |
| RAG returns nothing relevant | embedding artifact built with a different model | Re-pull `nomic-embed-text` and rebuild the artifact |
| Startup log warns about `GEMINI_API_KEY` | a key is set but the provider is local | Harmless. Remove the key if this machine should never reach Google |

## References

- [SPEC-022](../specs/SPEC-022-local-ai.md) — why local is the default.
- [ADR-015](../08-decisions/ADR-015-phi-egress-enumerated-seams.md) — what
  `AI_ALLOW_PHI` does and does not cover.
- [ADR-014](../08-decisions/ADR-014-phi-column-encryption.md) — why the dump is
  useless without the key.
- [production-enablement-runbook.md](production-enablement-runbook.md) — the
  hosted deployment this one replaces for clinical use.
