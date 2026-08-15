# Drug interactions — DDInter 2.0

**Source:** [DDInter 2.0](https://ddinter2.scbdd.com) — a curated drug-drug interaction database.
**License:** free to use; cite DDInter if redistributed. **Non-commercial use only** — see [ddinter2.scbdd.com](https://ddinter2.scbdd.com) for terms before any commercial deployment.

## What's actually in `ddinter_subset.json`

DDInter's public bulk CSV download gives a validated **severity classification** per drug pair (`Major`/`Moderate`/`Minor`/`Unknown`) — it does **not** include per-pair mechanism or management text (that only exists on DDInter's individual drug detail pages, not meant for bulk scraping).

So this subset is honest about what it is: real, sourced severity levels, with a **generic advisory tied to the severity tier** (not a fabricated per-pair mechanism) — e.g. every "major" pair gets the same tier-level effect/recommendation text, tagged `"source": "DDInter 2.0"`.

This is deliberately kept separate from the hand-curated pairs in `intelligence/mcp/drug_safety_server.py::INTERACTIONS`, which have real, pair-specific mechanism text (e.g. "NSAIDs increase bleeding risk and may raise INR") written from clinical references — those always take priority and are never overridden.

## Scope

Filtered to drug pairs where **both** drugs are in this project's medication vocabulary (see `DRUG_VOCABULARY` in `fetch_ddinter.py`) — the full DDInter bulk export is 100k+ pairs across every drug class; only pairs relevant to SEPHIROTH's demo patients and curated interactions were kept (193 pairs, `Major`/`Moderate`/`Minor` only — `Unknown` severity is dropped as not clinically actionable).

## Refreshing

```bash
PYTHONPATH=. python3 real_data/drug_interactions/fetch_ddinter.py
```

Requires network access to `ddinter2.scbdd.com`. Never run in CI/tests — `intelligence/mcp/drug_safety_server.py` degrades gracefully (falls back to the hand-curated table only) if `ddinter_subset.json` is missing.
