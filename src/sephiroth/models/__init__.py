"""Model providers — the `ModelProvider` contract and its implementations.

See `docs/specs/SPEC-001-model-provider.md`.
"""

from .base import ChatResult, LLMUnavailableError, ModelProvider, ToolExecutor
from .factory import get_llm_client, reset_llm_client
from .fallback import FallbackLLMClient
from .gemini import GeminiClient
from .groq import GroqClient, GroqToolUseFailedError
from .ollama import OllamaClient
from .vision_split import VisionChatSplitClient

__all__ = [
    "ChatResult",
    "FallbackLLMClient",
    "GeminiClient",
    "GroqClient",
    "GroqToolUseFailedError",
    "LLMUnavailableError",
    "ModelProvider",
    "OllamaClient",
    "ToolExecutor",
    "VisionChatSplitClient",
    "get_llm_client",
    "reset_llm_client",
]
