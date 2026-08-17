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
