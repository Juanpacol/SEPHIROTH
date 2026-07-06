"""
Clinical agents — Ollama-powered specialists with MCP tools.

Each specialist maps to one MCP server; the ClinicalCoordinator synthesizes
their outputs (see workflow.py for the LangGraph orchestration).
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List

from .base import OllamaMCPAgent


@dataclass
class AgentState:
    """State passed between clinical agents in the LangGraph workflow."""

    patient_id: str = ""
    query: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    agent_outputs: Dict[str, str] = field(default_factory=dict)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    final_answer: str = ""


class RadiologyAgent(OllamaMCPAgent):
    """Analyzes medical images through the imaging + vision MCP servers."""

    name = "radiology"
    role_prompt = (
        "You are the radiology specialist. When the patient context includes "
        "an image_path, FIRST call describe_medical_image to get an AI visual "
        "description, then reason over that description together with any "
        "structured analysis. Report findings with modality, location, and "
        "confidence. Clearly attribute what came from the vision model versus "
        "your clinical reasoning. Flag anything requiring urgent review."
    )
    allowed_tools = [
        "inspect_medical_image",
        "analyze_medical_image",
        "describe_medical_image",
    ]


class LabAgent(OllamaMCPAgent):
    """Interprets laboratory values present in the patient context."""

    name = "laboratory"
    role_prompt = (
        "You are the laboratory medicine specialist. Interpret the lab values "
        "in the patient context: flag values outside reference ranges, "
        "describe clinical significance, and note trends when prior values "
        "are available. Do not invent values that are not provided."
    )
    allowed_tools = None  # works purely from the provided patient context


class DrugSafetyAgent(OllamaMCPAgent):
    """Screens medication lists for interactions via the drug-safety server."""

    name = "drug-safety"
    role_prompt = (
        "You are the medication safety specialist. Screen the patient's "
        "medication list for drug-drug interactions and summarize severity "
        "and recommended actions."
    )
    allowed_tools = ["check_drug_interactions"]


class EvidenceAgent(OllamaMCPAgent):
    """Retrieves clinical guidelines and PubMed evidence — always cited."""

    name = "evidence"
    role_prompt = (
        "You are the clinical evidence specialist. Ground every statement in "
        "retrieved guidelines or PubMed results. ALWAYS include the citation "
        "for each claim in the form [Source, Year] or [PMID:xxxx]. If no "
        "evidence is found, say so explicitly — never fabricate a citation."
    )
    allowed_tools = ["search_clinical_guidelines", "search_pubmed"]


class ClinicalCoordinator(OllamaMCPAgent):
    """Synthesizes the specialists' outputs into one clinical summary."""

    name = "coordinator"
    role_prompt = (
        "You are the coordinating physician-assistant. You receive analyses "
        "from specialist agents (radiology, laboratory, drug safety, "
        "evidence). Synthesize them into a single structured response with "
        "sections: Summary, Findings, Evidence (with citations), "
        "Recommendations. End with: 'This is decision support, not a "
        "diagnosis — professional review required.'"
    )
    allowed_tools = ["extract_medical_entities", "summarize_clinical_note"]


__all__ = [
    "AgentState",
    "OllamaMCPAgent",
    "ClinicalCoordinator",
    "RadiologyAgent",
    "LabAgent",
    "DrugSafetyAgent",
    "EvidenceAgent",
]
