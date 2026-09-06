"""Whether patient content may leave this deployment.

One function, called at each of the four call sites that are known to carry
patient-derived content into a model (SPEC-022 §6.5). It is deliberately not a
wrapper that inspects prompts: a query reading "56-year-old on warfarin with an
INR of 4.8, is the dose safe" carries no name and no identifier, and any
detector tuned to catch it also refuses the guideline lookups that are
legitimately fine to send. The reasoning is in
`docs/08-decisions/ADR-015-phi-egress-enumerated-seams.md`.

The gate is inert on a local provider. Nothing leaves the deployment, so there
is nothing to hold back — the switch is about egress, not about whether AI runs.
"""

from __future__ import annotations

from typing import Any

from .base import PHINotAllowedError

#: The call sites gated by `ai_allow_phi`. Enforced, not merely documented:
#: `tests/test_phi_egress_gate.py` walks the modules that reach an LLM client
#: and fails when one appears that is on neither this list nor the exempt one,
#: so a seam added later fails the build instead of shipping ungated.
PHI_SEAMS = (
    "sephiroth.runtime.executor",
    "intelligence.nlp.timeline_extractor",
    "intelligence.mcp.vision_server",
    "intelligence.mcp.patient_comms_server",
    # The streaming half of image description. It calls the client directly
    # rather than going through `vision_server`, which is precisely why the
    # enforcement test exists -- this seam was missing from the first draft of
    # this list and the test found it.
    "api.routers.medical",
)

#: Modules that handle patient content but are only reachable *through* a
#: gated seam, named here so the claim can be checked rather than assumed.
#: They are not gated again: a second check on the same path is noise, and
#: noise is what makes people stop reading the list.
PHI_DOWNSTREAM = {
    "sephiroth.verification.claims": "sephiroth.runtime.executor",
    "sephiroth.verification.combined": "sephiroth.runtime.executor",
    "sephiroth.verification.verify": "sephiroth.runtime.executor",
    "sephiroth.runtime.agent": "sephiroth.runtime.executor",
    "api.routers.patients": "intelligence.nlp.timeline_extractor",
    "api.routers.agents": "sephiroth.runtime.executor",
    "api.routers.approvals": "intelligence.mcp.patient_comms_server",
}

#: Modules that reach a model with no patient content, and why. Kept next to
#: the list above so the two are read together and an exemption has to be
#: written down rather than assumed.
PHI_EXEMPT = {
    "intelligence.evaluation.faithfulness": "synthetic corpus; no patient rows",
    "intelligence.evaluation.runner": "synthetic corpus; no patient rows",
    "intelligence.evaluation.abstention": "synthetic corpus; no patient rows",
    "api.main": "reads describe() for the startup log; sends nothing",
    "intelligence.agents": "shim package; re-exports the runtime",
    "intelligence.evaluation.abstention_replay": "synthetic corpus; no patient rows",
    "intelligence.evaluation.consultation_eval": "synthetic corpus; no patient rows",
    "intelligence.evaluation.imaging_eval": "synthetic fixtures; no patient rows",
    "intelligence.evaluation.imaging_loop": "synthetic fixtures; no patient rows",
    "api.fast_path": (
        "a guideline lookup is not patient content, and the moment a query "
        "carries patient context it is no longer the fast path"
    ),
    "sephiroth.runtime.intent_router": (
        "classifies the question's intent; runs before patient context is assembled and never receives it"
    ),
}


def phi_egress_allowed(client: Any) -> bool:
    """True when this client may receive patient content."""
    from core.config import settings  # noqa: PLC0415 -- platform/ is on PYTHONPATH at runtime

    if settings.ai_allow_phi:
        return True
    describe = getattr(client, "describe", None)
    if describe is None:
        # A client that cannot say where it sends things is treated as remote.
        # Being wrong in the safe direction is the whole point of the switch.
        return False
    return bool(describe().local)


def assert_phi_egress_allowed(client: Any, seam: str) -> None:
    """Raise before anything is sent, if patient content may not go there.

    `seam` names the call site, so the error a clinician's log carries says
    which capability was refused rather than only that something was.
    """
    if phi_egress_allowed(client):
        return
    info = client.describe()
    raise PHINotAllowedError(
        f"{seam} carries patient content and this deployment forbids sending it to "
        f"{info.provider} ({info.endpoint}). Set AI_ALLOW_PHI=true to permit it, or "
        f"run a local provider."
    )


__all__ = [
    "PHI_SEAMS",
    "PHI_DOWNSTREAM",
    "PHI_EXEMPT",
    "phi_egress_allowed",
    "assert_phi_egress_allowed",
]
