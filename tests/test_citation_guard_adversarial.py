"""Adversarial coverage for the Citation Guard — the anti-hallucination
firewall that strips citations no tool result actually returned."""

from intelligence.agents.citation_guard import audit, collect_allowed_citations, sanitize

TOOL_CALLS = [
    {
        "name": "search_clinical_guidelines",
        "arguments": {"query": "diabetes"},
        "result": {
            "results": [
                {
                    "citation": "Glycemic Targets, American Diabetes Association, 2024",
                    "source": "ADA Standards of Care",
                }
            ]
        },
    },
    {
        "name": "search_pubmed",
        "arguments": {"query": "diabetes"},
        "result": {"results": [{"pmid": "12345678", "title": "A real trial"}]},
    },
]


def test_fabricated_source_is_flagged():
    answer = "Statins reduce risk [UpToDate]."
    report = audit(answer, TOOL_CALLS)
    assert "UpToDate" in report.fabricated
    assert not report.verified


def test_verified_pmid_from_tool_result():
    answer = "See the trial [PMID:12345678]."
    report = audit(answer, TOOL_CALLS)
    assert "PMID:12345678" in report.verified


def test_fabricated_pmid_not_in_tool_result():
    answer = "See the trial [PMID:99999999]."
    report = audit(answer, TOOL_CALLS)
    assert "PMID:99999999" in report.fabricated


def test_markdown_link_sanitize_replaces_fabricated():
    answer = "Evidence [Fake Journal](https://example.com/fake) supports this."
    report = audit(answer, TOOL_CALLS)
    assert "Fake Journal" in report.fabricated
    cleaned = sanitize(answer, report)
    assert "example.com" not in cleaned
    assert "[unverified — removed]" in cleaned


def test_bare_bracket_sanitize_replaces_fabricated():
    answer = "This is backed by [Totally Made Up Journal]."
    report = audit(answer, TOOL_CALLS)
    cleaned = sanitize(answer, report)
    assert "[unverified — removed]" in cleaned
    assert "Totally Made Up Journal" not in cleaned


def test_verified_citation_survives_sanitize_unchanged():
    answer = "Per [Glycemic Targets, American Diabetes Association, 2024], target A1C is <7%."
    report = audit(answer, TOOL_CALLS)
    cleaned = sanitize(answer, report)
    assert cleaned == answer


def test_fifty_percent_token_overlap_boundary_verified():
    # 2 of 4 candidate tokens ("glycemic", "targets") match the allowed
    # citation's tokens — exactly the >=0.5 boundary.
    answer = "See [Glycemic Targets XYZ ABC]."
    report = audit(answer, TOOL_CALLS)
    assert "Glycemic Targets XYZ ABC" in report.verified


def test_low_token_overlap_is_fabricated():
    answer = "See [Completely Unrelated Nonsense Reference]."
    report = audit(answer, TOOL_CALLS)
    assert "Completely Unrelated Nonsense Reference" in report.fabricated


def test_duplicate_citations_deduped_in_report():
    answer = "[UpToDate] said so. Also, [UpToDate] confirms it."
    report = audit(answer, TOOL_CALLS)
    assert report.fabricated.count("UpToDate") == 1


def test_numeric_only_bracket_refs_skipped():
    answer = "This is well established [1] and also [2]."
    report = audit(answer, TOOL_CALLS)
    assert report.total_checked == 0


def test_empty_tool_calls_everything_fabricated():
    answer = "Backed by [Some Guideline, 2024]."
    report = audit(answer, [])
    assert "Some Guideline, 2024" in report.fabricated
    assert not report.verified


def test_collect_allowed_citations_includes_tool_names():
    allowed = collect_allowed_citations(TOOL_CALLS)
    assert "search_clinical_guidelines" in allowed
    assert "search_pubmed" in allowed
