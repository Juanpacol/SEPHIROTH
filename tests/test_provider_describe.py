"""What a client says it is.

Three endpoints used to answer "which model is running" by reading
`settings.gemini_*`, whatever the configured provider was — so a stack serving
entirely from a local Ollama told its operator the data was going to Google.
`describe()` moves that answer to the only place that knows it: the client.

The conjunction rule for composites is the part worth guarding. A split client
exists precisely because its vision half is somewhere a local model cannot
reach, so reporting the composite as local would reintroduce the same untruth
under a new field name.

Verifies AC-022-02, AC-022-03 (docs/specs/SPEC-022-local-ai.md).
"""

import pytest

from sephiroth.models import FallbackLLMClient, GeminiClient, GroqClient, ProviderInfo
from sephiroth.models.base import _is_local_endpoint
from sephiroth.models.ollama import OllamaClient
from sephiroth.models.vision_split import VisionChatSplitClient


def _ollama(base_url="http://localhost:11434/v1", **kwargs):
    return OllamaClient(model="qwen2.5:14b", base_url=base_url, **kwargs)


def _gemini():
    return GeminiClient(api_key=None, model="gemini-flash-latest")


class TestEachClientReportsItself:
    def test_gemini_names_its_own_model_and_is_never_local(self):
        info = _gemini().describe()
        assert (info.provider, info.model, info.local) == ("gemini", "gemini-flash-latest", False)

    def test_ollama_names_its_own_model_not_geminis(self):
        """The defect this replaces: the status endpoint printed
        `settings.gemini_model` regardless of what was actually serving."""
        info = _ollama().describe()
        assert (info.provider, info.model) == ("ollama", "qwen2.5:14b")
        assert "gemini" not in info.model

    def test_groq_reports_its_endpoint_host_and_no_key(self):
        info = GroqClient(api_key="secret-value").describe()
        assert info.provider == "groq"
        assert info.endpoint == "api.groq.com"
        assert "secret-value" not in str(info.as_dict())


class TestLocality:
    @pytest.mark.parametrize(
        "url",
        [
            "http://localhost:11434/v1",
            "http://127.0.0.1:11434/v1",
            "http://ollama:11434/v1",  # a service name on a container network
            "http://192.168.1.40:11434/v1",
            "http://10.0.0.5:11434/v1",
            "http://clinic-gpu.local:11434/v1",
        ],
    )
    def test_addresses_inside_the_deployment_are_local(self, url):
        assert _is_local_endpoint(url) is True
        assert _ollama(base_url=url).describe().local is True

    @pytest.mark.parametrize(
        "url",
        [
            "https://openrouter.ai/api/v1",
            "https://api.example.com/v1",
            "https://8.8.8.8/v1",
        ],
    )
    def test_a_hosted_endpoint_is_not_local_even_through_the_ollama_client(self, url):
        """`ollama_base_url` is documented as retargetable at OpenRouter, so
        locality is a property of the instance, not of the class."""
        assert _is_local_endpoint(url) is False
        assert _ollama(base_url=url).describe().local is False

    @pytest.mark.parametrize("url", ["", "not a url", "http://"])
    def test_an_unreadable_endpoint_is_treated_as_remote(self, url):
        """Wrong in the safe direction: an address nobody can parse must not
        be assumed to be on this machine."""
        assert _is_local_endpoint(url) is False


class TestCompositesAreTheConjunction:
    def test_a_split_client_with_a_remote_vision_half_is_not_local(self):
        client = VisionChatSplitClient(chat_client=_ollama(), vision_client=_gemini())
        info = client.describe()

        assert info.provider == "split"
        assert info.local is False, "the vision half reaches Google; the deployment is not local"
        assert info.model == "qwen2.5:14b"
        assert info.vision_model == "gemini-flash-latest"

    def test_a_split_client_local_on_both_halves_is_local(self):
        client = VisionChatSplitClient(
            chat_client=_ollama(), vision_client=OllamaClient(model="llava", vision_model="llava")
        )
        assert client.describe().local is True

    def test_a_fallback_to_a_remote_secondary_is_not_local(self):
        """A local primary that reaches out to Groq under load is a deployment
        whose data leaves the building sometimes, which is not 'local'."""
        client = FallbackLLMClient(primary=_ollama(), secondary=GroqClient(api_key="k"))
        assert client.describe().local is False

    def test_a_composite_lists_its_parts(self):
        client = VisionChatSplitClient(chat_client=_ollama(), vision_client=_gemini())
        parts = client.describe().components

        assert [p.provider for p in parts] == ["ollama", "gemini"]
        assert all(isinstance(p, ProviderInfo) for p in parts)

    def test_a_leaf_lists_no_parts(self):
        assert _ollama().describe().components == ()
