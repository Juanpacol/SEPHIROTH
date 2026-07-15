"""Direct tests for the NLP, imaging, and vision MCP tool functions
(offline paths only — no MedCAT/MONAI weights, no live Ollama)."""

import pytest

from intelligence.mcp import imaging_server, nlp_server, vision_server


def test_extract_medical_entities_lexicon_fallback():
    result = nlp_server.extract_medical_entities("Patient with diabetes on metformin, reports fatigue.")
    assert result["engine"] == "lexicon-fallback"
    types = {e["entity_type"] for e in result["entities"]}
    assert "disease" in types
    assert "medication" in types


def test_extract_medical_entities_no_matches():
    result = nlp_server.extract_medical_entities("Nothing medical here at all.")
    assert result["entities"] == []


def test_summarize_clinical_note_picks_entity_dense_sentences():
    text = (
        "The weather was nice today. Patient has diabetes and hypertension, "
        "on metformin and lisinopril. The parking lot was full."
    )
    result = nlp_server.summarize_clinical_note(text, max_sentences=1)
    assert result["sentence_count"] == 1
    assert "metformin" in result["summary"].lower()


def test_summarize_clinical_note_empty_text():
    result = nlp_server.summarize_clinical_note("", max_sentences=3)
    assert result["sentence_count"] == 0
    assert result["summary"] == ""


def test_inspect_medical_image_missing_file():
    result = imaging_server.inspect_medical_image("/tmp/does-not-exist-xyz.png")
    assert "error" in result


def test_inspect_medical_image_png(tmp_path):
    from PIL import Image

    img_path = tmp_path / "test.png"
    Image.new("RGB", (10, 20)).save(img_path)

    result = imaging_server.inspect_medical_image(str(img_path))
    assert result["format"] == ".png"
    assert result["shape"] == [20, 10]


def test_analyze_medical_image_unsupported_modality():
    result = imaging_server.analyze_medical_image("/tmp/x.png", modality="not-a-modality")
    assert "error" in result


def test_analyze_medical_image_missing_file():
    result = imaging_server.analyze_medical_image("/tmp/does-not-exist-xyz.png", modality="xray")
    assert "error" in result


def test_analyze_medical_image_no_weights_configured(tmp_path):
    img_path = tmp_path / "x.png"
    img_path.write_bytes(b"fake png bytes")
    result = imaging_server.analyze_medical_image(str(img_path), modality="xray")
    assert result["status"] == "model_not_configured"
    assert result["requires_professional_review"] is True


@pytest.mark.asyncio
async def test_describe_medical_image_disabled(monkeypatch):
    class _Settings:
        enable_vision_analysis = False

    monkeypatch.setattr(vision_server, "_settings", lambda: _Settings())
    result = await vision_server.describe_medical_image("/tmp/x.png")
    assert result["status"] == "unavailable"


@pytest.mark.asyncio
async def test_describe_medical_image_missing_file(monkeypatch):
    class _Settings:
        enable_vision_analysis = True

    monkeypatch.setattr(vision_server, "_settings", lambda: _Settings())
    result = await vision_server.describe_medical_image("/tmp/does-not-exist-xyz.png")
    assert "error" in result


@pytest.mark.asyncio
async def test_describe_medical_image_unsupported_format(monkeypatch, tmp_path):
    class _Settings:
        enable_vision_analysis = True

    monkeypatch.setattr(vision_server, "_settings", lambda: _Settings())
    dicom_like = tmp_path / "scan.dcm"
    dicom_like.write_bytes(b"not really dicom")
    result = await vision_server.describe_medical_image(str(dicom_like))
    assert "error" in result
