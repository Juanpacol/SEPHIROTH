"""FastMCP server exposing clinical NLP tools (entity extraction)."""

from typing import Any, Dict, List

from fastmcp import FastMCP

mcp = FastMCP(
    name="clinical-nlp",
    instructions="Clinical natural-language processing over medical text.",
)

# Lightweight keyword-based fallback used until a trained MedCAT model pack
# is configured (settings.medcat_model_path). Kept deterministic so the
# pipeline is testable without a 2GB model download.
_FALLBACK_LEXICON: Dict[str, List[str]] = {
    "disease": [
        "diabetes", "hypertension", "asthma", "copd", "pneumonia",
        "heart failure", "atrial fibrillation", "ckd", "anemia",
        "hyperlipidemia", "obesity", "depression", "cancer", "melanoma",
    ],
    "medication": [
        "metformin", "lisinopril", "atorvastatin", "aspirin", "insulin",
        "amlodipine", "omeprazole", "albuterol", "warfarin", "furosemide",
        "hydrochlorothiazide", "losartan", "prednisone", "ventolin",
    ],
    "symptom": [
        "chest pain", "shortness of breath", "dyspnea", "fatigue", "fever",
        "cough", "headache", "nausea", "dizziness", "palpitations", "edema",
    ],
    "procedure": [
        "ct scan", "mri", "x-ray", "echocardiogram", "colonoscopy",
        "biopsy", "catheterization", "dialysis", "surgery",
    ],
}


def _extract_with_lexicon(text: str) -> List[Dict[str, Any]]:
    lowered = text.lower()
    entities: List[Dict[str, Any]] = []
    for entity_type, terms in _FALLBACK_LEXICON.items():
        for term in terms:
            start = lowered.find(term)
            if start != -1:
                entities.append(
                    {
                        "text": term,
                        "entity_type": entity_type,
                        "confidence": 0.7,
                        "start": start,
                        "end": start + len(term),
                        "source": "lexicon-fallback",
                    }
                )
    return entities


@mcp.tool
def extract_medical_entities(text: str) -> Dict[str, Any]:
    """Extract medical entities (diseases, medications, symptoms, procedures)
    from clinical free text. Returns a list of entities with type, confidence,
    and character offsets."""
    try:
        # Prefer MedCAT when a model pack is configured.
        # NOTE: `platform/` is on PYTHONPATH (it can't be a package itself —
        # the name would shadow Python's stdlib `platform` module).
        from core.config import settings  # noqa: PLC0415

        if settings.medcat_model_path:
            from medcat.cat import CAT  # noqa: PLC0415

            cat = CAT.load_model_pack(settings.medcat_model_path)
            doc = cat.get_entities(text)
            entities = [
                {
                    "text": ent["source_value"],
                    "entity_type": ent.get("types", ["unknown"])[0],
                    "confidence": ent.get("acc", 0.0),
                    "start": ent.get("start"),
                    "end": ent.get("end"),
                    "cui": ent.get("cui"),
                    "source": "medcat",
                }
                for ent in doc.get("entities", {}).values()
            ]
            return {"entities": entities, "engine": "medcat"}
    except Exception:
        pass  # fall through to lexicon

    return {"entities": _extract_with_lexicon(text), "engine": "lexicon-fallback"}


@mcp.tool
def summarize_clinical_note(text: str, max_sentences: int = 3) -> Dict[str, Any]:
    """Produce a short extractive summary of a clinical note by selecting the
    sentences that contain the most medical entities."""
    sentences = [s.strip() for s in text.replace("\n", " ").split(".") if s.strip()]
    scored = []
    for sentence in sentences:
        score = len(_extract_with_lexicon(sentence))
        scored.append((score, sentence))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    top = [s for _, s in scored[:max_sentences]]
    return {"summary": ". ".join(top) + ("." if top else ""), "sentence_count": len(top)}
