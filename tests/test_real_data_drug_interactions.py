"""Tests for the DDInter real-data merge in drug_safety_server — graceful
degradation when the file is missing, and correct fusion (hand-curated
text always wins, DDInter only fills gaps) when it's present."""

import json

from intelligence.mcp import drug_safety_server as dss


def test_ddinter_subset_file_exists_and_has_expected_shape():
    # This is the actual committed file — verifies it's valid and non-empty,
    # not just that the loader degrades gracefully.
    assert dss._DDINTER_SUBSET_PATH.exists()
    entries = json.loads(dss._DDINTER_SUBSET_PATH.read_text())
    assert len(entries) > 0
    for entry in entries[:5]:
        assert {"drug_a", "drug_b", "severity", "effect", "recommendation"} <= entry.keys()
        assert entry["severity"] in ("major", "moderate", "minor")


def test_load_ddinter_subset_returns_empty_when_file_missing(tmp_path):
    missing_path = tmp_path / "does-not-exist.json"
    assert dss._load_ddinter_subset(missing_path) == {}


def test_load_ddinter_subset_returns_empty_on_malformed_json(tmp_path):
    bad_path = tmp_path / "bad.json"
    bad_path.write_text("{not valid json")
    assert dss._load_ddinter_subset(bad_path) == {}


def test_load_ddinter_subset_merges_new_pairs(tmp_path):
    path = tmp_path / "subset.json"
    path.write_text(
        json.dumps(
            [
                {
                    "drug_a": "drugx",
                    "drug_b": "drugy",
                    "severity": "moderate",
                    "effect": "test effect",
                    "recommendation": "test recommendation",
                    "source": "DDInter 2.0 (test)",
                }
            ]
        )
    )
    extra = dss._load_ddinter_subset(path)
    assert frozenset(["drugx", "drugy"]) in extra
    assert extra[frozenset(["drugx", "drugy"])]["severity"] == "moderate"


def test_load_ddinter_subset_never_overrides_hand_curated_pair(tmp_path):
    # warfarin+aspirin is hand-curated with specific mechanism text — a
    # DDInter entry for the same pair must never override it.
    path = tmp_path / "subset.json"
    path.write_text(
        json.dumps(
            [
                {
                    "drug_a": "warfarin",
                    "drug_b": "aspirin",
                    "severity": "minor",
                    "effect": "wrong generic text",
                    "recommendation": "wrong generic recommendation",
                }
            ]
        )
    )
    extra = dss._load_ddinter_subset(path)
    assert frozenset(["warfarin", "aspirin"]) not in extra


def test_interactions_table_includes_both_hand_curated_and_ddinter_pairs():
    # warfarin+aspirin: hand-curated. warfarin+metformin: DDInter-only.
    assert frozenset(["warfarin", "aspirin"]) in dss.INTERACTIONS
    assert dss.INTERACTIONS[frozenset(["warfarin", "aspirin"])]["severity"] == "major"
    assert frozenset(["warfarin", "metformin"]) in dss.INTERACTIONS
    assert "source" in dss.INTERACTIONS[frozenset(["warfarin", "metformin"])]
