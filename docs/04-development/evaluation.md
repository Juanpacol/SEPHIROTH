# RAG Evaluation — Methodology

Full detail behind the metrics table in [README.md](../../README.md#evaluation). Read this when you need to regenerate the baseline, tune retrieval, or understand why a number is what it is.

## Modes

- **`--mode ci`** (offline, deterministic, <5s): Recall@k and MRR are recomputed live against `RAGPipeline.retrieve()` and the golden dataset; Citation Precision is recomputed by replaying the Citation Guard over committed transcripts. Runs on every PR — no Gemini API key required.
- **`--mode full`** (calls the Gemini API, burns free-tier quota): runs the real Evidence Agent end-to-end, records fresh transcripts, and scores Faithfulness with an LLM judge (per-claim: "is this supported by the retrieved evidence?"). Writes `results/latest.json`.
- The committed results embed a SHA-256 hash of the dataset and transcripts. If either changes without a fresh `--mode full --record` run, CI fails on a stale baseline rather than silently trusting outdated numbers.

```bash
PYTHONPATH=.:platform .venv/bin/python -m intelligence.evaluation.run --mode ci
PYTHONPATH=.:platform .venv/bin/python -m intelligence.evaluation.run --mode full --record --skip-pubmed
```

Recall@1/@3/@5 and MRR are live, verified numbers from the hybrid retriever (below), run via `--mode ci` against the committed embeddings artifact (reproducible offline). Citation Precision and Faithfulness come from a live `--mode full --record` run against `qwen3:8b` via local Ollama — the model this deployment actually runs, not a Gemini stand-in. The raw per-case citation count (`intelligence/evaluation/results/latest.json`'s `citation.per_case`) shows a real, unresolved gap below the aggregate: 13 of 27 citations across cases were outright fabricated (the Evidence Agent answering from parametric memory instead of calling its retrieval tool — a known local-model tool-calling reliability issue). Regenerate against Gemini instead: `--mode full --record --skip-pubmed` (defaults to `--provider gemini`).

Full numbers, per-case breakdown, and run metadata: [`intelligence/evaluation/results/latest.json`](../../intelligence/evaluation/results/latest.json).

## Hybrid retrieval (dense embeddings + keyword)

`data/rag/RAGPipeline.retrieve()` fuses keyword-overlap scoring with dense embeddings via Reciprocal Rank Fusion — keyword-only Recall@1 misses colloquial paraphrases ("my kid has an ear infection" → *Acute Otitis Media*) that share little vocabulary with the guideline text.

- **Storage is pgvector, not in-memory** (`ADR-017`). `RAGPipeline()` requires an `embedding_provider` and queries `guideline_documents` on every call — no keyword-only fallback mode. Populate once per environment: `alembic upgrade head` then `python -m data.rag.seed_pgvector`. RAG tests self-skip without a local Postgres.
- **Deterministic query-side embeddings in CI.** A committed, hashed artifact (`data/embeddings/artifacts/seed_embeddings.json.gz`) supplies query vectors for `--mode ci` and the test suite — no network needed. Rebuild: `python -m data.embeddings.build_artifact --provider ollama` (must match the committed artifact's model — `--provider gemini` produces an incompatible vector space). Document-side embeddings are computed once at seed time, not re-read from this artifact.
- **Similarity floor, empirically calibrated.** `retrieval_min_similarity` (**0.636**) drops low-confidence dense hits — tuned against real scores, with a tight margin (best adversarial match 0.6334, weakest genuinely-relevant document 0.6380; see `tests/test_embeddings_matching.py`). It doesn't try to detect "pseudo-scientific" content from embeddings alone — that's the Citation Guard's job, checking whether specific claims are grounded in what a retrieved document actually says.
- **Dense-weighted fusion.** RRF weights the dense signal 2x over keyword (`DENSE_WEIGHT`/`KEYWORD_WEIGHT` in `data/rag/__init__.py`) — keyword scoring isn't IDF-weighted, so short documents sharing only generic words with the query could otherwise rank artificially high.
- **Matching-quality test suite** (`tests/test_embeddings_matching.py`, `tests/test_rag_pipeline.py`) pins specific match/no-match pairs so a regression fails by name, not just as a dip in an aggregate metric.

**Honest limitations:**
- Citation Precision and Faithfulness in the README table are from the pre-Gemini baseline (`llama3.2:latest` stand-in). Regenerating against `gemini-flash-latest` needs enough free-tier quota to run one agent consultation per golden case — some Gemini aliases carry low daily caps independent of the per-minute rate limit.
- The LLM judge is the same model family as the generator on the committed baseline (a self-judging limitation); an independent judge model would be a stronger signal.

## Free-tier quota management (Gemini + Groq fallback)

Neither Gemini's nor Groq's free tiers are unlimited — Gemini caps requests per minute **and** per day, and newer model aliases can carry stricter daily caps than older ones.

`src/sephiroth/models/factory.py::get_llm_client()` optionally wraps Gemini with a Groq fallback for text/tool-calling (`src/sephiroth/models/fallback.py::FallbackLLMClient`):

- Set `GROQ_API_KEY` (free key at [console.groq.com/keys](https://console.groq.com/keys)) to enable it — unset, behavior is identical to a bare Gemini client.
- `chat()`/`generate_json()` try Gemini first; on failure (rate limit, quota exhaustion, outage) they fall through to Groq (`llama-3.3-70b-versatile` by default, `GROQ_MODEL`) — same `ChatResult` contract.
- Vision and embeddings always stay on Gemini — Groq has no comparable endpoint.
- Set `LLM_ENABLE_FALLBACK=false` to disable fallback even with a Groq key configured.

```bash
# .env
GROQ_API_KEY=your-groq-key
GROQ_MODEL=llama-3.3-70b-versatile   # default
```
