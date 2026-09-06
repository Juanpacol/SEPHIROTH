"""Whether patient content may leave the deployment.

`ai_allow_phi` is off by default and inert while the provider is local — the
switch is about egress, not about whether AI runs. It bites exactly when
someone points the stack at a remote model without deciding, separately, that
patient data may go there.

The last class is the one that keeps this honest over time. The gate is an
enumerated list of call sites rather than a payload classifier (ADR-015),
because a query reading "56-year-old on warfarin, INR 4.8, is the dose safe"
carries no name and no identifier and would slip past any detector tuned not to
refuse ordinary clinical language. An enumerated list's weakness is a seam
added later and forgotten — which is a structural question a machine can
actually answer, unlike "does this string contain PHI".

Verifies AC-022-05 (docs/specs/SPEC-022-local-ai.md).
"""

import ast
import pathlib

import pytest

from sephiroth.models import PHINotAllowedError, ProviderInfo
from sephiroth.models.egress import (
    PHI_DOWNSTREAM,
    PHI_EXEMPT,
    PHI_SEAMS,
    assert_phi_egress_allowed,
    phi_egress_allowed,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


class _Client:
    model = "some-model"

    def __init__(self, local: bool):
        self._local = local

    def describe(self):
        return ProviderInfo(
            provider="ollama" if self._local else "gemini",
            model=self.model,
            local=self._local,
            endpoint="localhost" if self._local else "generativelanguage.googleapis.com",
        )


@pytest.fixture
def allow_phi(monkeypatch):
    def _set(value: bool):
        import core.config as config_module
        from core.config import Settings

        monkeypatch.setattr(
            config_module,
            "settings",
            Settings(_env_file=None, environment="development", ai_allow_phi=value),
        )

    return _set


class TestTheSwitch:
    def test_a_local_provider_is_allowed_with_the_switch_off(self, allow_phi):
        """Nothing leaves the deployment, so there is nothing to hold back.
        A flag that disabled local AI too would just get turned on."""
        allow_phi(False)
        assert phi_egress_allowed(_Client(local=True)) is True

    def test_a_remote_provider_is_refused_with_the_switch_off(self, allow_phi):
        allow_phi(False)
        assert phi_egress_allowed(_Client(local=False)) is False

    def test_a_remote_provider_is_allowed_once_the_switch_is_on(self, allow_phi):
        allow_phi(True)
        assert phi_egress_allowed(_Client(local=False)) is True

    def test_a_client_that_cannot_say_where_it_sends_things_is_treated_as_remote(self, allow_phi):
        """Wrong in the safe direction, deliberately."""
        allow_phi(False)
        assert phi_egress_allowed(object()) is False

    def test_the_refusal_names_the_seam_and_the_destination(self, allow_phi):
        allow_phi(False)
        with pytest.raises(PHINotAllowedError) as exc:
            assert_phi_egress_allowed(_Client(local=False), "medical image description")

        message = str(exc.value)
        assert "medical image description" in message
        assert "gemini" in message
        assert "AI_ALLOW_PHI" in message

    def test_the_refusal_degrades_like_any_other_outage(self):
        """It subclasses `LLMUnavailableError` so every seam's existing
        degrade path catches it, instead of each site growing a second
        `except` that someone will forget."""
        from sephiroth.models import LLMUnavailableError

        assert issubclass(PHINotAllowedError, LLMUnavailableError)


@pytest.mark.asyncio
class TestEachSeamRefusesBeforeSending:
    async def test_timeline_extraction_falls_back_to_the_lexicon(self, allow_phi):
        from intelligence.nlp.timeline_extractor import extract_events

        allow_phi(False)

        class _NeverCalled(_Client):
            async def generate_json(self, *args, **kwargs):
                raise AssertionError("the note reached the model")

        events = await extract_events(_NeverCalled(local=False), "Started metformin 500mg.", "2026-09-06")

        # Degraded, not failed: the deterministic lexicon still produces a
        # timeline, which is the same thing an outage produces.
        assert isinstance(events, list)

    async def test_image_description_reports_unavailable_rather_than_raising(
        self, allow_phi, tmp_path, monkeypatch
    ):
        from intelligence.mcp import vision_server

        allow_phi(False)
        image = tmp_path / "cxr.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)

        class _NeverCalled(_Client):
            async def describe_image(self, **kwargs):
                raise AssertionError("the image reached the model")

        monkeypatch.setattr(vision_server, "get_llm_client", lambda: _NeverCalled(local=False))
        result = await vision_server.describe_medical_image(str(image))

        assert result["status"] == "unavailable"
        assert result["requires_professional_review"] is True

    async def test_a_consultation_refuses_before_the_first_model_call(self, allow_phi):
        from sephiroth.runtime.executor import run_consultation

        allow_phi(False)

        class _NeverCalled(_Client):
            async def chat(self, *args, **kwargs):
                raise AssertionError("the query reached the model")

            async def generate_json(self, *args, **kwargs):
                raise AssertionError("the query reached the model")

        with pytest.raises(PHINotAllowedError):
            await run_consultation(_NeverCalled(local=False), "Is this warfarin dose safe?", "P001")

    async def test_a_local_provider_runs_the_consultation_normally(self, allow_phi):
        """AC-022-05's other half: the flag must not change anything at all
        when nothing is leaving."""
        from sephiroth.models.egress import phi_egress_allowed

        allow_phi(False)
        assert phi_egress_allowed(_Client(local=True)) is True


class TestTheSeamListIsEnforcedNotJustWritten:
    """A list of gated call sites is only worth what its maintenance is worth.

    "Does this module reach an LLM client" is a structural question with an
    exact answer, so it is checked rather than trusted. A new seam fails here
    instead of shipping ungated.
    """

    #: Where a model client can be obtained. A module that names one of these
    #: is reaching a model, whatever it does with it.
    _ENTRY_POINTS = ("get_llm_client", "ModelProvider")

    #: Directories that are application code rather than tests or tooling.
    _ROOTS = ("src/sephiroth", "intelligence", "platform/api", "data")

    def _modules_reaching_a_model(self):
        found = set()
        for root in self._ROOTS:
            for path in (REPO_ROOT / root).rglob("*.py"):
                if "__pycache__" in path.parts:
                    continue
                try:
                    tree = ast.parse(path.read_text())
                except SyntaxError:  # pragma: no cover - would fail the build elsewhere
                    continue
                names = {
                    node.id if isinstance(node, ast.Name) else node.attr
                    for node in ast.walk(tree)
                    if isinstance(node, (ast.Name, ast.Attribute))
                }
                if names & set(self._ENTRY_POINTS):
                    found.add(self._module_name(path))
        return found

    @staticmethod
    def _module_name(path: pathlib.Path) -> str:
        rel = path.relative_to(REPO_ROOT).with_suffix("")
        parts = list(rel.parts)
        for prefix in (["src"], ["platform"]):
            if parts[: len(prefix)] == prefix:
                parts = parts[len(prefix) :]
        if parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts)

    def test_every_module_that_reaches_a_model_is_gated_or_explicitly_exempt(self):
        reaching = self._modules_reaching_a_model()
        accounted = set(PHI_SEAMS) | set(PHI_EXEMPT) | set(PHI_DOWNSTREAM)

        # Plumbing: the models package *is* the clients, and the protocol is
        # the type they satisfy. Nothing there carries content of its own.
        plumbing = {m for m in reaching if m.startswith("sephiroth.models")}

        unaccounted = reaching - accounted - plumbing
        assert not unaccounted, (
            "these modules reach an LLM client but are on none of PHI_SEAMS, PHI_DOWNSTREAM or "
            f"PHI_EXEMPT: {sorted(unaccounted)}. Gate it, name the gated seam it sits behind, or "
            "record why its content is not patient-derived "
            "(docs/08-decisions/ADR-015-phi-egress-enumerated-seams.md)."
        )

    def test_every_declared_seam_actually_calls_the_gate(self):
        """The list must not drift the other way either: a module named as a
        seam that stopped enforcing is worse than one that was never listed,
        because the list says it is covered."""
        missing = []
        for module in PHI_SEAMS:
            path = self._path_for(module)
            assert path is not None, f"PHI_SEAMS names a module that does not exist: {module}"
            if "assert_phi_egress_allowed" not in path.read_text():
                missing.append(module)
        assert not missing, f"declared PHI seams that no longer call the gate: {missing}"

    @staticmethod
    def _path_for(module: str):
        rel = pathlib.Path(*module.split("."))
        for prefix in ("src", "platform", "."):
            candidate = REPO_ROOT / prefix / rel.with_suffix(".py")
            if candidate.exists():
                return candidate
            package = REPO_ROOT / prefix / rel / "__init__.py"
            if package.exists():
                return package
        return None
