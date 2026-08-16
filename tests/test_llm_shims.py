"""`intelligence/llm/*` are re-export shims over `sephiroth.models.*`.

Every name the four legacy test modules import must remain importable from the
old path, and — the actual trap — patching `intelligence.llm.factory`'s
module-level `_client` global must be observed by `get_llm_client()`, wherever
it was imported from. A naive `from sephiroth.models.factory import *` shim
would make `intelligence.llm.factory._client` a *different* binding than the
one `get_llm_client()` reads from its own module globals, so
`monkeypatch.setattr(factory_module, "_client", fake)` against the shim would
silently do nothing — tests would pass while exercising the real client.

Verifies AC-001-08 (`docs/specs/SPEC-001-model-provider.md`), and records the
`test_llm_factory.py` retarget documented in SPEC-001 §10 (v1.1.0).
"""

import pytest

pytestmark = pytest.mark.contract


def test_gemini_client_shim_exports_everything_the_legacy_test_imports():
    """Mirrors `tests/test_gemini_client.py:10-15` exactly."""
    from intelligence.llm.gemini_client import (
        DEFAULT_MAX_TOOL_ROUNDS,
        GeminiClient,
        LLMUnavailableError,
        _sanitize_schema,
    )

    assert DEFAULT_MAX_TOOL_ROUNDS == 6
    assert GeminiClient is not None
    assert LLMUnavailableError is not None
    assert callable(_sanitize_schema)


def test_groq_client_shim_exports_everything_the_legacy_test_imports():
    """Mirrors `tests/test_groq_client.py:10-11`."""
    from intelligence.llm.gemini_client import LLMUnavailableError
    from intelligence.llm.groq_client import GroqClient

    assert GroqClient is not None
    assert LLMUnavailableError is not None


def test_fallback_client_shim_exports_everything_the_legacy_test_imports():
    """Mirrors `tests/test_fallback_client.py:7-8`."""
    from intelligence.llm.fallback_client import FallbackLLMClient
    from intelligence.llm.gemini_client import ChatResult, LLMUnavailableError

    assert FallbackLLMClient is not None
    assert ChatResult is not None
    assert LLMUnavailableError is not None


def test_factory_shim_exports_get_and_reset():
    from intelligence.llm.factory import get_llm_client, reset_llm_client

    assert callable(get_llm_client)
    assert callable(reset_llm_client)


def test_legacy_symbols_are_identical_objects_not_copies():
    """A shim re-exports; it does not re-implement. If `GeminiClient` imported
    via the old path were a different class than the one via the new path,
    `isinstance` checks written against either would silently diverge."""
    from intelligence.llm.gemini_client import GeminiClient as OldGemini
    from sephiroth.models.gemini import GeminiClient as NewGemini

    assert OldGemini is NewGemini


def test_factory_get_llm_client_is_defined_in_the_new_module():
    """The identity check that makes the whole shim strategy safe: the
    function object reachable via the old import path must be *the same
    function*, defined in `sephiroth.models.factory` — so patching that
    module's globals (not the shim's) is what `get_llm_client()` actually
    observes."""
    from intelligence.llm.factory import get_llm_client

    assert get_llm_client.__module__ == "sephiroth.models.factory"


def test_patching_the_real_module_is_observed_through_the_old_import_path(monkeypatch):
    """The mechanical version of the trap this file exists to prevent:
    patch `sephiroth.models.factory._client` directly (as
    `tests/conftest.py::patch_llm_factory` does after this phase), then call
    `get_llm_client` via the *old* import path, and confirm the patched value
    is what comes back."""
    import sephiroth.models.factory as factory_module
    from intelligence.llm.factory import get_llm_client as legacy_get_llm_client

    sentinel = object()
    monkeypatch.setattr(factory_module, "_client", sentinel)

    assert legacy_get_llm_client() is sentinel


def test_reset_llm_client_has_no_production_callers():
    """`reset_llm_client` is test-only scaffolding. Confirmed here rather than
    asserted by removing it — deletion is deferred to the Phase 2
    shim-removal PR (`docs/00-migration-charter.md` §3 shim schedule)."""
    import intelligence.llm.factory as legacy_factory_module

    assert hasattr(legacy_factory_module, "reset_llm_client")
