"""DEPRECATED — moved to `sephiroth.models.factory` in Phase 1.

This module re-exports for backward compatibility only. Removed in Phase 2
per the shim schedule in `docs/00-migration-charter.md` §3.

Do NOT `monkeypatch.setattr` this module's `_client`/`settings` — they are
copies of the bindings, not the ones `get_llm_client()` reads from its own
module globals. Patch `sephiroth.models.factory` directly (see
`tests/conftest.py::patch_llm_factory` and
`docs/specs/SPEC-001-model-provider.md` §10).
"""

from sephiroth.models.factory import get_llm_client, reset_llm_client

__all__ = ["get_llm_client", "reset_llm_client"]
