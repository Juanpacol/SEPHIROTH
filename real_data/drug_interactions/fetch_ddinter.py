"""
Rebuild `ddinter_subset.json` from DDInter 2.0's public bulk CSVs.

DDInter (https://ddinter2.scbdd.com) publishes 8 CSVs, one per ATC top-level
code, each with rows of `DDInterID_A,Drug_A,DDInterID_B,Drug_B,Level`. The
bulk download gives a validated MAJOR/MODERATE/MINOR severity classification
per pair — it does NOT include per-pair mechanism/management text (that only
exists on DDInter's per-drug detail pages, which aren't meant for bulk
scraping). So this script:

  1. Downloads the ATC categories relevant to the medications this project's
     agents/demo patients actually reference (cardiovascular, metabolic,
     respiratory, hormonal — see `RELEVANT_ATC_CODES`).
  2. Filters to pairs where BOTH drugs are in `DRUG_VOCABULARY` (the generic
     names already used across SEPHIROTH's curated data, demo patients, and
     tests) — the full bulk files are 100k+ rows total and mostly irrelevant
     to this project's domain.
  3. Drops rows classified "Unknown" (not clinically actionable) and any
     pair already covered by the hand-curated table in
     `intelligence/mcp/drug_safety_server.py::INTERACTIONS` (that table's
     text is pair-specific and takes priority; DDInter only fills gaps).
  4. Attaches a generic, HONEST, severity-tier advisory (not a fabricated
     per-pair mechanism) plus a `source` field crediting DDInter, and writes
     the committed `ddinter_subset.json`.

Run manually, never in CI/tests (network required):

    PYTHONPATH=. python3 real_data/drug_interactions/fetch_ddinter.py
"""

from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

import httpx

BASE_URL = "https://ddinter2.scbdd.com/static/media/download"
RELEVANT_ATC_CODES = ["A", "B", "R", "H"]  # metabolism, blood, respiratory, hormones

OUTPUT_PATH = Path(__file__).parent / "ddinter_subset.json"

# Generic names already used in SEPHIROTH: hand-curated INTERACTIONS,
# real_data/patients demo medications, and the eval/test fixtures. Extend
# this list as the project's medication vocabulary grows.
DRUG_VOCABULARY = {
    "warfarin",
    "aspirin",
    "ibuprofen",
    "lisinopril",
    "spironolactone",
    "metformin",
    "sertraline",
    "tramadol",
    "simvastatin",
    "clarithromycin",
    "digoxin",
    "furosemide",
    "atorvastatin",
    "amiodarone",
    "metoprolol",
    "losartan",
    "omeprazole",
    "fluoxetine",
    "citalopram",
    "apixaban",
    "rivaroxaban",
    "clopidogrel",
    "prednisone",
    "levothyroxine",
    "amlodipine",
    "hydrochlorothiazide",
    "insulin",
    "gabapentin",
    "tamsulosin",
    "allopurinol",
    "enalapril",
    "atenolol",
    "carvedilol",
    "pantoprazole",
    "escitalopram",
    "esomeprazole",
    "naproxen",
    "diclofenac",
    "celecoxib",
    "heparin",
    "enoxaparin",
}

# Pairs already hand-curated in intelligence/mcp/drug_safety_server.py::INTERACTIONS —
# that text is pair-specific and takes priority; never duplicate it here.
HAND_CURATED_PAIRS = {
    frozenset(["warfarin", "aspirin"]),
    frozenset(["warfarin", "ibuprofen"]),
    frozenset(["lisinopril", "spironolactone"]),
    frozenset(["lisinopril", "potassium"]),
    frozenset(["metformin", "iodinated contrast"]),
    frozenset(["sertraline", "tramadol"]),
    frozenset(["simvastatin", "clarithromycin"]),
    frozenset(["digoxin", "furosemide"]),
}

#: DDInter's bulk download gives only a MAJOR/MODERATE/MINOR severity tier,
#: no free-text description per pair — these are the plain-language stand-in
#: (a clinician skimming a chart needs "what to do", not a citation of the
#: classification scheme that produced the tier). Kept short and direct on
#: purpose, matching the hand-curated pairs' own tone above.
TIER_TEXT = {
    "major": {
        "effect": "Serious interaction — taking these together can cause real harm.",
        "recommendation": "Avoid this combination if possible; if it's needed, watch the patient closely.",
    },
    "moderate": {
        "effect": "Moderate interaction — may need a dose change or extra monitoring.",
        "recommendation": (
            "Use together with caution — watch for signs of the interaction and adjust treatment as needed."
        ),
    },
    "minor": {
        "effect": "Minor interaction — usually not a problem for most patients.",
        "recommendation": "Generally safe to combine; keep an eye out for any unusual symptoms.",
    },
}


def _download_csv(code: str) -> list[dict]:
    url = f"{BASE_URL}/ddinter_downloads_code_{code}.csv"
    response = httpx.get(url, timeout=30, follow_redirects=True)
    response.raise_for_status()
    return list(csv.DictReader(io.StringIO(response.text)))


def build() -> list[dict]:
    seen: set[frozenset] = set()
    pairs: list[dict] = []

    for code in RELEVANT_ATC_CODES:
        print(f"Downloading category {code}...", file=sys.stderr)
        for row in _download_csv(code):
            a = row["Drug_A"].strip().lower()
            b = row["Drug_B"].strip().lower()
            level = row["Level"].strip().lower()

            if a not in DRUG_VOCABULARY or b not in DRUG_VOCABULARY:
                continue
            if level not in TIER_TEXT:
                continue  # drop "unknown" — not clinically actionable

            key = frozenset([a, b])
            if key in seen or key in HAND_CURATED_PAIRS:
                continue
            seen.add(key)

            tier = TIER_TEXT[level]
            pairs.append(
                {
                    "drug_a": a,
                    "drug_b": b,
                    "severity": level,
                    "effect": tier["effect"],
                    "recommendation": tier["recommendation"],
                    "source": "DDInter 2.0 (https://ddinter2.scbdd.com)",
                }
            )

    pairs.sort(key=lambda d: (d["drug_a"], d["drug_b"]))
    return pairs


def main() -> int:
    pairs = build()
    with open(OUTPUT_PATH, "w") as f:
        json.dump(pairs, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Wrote {len(pairs)} pairs to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
