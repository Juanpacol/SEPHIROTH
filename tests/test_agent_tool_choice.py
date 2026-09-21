"""`Agent.run` maps `AgentCapability.require_tool_call` to the
`ModelProvider.chat(tool_choice=...)` a small local model needs to reliably
call its tool instead of answering from parametric memory and fabricating a
citation — see `AgentCapability.require_tool_call`'s docstring and
`OllamaClient.chat`'s module docstring for the incident this fixes.
"""

import pytest

from sephiroth.contracts import AgentCapability
from sephiroth.models import ChatResult
from sephiroth.runtime.agent import Agent, ToolCallOmittedError


class _CapturingClient:
    model = "fake"
    supports_vision = False
    supports_tools = True

    def __init__(self):
        self.last_kwargs = None

    async def chat(self, messages, **kwargs):
        self.last_kwargs = kwargs
        return ChatResult(content="ok", tool_calls=[], rounds=1, prompt_tokens=0, completion_tokens=0)


def _capability(*, require_tool_call: bool, tools: list[str]) -> AgentCapability:
    return AgentCapability(
        id="test-agent",
        node_name="test_agent",
        name="Test Agent",
        role_prompt="You are a test agent.",
        tools=tools,
        require_tool_call=require_tool_call,
    )


@pytest.mark.asyncio
async def test_require_tool_call_sets_tool_choice_required(monkeypatch):
    client = _CapturingClient()
    agent = Agent(_capability(require_tool_call=True, tools=["search_clinical_guidelines"]), client)

    class _FakeRegistry:
        async def load(self):
            return None

        def llm_tools(self, names):
            return [{"type": "function", "function": {"name": n}} for n in names]

        def system_prompt_summary(self, names):
            return ""

        def scoped_executor(self, names):
            async def _exec(name, args):
                return {}

            return _exec

    monkeypatch.setattr("sephiroth.runtime.agent.get_tool_runtime", lambda: _FakeRegistry())

    # `_CapturingClient` never returns a tool call, so this now also proves
    # the post-hoc `ToolCallOmittedError` check (see that class's docstring)
    # fires in exactly the case `tool_choice="required"` was meant to
    # prevent. `last_kwargs` is recorded before the raise.
    with pytest.raises(ToolCallOmittedError):
        await agent.run("What blood pressure reading is considered high?")
    assert client.last_kwargs["tool_choice"] == "required"


@pytest.mark.asyncio
async def test_require_tool_call_does_not_raise_when_a_tool_was_called(monkeypatch):
    class _ToolCallingClient(_CapturingClient):
        async def chat(self, messages, **kwargs):
            self.last_kwargs = kwargs
            return ChatResult(
                content="ok",
                tool_calls=[{"name": "search_clinical_guidelines", "arguments": {}}],
                rounds=1,
                prompt_tokens=0,
                completion_tokens=0,
            )

    client = _ToolCallingClient()
    agent = Agent(_capability(require_tool_call=True, tools=["search_clinical_guidelines"]), client)

    class _FakeRegistry:
        async def load(self):
            return None

        def llm_tools(self, names):
            return [{"type": "function", "function": {"name": n}} for n in names]

        def system_prompt_summary(self, names):
            return ""

        def scoped_executor(self, names):
            async def _exec(name, args):
                return {}

            return _exec

    monkeypatch.setattr("sephiroth.runtime.agent.get_tool_runtime", lambda: _FakeRegistry())

    result = await agent.run("What blood pressure reading is considered high?")
    assert result.tool_calls


@pytest.mark.asyncio
async def test_require_tool_call_false_leaves_tool_choice_unset(monkeypatch):
    client = _CapturingClient()
    agent = Agent(_capability(require_tool_call=False, tools=["search_clinical_guidelines"]), client)

    class _FakeRegistry:
        async def load(self):
            return None

        def llm_tools(self, names):
            return [{"type": "function", "function": {"name": n}} for n in names]

        def system_prompt_summary(self, names):
            return ""

        def scoped_executor(self, names):
            async def _exec(name, args):
                return {}

            return _exec

    monkeypatch.setattr("sephiroth.runtime.agent.get_tool_runtime", lambda: _FakeRegistry())

    await agent.run("hello")
    assert client.last_kwargs["tool_choice"] is None


@pytest.mark.asyncio
async def test_require_tool_call_with_no_tools_leaves_tool_choice_unset(monkeypatch):
    """A capability with no tools at all (e.g. the laboratory agent) never
    forces a tool call regardless of the flag — there's nothing to call."""
    client = _CapturingClient()
    agent = Agent(_capability(require_tool_call=True, tools=[]), client)

    class _FakeRegistry:
        async def load(self):
            return None

    monkeypatch.setattr("sephiroth.runtime.agent.get_tool_runtime", lambda: _FakeRegistry())

    await agent.run("hello")
    assert client.last_kwargs["tool_choice"] is None
