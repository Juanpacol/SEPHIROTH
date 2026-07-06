"""Local LLM layer — Ollama client with MCP tool-calling support."""

from .ollama_client import OllamaClient, ChatResult

__all__ = ["OllamaClient", "ChatResult"]
