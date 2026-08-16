"""DEPRECATED — moved to `sephiroth.models.fallback` in Phase 1.

This module re-exports for backward compatibility only. Removed in Phase 2
per the shim schedule in `docs/00-migration-charter.md` §3. See
`docs/specs/SPEC-001-model-provider.md`.
"""

from sephiroth.models.base import ChatResult, LLMUnavailableError
from sephiroth.models.fallback import FallbackLLMClient
from sephiroth.models.gemini import GeminiClient

__all__ = ["ChatResult", "FallbackLLMClient", "GeminiClient", "LLMUnavailableError"]
