"""DEPRECATED — moved to `sephiroth.models.gemini` in Phase 1.

This module re-exports for backward compatibility only. Removed in Phase 2
per the shim schedule in `docs/00-migration-charter.md` §3. See
`docs/specs/SPEC-001-model-provider.md`.
"""

from sephiroth.models.base import ChatResult, LLMUnavailableError
from sephiroth.models.gemini import DEFAULT_MAX_TOOL_ROUNDS, GeminiClient, _sanitize_schema

__all__ = [
    "ChatResult",
    "DEFAULT_MAX_TOOL_ROUNDS",
    "GeminiClient",
    "LLMUnavailableError",
    "_sanitize_schema",
]
