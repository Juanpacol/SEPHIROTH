"""Citation Guard unit tests — the anti-hallucination layer."""

from intelligence.agents.citation_guard import audit, collect_allowed_citations, sanitize

TOOL_CALLS = [
    {
        "agent": "evidence",
        "name": "search_clinical_guidelines",
        "arguments": {"query": "hf"},
        "result": {
            "results": [
                {
                    "content": "GDMT includes ARNI...",
                    "source": "AHA/ACC/HFSA Heart Failure Guideline",
                    "citation": "Management of Heart Failure, AHA/ACC/HFSA, 2022",
                    "metadata": {"organization": "AHA/ACC/HFSA", "year": 2022},
                }
            ]
        },
    },
    {
        "agent": "evidence",
        "name": "search_pubmed",
        "arguments": {"query": "sglt2"},
        "result": {"results": [{"pmid": "12345678", "title": "SGLT2i in HFrEF"}]},
    },
]


def test_collect_allowed_includes_citations_and_tool_names():
    allowed = collect_allowed_citations(TOOL_CALLS)
    assert "Management of Heart Failure, AHA/ACC/HFSA, 2022" in allowed
    assert "search_clinical_guidelines" in allowed
    assert "PMID:12345678" in allowed


def test_verified_citation_passes():
    answer = "ARNI is recommended [AHA/ACC/HFSA Heart Failure Guideline, 2022]."
    report = audit(answer, TOOL_CALLS)
    assert report.fabricated == []
    assert len(report.verified) == 1


def test_fabricated_citation_flagged_and_stripped():
    answer = "Beta-blockers reduce mortality [UpToDate Clinical Reference]."
    report = audit(answer, TOOL_CALLS)
    assert report.verified == []
    assert report.fabricated == ["UpToDate Clinical Reference"]
    assert "[unverified — removed]" in sanitize(answer, report)
    assert "UpToDate" not in sanitize(answer, report)


def test_pmid_citation_verified():
    answer = "SGLT2 inhibitors improve outcomes (PMID: 12345678)."
    report = audit(answer, TOOL_CALLS)
    assert "PMID:12345678" in report.verified


def test_unknown_pmid_fabricated():
    answer = "Shown in a large RCT (PMID: 99999999)."
    report = audit(answer, TOOL_CALLS)
    assert "PMID:99999999" in report.fabricated


def test_tool_name_citation_verified():
    answer = "A major interaction was found [search_clinical_guidelines]."
    report = audit(answer, TOOL_CALLS)
    assert report.fabricated == []


def test_numeric_refs_and_plain_text_ignored():
    answer = "Standard therapy applies [1]. No citations here."
    report = audit(answer, TOOL_CALLS)
    assert report.total_checked == 0


def test_markdown_link_stripped():
    answer = "See [UpToDate](https://www.uptodate.com) for details."
    report = audit(answer, TOOL_CALLS)
    assert "UpToDate" in report.fabricated
    sanitized = sanitize(answer, report)
    assert "https://www.uptodate.com" not in sanitized
