"""Contract-drift gate: the committed JSON Schema must match the models.

This is the mechanism that makes the specification binding. `docs/specs/contracts/`
is the machine-readable half of the spec; if a field can change in
`src/sephiroth/contracts/` without anything failing, the spec is decoration.

Verifies AC-000-05 (`docs/specs/SPEC-000-spec-process.md`).
"""

import inspect
import json

import pytest
from pydantic import BaseModel

from sephiroth import contracts
from sephiroth.contracts import PUBLIC_MODELS

pytestmark = pytest.mark.contract


def _defined_models() -> set[type[BaseModel]]:
    """Every BaseModel subclass *defined in* the contracts package.

    Walks submodules rather than the package namespace so a model that exists
    but was never re-exported is still caught.
    """
    found: set[type[BaseModel]] = set()
    for _, module in inspect.getmembers(contracts, inspect.ismodule):
        if not (module.__name__ or "").startswith("sephiroth.contracts"):
            continue
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, BaseModel)
                and obj is not BaseModel
                and (obj.__module__ or "").startswith("sephiroth.contracts")
            ):
                found.add(obj)
    return found


def test_committed_schemas_match_models():
    """The whole point. Run `python scripts/export_contracts.py` to fix."""
    from scripts.export_contracts import export

    assert export(check_only=True) == 0, (
        "committed contract schemas are out of date — regenerate with "
        "`python scripts/export_contracts.py` and commit the result"
    )


def test_public_models_covers_every_defined_model():
    """A model missing from PUBLIC_MODELS gets no schema and no drift gate, so
    it could change freely. That would be a silent hole in the contract."""
    missing = _defined_models() - set(PUBLIC_MODELS)
    assert not missing, (
        f"models defined but absent from PUBLIC_MODELS: "
        f"{sorted(m.__name__ for m in missing)} — add them so their schema is "
        f"exported and drift-checked"
    )


def test_every_schema_file_is_valid_json():
    from scripts.export_contracts import CONTRACTS_DIR

    files = sorted(CONTRACTS_DIR.glob("*.schema.json"))
    assert files, "no contract schemas committed"
    for path in files:
        json.loads(path.read_text())


@pytest.mark.parametrize("model", PUBLIC_MODELS, ids=lambda m: m.__name__)
def test_model_forbids_unknown_fields(model):
    """`extra="forbid"` across the board.

    The TypedDict this replaces silently accepted and dropped a typo'd key.
    Forbidding extras is the concrete improvement, so it is asserted rather
    than assumed.
    """
    assert model.model_config.get("extra") == "forbid", f"{model.__name__} does not forbid extra fields"
