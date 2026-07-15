"""Local LLM layer — Ollama client with MCP tool-calling support."""

from .ollama_client import ChatResult, OllamaClient

__all__ = ["OllamaClient", "ChatResult"]
