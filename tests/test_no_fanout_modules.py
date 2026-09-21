"""SPEC-029 B-5 / AC-029-04: the multi-agent fan-out modules are deleted
outright, not left as unreachable dead code — `planner.py`/`router.py`
had exactly one internal caller (`executor.py`), so a strangler-fig shim
here would protect nothing (see SPEC-029 §10). Mirrors the dependency-
hygiene pattern `tests/test_no_langgraph.py` already uses for SPEC-003 B-5.
"""

import importlib

import pytest


@pytest.mark.parametrize("module_name", ["sephiroth.runtime.planner", "sephiroth.runtime.router"])
def test_fanout_module_no_longer_importable(module_name):
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module_name)
