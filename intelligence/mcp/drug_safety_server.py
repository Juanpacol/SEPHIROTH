"""FastMCP server exposing drug interaction and safety checks."""

import json
import logging
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List

from fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP(
    name="drug-safety",
    instructions="Drug-drug interaction screening against a curated interaction table.",
)

# Curated, well-established interaction pairs (normalized lowercase).
# Extend via data ingestion or an external service (e.g. RxNorm) later.
INTERACTIONS: Dict[frozenset, Dict[str, str]] = {
    frozenset(["warfarin", "aspirin"]): {
        "severity": "major",
        "effect": "Additive anticoagulation markedly increases bleeding risk.",
        "recommendation": "Avoid combination unless specifically indicated; monitor INR closely.",
    },
    frozenset(["warfarin", "ibuprofen"]): {
        "severity": "major",
        "effect": "NSAIDs increase bleeding risk and may raise INR.",
        "recommendation": "Prefer acetaminophen for analgesia in anticoagulated patients.",
    },
    frozenset(["lisinopril", "spironolactone"]): {
        "severity": "moderate",
        "effect": "Combined ACE inhibitor and potassium-sparing diuretic can cause hyperkalemia.",
        "recommendation": "Monitor serum potassium and renal function.",
    },
    frozenset(["lisinopril", "potassium"]): {
        "severity": "moderate",
        "effect": "ACE inhibitors reduce potassium excretion; supplements add to hyperkalemia risk.",
        "recommendation": "Monitor potassium; avoid routine supplementation.",
    },
    frozenset(["metformin", "iodinated contrast"]): {
        "severity": "major",
        "effect": "Risk of contrast-induced nephropathy and lactic acidosis.",
        "recommendation": (
            "Hold metformin at the time of contrast administration; recheck renal function at 48h."
        ),
    },
    frozenset(["sertraline", "tramadol"]): {
        "severity": "major",
        "effect": "Increased risk of serotonin syndrome and seizures.",
        "recommendation": "Avoid combination or monitor closely for serotonergic symptoms.",
    },
    frozenset(["simvastatin", "clarithromycin"]): {
        "severity": "major",
        "effect": "CYP3A4 inhibition raises statin levels; rhabdomyolysis risk.",
        "recommendation": "Suspend simvastatin during clarithromycin course.",
    },
    frozenset(["digoxin", "furosemide"]): {
        "severity": "moderate",
        "effect": "Diuretic-induced hypokalemia potentiates digoxin toxicity.",
        "recommendation": "Monitor potassium and digoxin levels.",
    },
}

# Real-data extension (DDInter 2.0 — see real_data/drug_interactions/README.md).
# Never overrides a hand-curated pair above (that text is pair-specific);
# only fills in additional pairs DDInter covers. Missing file degrades
# gracefully — INTERACTIONS just stays at the hand-curated set.
_DDINTER_SUBSET_PATH = (
    Path(__file__).parent.parent.parent / "real_data" / "drug_interactions" / "ddinter_subset.json"
)


def _load_ddinter_subset(path: Path = _DDINTER_SUBSET_PATH) -> Dict[frozenset, Dict[str, str]]:
    if not path.exists():
        return {}
    try:
        entries = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        logger.exception("Failed to load DDInter subset from %s", path)
        return {}

    extra: Dict[frozenset, Dict[str, str]] = {}
    for entry in entries:
        key = frozenset([entry["drug_a"], entry["drug_b"]])
        if key in INTERACTIONS:
            continue  # hand-curated text always wins
        extra[key] = {
            "severity": entry["severity"],
            "effect": entry["effect"],
            "recommendation": entry["recommendation"],
            "source": entry.get("source", "DDInter 2.0"),
        }
    return extra


INTERACTIONS.update(_load_ddinter_subset())


def _normalize(name: str) -> str:
    return name.strip().lower()


def find_interactions(medications: List[str]) -> List[Dict[str, Any]]:
    """Plain lookup shared by the MCP tool and the risk engine."""
    normalized = [_normalize(m) for m in medications if m.strip()]
    findings = []
    for a, b in combinations(sorted(set(normalized)), 2):
        hit = INTERACTIONS.get(frozenset([a, b]))
        if hit:
            findings.append({"pair": [a, b], **hit})
    return findings


@mcp.tool
def check_drug_interactions(medications: List[str]) -> Dict[str, Any]:
    """Screen a medication list for known drug-drug interactions. Pass generic
    names (e.g. ["warfarin", "aspirin", "metformin"]). Returns interacting
    pairs with severity, mechanism, and recommendations."""
    normalized = [_normalize(m) for m in medications if m.strip()]
    findings = find_interactions(medications)

    return {
        "medications_checked": normalized,
        "interactions_found": len(findings),
        "interactions": findings,
        "disclaimer": (
            "Screening against a curated table only — not exhaustive. "
            "Verify with a pharmacist or a complete interaction database."
        ),
    }
