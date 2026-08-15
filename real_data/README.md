# `real_data/` — verified, licensed sample data

Optional, real/synthetic sample data to make SEPHIROTH's demo experience realistic — patients with actual clinical histories, real drug-interaction severities, and a real chest X-ray, instead of only the two hand-typed demo patients. **Nothing here is required to run the app or the test suite** — see [Qué NO cambia](#qué-no-cambia-y-por-qué) below.

Each source was chosen after explicit research into which one is genuinely verifiable and appropriately licensed for this use — see the conversation history / project docs for the comparison against alternatives that were rejected (NIH ChestX-ray14, CheXpert, MIMIC, RxNav, openFDA, DrugBank, n2c2, etc.) and why.

| Folder | Source | License | Committed? | Refresh command |
|---|---|---|---|---|
| `patients/` | [Synthea Coherent Data Set](https://registry.opendata.aws/synthea-coherent-data/) (MITRE) | CC BY 4.0 / Apache 2.0 | ✅ `sample_patients.json` (12 patients, parsed) | `python3 real_data/patients/fetch_synthea_sample.py` |
| `notes/` | Derived from the Synthea patients above, via SEPHIROTH's own Gemini client (same role as `synthetichealth/chatty-notes`) | 100% synthetic | ✅ `sample_notes.json` (6 notes — see its README for an honest note on how these were actually authored) | `python3 real_data/notes/generate_notes.py` |
| `drug_interactions/` | [DDInter 2.0](https://ddinter2.scbdd.com) | CC BY-NC (**non-commercial**) | ✅ `ddinter_subset.json` (193 pairs, severity real + tier-based advisory text) | `python3 real_data/drug_interactions/fetch_ddinter.py` |
| `imaging/` | [RSNA Pneumonia Detection Challenge](https://www.kaggle.com/competitions/rsna-pneumonia-detection-challenge) (via Kaggle) | Academic/non-commercial, **not redistributable** | ❌ never — `samples/` is gitignored | `python3 real_data/imaging/fetch_rsna_samples.py --count 10` (needs your own Kaggle credentials) |

Each subfolder has its own `README.md` with the full detail on what's actually in the data, its exact license terms, and how it's used by the app.

## Qué NO cambia (y por qué)

- **`platform/core/db.py::SEED_PATIENTS`** (the two demo patients, P001/P002) is untouched — it's the deterministic fixture the test suite depends on. Synthea patients are *additive*, imported separately, never auto-seeded.
- **`intelligence/mcp/drug_safety_server.py::INTERACTIONS`** (hand-curated pairs) is untouched and always takes priority — DDInter only fills gaps, and gracefully degrades to hand-curated-only if `ddinter_subset.json` is ever missing.
- **Nothing in this folder runs automatically** — not in `pytest`, not in CI, not in `init_db()`. Every `fetch_*.py`/`import_*.py`/`generate_*.py` script is meant to be run by hand, exactly like the existing `data/embeddings/build_artifact.py` and the `references/` clone instructions in the main README.
- **`data/rag/SEED_GUIDELINES`** (the RAG corpus) is untouched — no programmatic source was found reliable enough to expand it automatically (see `drug_interactions/README.md` and the project's evaluation research); it keeps growing via the `/add-guideline` skill.

## Licensing summary (read before any commercial use)

If SEPHIROTH is ever monetized, **`drug_interactions/` (DDInter, CC BY-NC) and `imaging/` (RSNA, academic/non-commercial) both require a separate commercial license or removal** before that happens. `patients/` and `notes/` (Synthea-derived) have no such restriction.
