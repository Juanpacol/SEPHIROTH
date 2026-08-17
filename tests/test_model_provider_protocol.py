"""The `ModelProvider` contract — the interface every LLM backend satisfies.

`GeminiClient`, `GroqClient` and `FallbackLLMClient` shared method names by
convention only until this phase; nothing failed when they diverged. This
module makes the contract mechanical: every provider (real or fake) must
satisfy `isinstance(p, ModelProvider)`, and the load-bearing parameter names
every call site depends on are asserted by introspection rather than assumed.

Verifies AC-001-01, AC-001-02, AC-001-03
(`docs/specs/SPEC-001-model-provider.md`).
"""

import inspect

import pytest

from sephiroth.models import FallbackLLMClient, GeminiClient, GroqClient, ModelProvider
from tests.conftest import FakeLLMClient

pytestmark = pytest.mark.contract

PROVIDER_INSTANCES = [
    GeminiClient(api_key=None, model="gemini-flash-latest"),
    GroqClient(api_key=None),
    FallbackLLMClient(
        primary=GeminiClient(api_key=None, model="gemini-flash-latest"),
        secondary=GroqClient(api_key=None),
    ),
    FakeLLMClient(),
]
PROVIDER_IDS = ["gemini", "groq", "fallback", "fake"]


@pytest.mark.parametrize("provider", PROVIDER_INSTANCES, ids=PROVIDER_IDS)
def test_provider_satisfies_the_protocol(provider):
    """AC-001-01 — every provider, including the test double, is a ModelProvider."""
    assert isinstance(provider, ModelProvider), (
        f"{type(provider).__name__} does not structurally satisfy ModelProvider"
    )


@pytest.mark.parametrize("provider", PROVIDER_INSTANCES, ids=PROVIDER_IDS)
def test_provider_declares_capabilities_as_booleans(provider):
    assert isinstance(provider.supports_vision, bool)
    assert isinstance(provider.supports_tools, bool)


@pytest.mark.parametrize("provider", PROVIDER_INSTANCES, ids=PROVIDER_IDS)
def test_provider_exposes_a_model_string(provider):
    assert isinstance(provider.model, str)
    assert provider.model


def test_protocol_chat_signature_is_keyword_only_after_messages():
    """AC-001-02 — every `chat()` call site in the repo passes these by
    keyword; the Protocol marks them keyword-only so that guarantee is
    mechanical rather than a convention someone can quietly break."""
    signature = inspect.signature(ModelProvider.chat)
    params = signature.parameters

    assert list(params)[:2] == ["self", "messages"], (
        "the first two parameters must be self, messages (positional)"
    )
    keyword_only = [name for name, p in params.items() if p.kind is inspect.Parameter.KEYWORD_ONLY]
    assert keyword_only == ["system_prompt", "tools", "tool_executor", "think"], (
        f"expected exactly these keyword-only params, got {keyword_only}"
    )


def test_protocol_generate_json_first_params_are_prompt_then_schema():
    """AC-001-03 — `faithfulness.py` calls this positionally
    (`generate_json(answer, schema=...)`), `timeline_extractor.py` calls it by
    keyword. Both work only if `prompt, schema` stay positional-or-keyword, in
    that order."""
    signature = inspect.signature(ModelProvider.generate_json)
    params = list(signature.parameters.values())

    assert params[0].name == "self"
    assert params[1].name == "prompt"
    assert params[1].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert params[2].name == "schema"
    assert params[2].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD


def test_protocol_describe_image_signature():
    signature = inspect.signature(ModelProvider.describe_image)
    names = list(signature.parameters)
    assert names == ["self", "image_bytes", "mime_type", "prompt", "max_output_tokens"]


def test_protocol_health_takes_no_arguments():
    signature = inspect.signature(ModelProvider.health)
    assert list(signature.parameters) == ["self"]
