"""
Clinical agents — thin wrappers over `sephiroth.runtime.Agent`.

Moved to `sephiroth.runtime` in Phase 3
(`docs/specs/SPEC-003-agent-runtime.md`): each class here used to carry its
own `name`/`role_prompt`/`allowed_tools` class attributes; now it's a
one-line adapter binding `Agent` to a capability record, kept only so
`platform/api/routers/agents.py::/ask` and any direct importer can keep doing
`RadiologyAgent(client)`.
"""

from sephiroth.models import ModelProvider
from sephiroth.runtime.agent import Agent
from sephiroth.runtime.registry import COORDINATOR, DRUG_SAFETY, EVIDENCE, LABORATORY, RADIOLOGY

MCPAgent = Agent


class RadiologyAgent(Agent):
    def __init__(self, client: ModelProvider):
        super().__init__(RADIOLOGY, client)


class LabAgent(Agent):
    def __init__(self, client: ModelProvider):
        super().__init__(LABORATORY, client)


class DrugSafetyAgent(Agent):
    def __init__(self, client: ModelProvider):
        super().__init__(DRUG_SAFETY, client)


class EvidenceAgent(Agent):
    def __init__(self, client: ModelProvider):
        super().__init__(EVIDENCE, client)


class ClinicalCoordinator(Agent):
    def __init__(self, client: ModelProvider):
        super().__init__(COORDINATOR, client)


__all__ = [
    "MCPAgent",
    "ClinicalCoordinator",
    "RadiologyAgent",
    "LabAgent",
    "DrugSafetyAgent",
    "EvidenceAgent",
]
