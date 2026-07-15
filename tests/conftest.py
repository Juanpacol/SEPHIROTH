"""Shared fixtures: an isolated async SQLite database per test, and a
scripted OllamaClient double so agent/workflow tests never need a live
Ollama server."""

from typing import Any, Dict, List, Optional, Tuple

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from data.schemas import Base
from intelligence.llm.ollama_client import ChatResult


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def anyio_backend():
    return "asyncio"


class FakeOllamaClient:
    """Scripted double for `OllamaClient` — the only LLM touchpoint the
    whole agent stack uses (`base.py::OllamaMCPAgent.run` calls `.chat()`
    exclusively).

    `scripts` maps a substring found in the agent's `system_prompt` (each
    agent's `role_prompt` is distinct, e.g. "clinical evidence specialist")
    to an ordered list of steps:
      ("tool", name, args) — awaits the REAL `tool_executor`, so the MCP
          registry / rag_server / RAGPipeline code runs for real and any
          resulting tool_calls carry genuine citations.
      ("answer", text) — the final assistant content for that call.

    A system_prompt matching no key falls back to `default_script`.
    """

    model = "fake-model"

    def __init__(
        self,
        scripts: Optional[Dict[str, List[Tuple]]] = None,
        default_script: Optional[List[Tuple]] = None,
        json_payloads: Optional[List[Dict[str, Any]]] = None,
    ):
        self.scripts = scripts or {}
        self.default_script = default_script or [("answer", "")]
        self.json_payloads = list(json_payloads or [])
        self.chat_calls: List[Dict[str, Any]] = []

    def _script_for(self, system_prompt: Optional[str]) -> List[Tuple]:
        system_prompt = system_prompt or ""
        for key, script in self.scripts.items():
            if key in system_prompt:
                return script
        return self.default_script

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_executor=None,
        think: Optional[bool] = False,
    ) -> ChatResult:
        self.chat_calls.append({"system_prompt": system_prompt, "messages": messages})
        script = self._script_for(system_prompt)
        executed: List[Dict[str, Any]] = []
        content = ""
        for step in script:
            kind = step[0]
            if kind == "tool":
                _, name, args = step
                result = await tool_executor(name, args) if tool_executor else None
                executed.append({"name": name, "arguments": args, "result": result})
            elif kind == "answer":
                content = step[1]
        return ChatResult(content=content, tool_calls=executed, rounds=max(len(script), 1))

    async def generate_json(
        self, prompt: str, schema: Dict[str, Any], system_prompt: Optional[str] = None
    ) -> Any:
        if self.json_payloads:
            return self.json_payloads.pop(0)
        return {}

    async def health(self) -> bool:
        return True


@pytest.fixture
def fake_ollama_client():
    """A bare FakeOllamaClient with no scripts — override `.scripts` /
    `.default_script` per test as needed."""
    return FakeOllamaClient()
