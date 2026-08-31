"""`harvest_evidence` — normalizes tool call results into `EvidenceRecord`s."""

from datetime import datetime, timezone

from sephiroth.contracts import RetrievalMethod, SourceType, ToolCall
from sephiroth.verification.evidence import harvest_evidence


def _tool_call(result):
    return ToolCall(
        id="tc1",
        tool="search_clinical_guidelines",
        agent="evidence",
        result=result,
        timestamp=datetime.now(timezone.utc),
    )


def _drug_tool_call(result):
    return ToolCall(
        id="tc2",
        tool="check_drug_interactions",
        agent="drug_safety",
        result=result,
        timestamp=datetime.now(timezone.utc),
    )


# `check_drug_interactions` returns rows under `interactions`, and its fields
# match neither `_CONTENT_KEYS` nor any citation key. Reading only `results`
# left drug-safety runs with zero evidence — every claim UNKNOWN, and the
# answer/abstain outcome decided by whether extraction returned any claims.
DRUG_RESULT = {
    "medications_checked": ["warfarin", "ibuprofen"],
    "interactions_found": 1,
    "interactions": [
        {
            "pair": ["ibuprofen", "warfarin"],
            "severity": "major",
            "effect": "NSAIDs increase bleeding risk and may raise INR.",
            "recommendation": "Prefer acetaminophen for analgesia in anticoagulated patients.",
        }
    ],
    "disclaimer": "Screening against a curated table only.",
}


def test_drug_interactions_become_evidence():
    records = harvest_evidence([_drug_tool_call(DRUG_RESULT)])

    assert len(records) == 1
    assert records[0].originating_agent == "drug_safety"


def test_drug_interaction_evidence_carries_verifiable_content():
    # Empty content is not merely cosmetic: `_overlap_supports` skips
    # content-less evidence, which downgrades every claim grounded on it.
    content = harvest_evidence([_drug_tool_call(DRUG_RESULT)])[0].content

    assert content
    for expected in ("ibuprofen", "warfarin", "major", "bleeding risk", "acetaminophen"):
        assert expected in content


def test_drug_interaction_without_source_falls_back_to_the_table_label():
    record = harvest_evidence([_drug_tool_call(DRUG_RESULT)])[0]
    assert record.source == "Curated drug-interaction table"


def test_ddinter_sourced_interaction_keeps_its_own_provenance():
    result = {"interactions": [{"pair": ["a", "b"], "severity": "moderate", "source": "DDInter 2.0"}]}
    assert harvest_evidence([_drug_tool_call(result)])[0].source == "DDInter 2.0"


def test_model_generated_tool_output_is_never_treated_as_evidence():
    # Imaging `findings` and vision `description` are the model's own output;
    # admitting them would let an answer verify itself.
    imaging = {"status": "ok", "findings": [{"label": "abnormal", "probability": 0.91}]}
    vision = {"status": "ok", "description": "There is a left-basilar opacity."}

    assert harvest_evidence([_tool_call(imaging)]) == []
    assert harvest_evidence([_tool_call(vision)]) == []


def test_harvests_guideline_content():
    result = {
        "results": [
            {
                "id": "ada-2024-hba1c",
                "content": "An A1C goal of <7% is appropriate.",
                "source": "ADA Standards of Care in Diabetes",
                "citation": "ADA Standards of Care in Diabetes, 2024",
                "score": 1.15,
            }
        ]
    }
    records = harvest_evidence([_tool_call(result)])

    assert len(records) == 1
    record = records[0]
    assert record.content == "An A1C goal of <7% is appropriate."
    assert record.source_type is SourceType.GUIDELINE
    assert record.retrieval_method is RetrievalMethod.TOOL
    assert record.originating_agent == "evidence"
    assert record.citation.label == "ADA Standards of Care in Diabetes, 2024"
    # Score exceeding 1.0 (RRF-fused scores can) must be clamped for the
    # bounded `relevance` field.
    assert record.relevance == 1.0


def test_pubmed_result_has_no_content_but_still_becomes_evidence():
    result = {"results": [{"pmid": "12345", "title": "A study", "journal": "NEJM", "citation": "PMID:12345"}]}
    records = harvest_evidence([_tool_call(result)])

    assert len(records) == 1
    assert records[0].content == ""
    assert records[0].source_type is SourceType.LITERATURE


def test_non_list_or_missing_results_yields_no_evidence():
    assert harvest_evidence([_tool_call({"error": "not found"})]) == []
    assert harvest_evidence([_tool_call(None)]) == []
    assert harvest_evidence([_tool_call({"results": "not a list"})]) == []


def test_non_dict_items_in_results_are_skipped():
    records = harvest_evidence([_tool_call({"results": ["not a dict", 123]})])
    assert records == []
