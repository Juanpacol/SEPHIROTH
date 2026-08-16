"""DEPRECATED — moved to `sephiroth.models.groq` in Phase 1.

This module re-exports for backward compatibility only. Removed in Phase 2
per the shim schedule in `docs/00-migration-charter.md` §3. See
`docs/specs/SPEC-001-model-provider.md`.
"""

from sephiroth.models.base import LLMUnavailableError
from sephiroth.models.groq import DEFAULT_MAX_TOOL_ROUNDS, GroqClient, GroqToolUseFailedError

__all__ = ["DEFAULT_MAX_TOOL_ROUNDS", "GroqClient", "GroqToolUseFailedError", "LLMUnavailableError"]
