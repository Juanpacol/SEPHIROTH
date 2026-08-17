#!/usr/bin/env python3
"""Export the SEPHIROTH domain contracts as JSON Schema.

The committed schemas under `docs/specs/contracts/` are the machine-readable
half of the specification. Regenerating them is how a contract change becomes
visible in review: `tests/test_contracts_schema.py` fails if the code and the
committed schema disagree, so a field cannot change without the spec artefact
changing alongside it.

Usage:
    python scripts/export_contracts.py            # write schemas
    python scripts/export_contracts.py --check    # verify, exit 1 on drift
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sephiroth.contracts import PUBLIC_MODELS

CONTRACTS_DIR = Path(__file__).resolve().parents[1] / "docs" / "specs" / "contracts"


def _schema_path(model: type) -> Path:
    """`ExecutionPlan` -> `execution_plan.schema.json`."""
    snake = "".join(f"_{c.lower()}" if c.isupper() else c for c in model.__name__).lstrip("_")
    return CONTRACTS_DIR / f"{snake}.schema.json"


def _render(model: type) -> str:
    # sort_keys so the output is stable across Python versions and dict
    # ordering changes — otherwise the drift check produces false positives.
    return json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n"


def export(check_only: bool = False) -> int:
    CONTRACTS_DIR.mkdir(parents=True, exist_ok=True)
    drifted: list[str] = []
    written = 0

    expected_files = set()
    for model in PUBLIC_MODELS:
        path = _schema_path(model)
        expected_files.add(path.name)
        rendered = _render(model)

        if check_only:
            if not path.exists():
                drifted.append(f"{path.name}: missing (model {model.__name__} has no schema)")
            elif path.read_text() != rendered:
                drifted.append(f"{path.name}: out of date")
        else:
            if not path.exists() or path.read_text() != rendered:
                path.write_text(rendered)
                written += 1

    # A model removed from PUBLIC_MODELS must not leave its schema behind.
    for stale in sorted(CONTRACTS_DIR.glob("*.schema.json")):
        if stale.name not in expected_files:
            if check_only:
                drifted.append(f"{stale.name}: orphaned (no corresponding model)")
            else:
                stale.unlink()

    if check_only:
        if drifted:
            print("Contract schema drift detected:", file=sys.stderr)
            for item in drifted:
                print(f"  - {item}", file=sys.stderr)
            print(
                "\nRun `python scripts/export_contracts.py` and commit the result.",
                file=sys.stderr,
            )
            return 1
        print(f"OK — {len(PUBLIC_MODELS)} contract schemas match.")
        return 0

    print(f"Exported {len(PUBLIC_MODELS)} schemas to {CONTRACTS_DIR} ({written} changed).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify committed schemas match the models; exit 1 on drift",
    )
    args = parser.parse_args()
    return export(check_only=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
