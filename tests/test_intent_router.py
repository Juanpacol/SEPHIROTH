"""`intent_router.route_intent` — the three-tier single-specialist router
(keywords → structured signals → LLM) that single-agent mode dispatches on.

Two properties matter most here and get the most cases:

1. **Intent beats topic.** "What A1C goal is appropriate?" names a lab test
   but asks for a guideline, so it must reach `evidence`, not `laboratory`.
   A router that matched on domain vocabulary alone would answer the wrong
   question — this is the failure the rule ordering exists to prevent.
2. **Every failure path degrades, never raises.** A routing miss should
   cost accuracy, not the consultation.
"""

import pytest

from sephiroth.runtime.intent_router import DEFAULT_ROUTE, route_intent
from tests.conftest import FakeLLMClient

pytestmark = pytest.mark.asyncio


class _NoLLMClient(FakeLLMClient):
    """Fails loudly if the router reaches the LLM tier — used to prove a
    case was resolved by keywords or context signals alone."""

    async def generate_json(self, prompt, schema, *, system_prompt=None):
        raise AssertionError("router reached the LLM tier when it should not have")


class _StubClassifier(FakeLLMClient):
    def __init__(self, payload):
        super().__init__()
        self._payload = payload

    async def generate_json(self, prompt, schema, *, system_prompt=None):
        return self._payload


# --------------------------------------------------------------------------
# Tier 1 — keyword rules
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query,expected",
    [
        # Guideline intent wins even when the question names a lab analyte
        # or a drug — this ordering is the whole point of the rule list.
        ("What A1C goal is appropriate?", "evidence"),
        ("What is the target A1C for adults with type 2 diabetes?", "evidence"),
        ("What is the first-line treatment for hypertension?", "evidence"),
        ("When is anticoagulation recommended for atrial fibrillation?", "evidence"),
        ("What do the guidelines say about statins?", "evidence"),
        # Drug safety: screening a combination
        ("Do warfarin and ibuprofen interact?", "drug_safety"),
        ("Are these medications safe together?", "drug_safety"),
        ("Is this contraindicated with metformin?", "drug_safety"),
        # Radiology: reading an image
        ("Interpret this chest X-ray", "radiology"),
        ("What does the MRI show?", "radiology"),
        ("Any findings on this radiograph?", "radiology"),
        # Laboratory: interpreting values in hand, not merely naming a test
        ("Interpret these lab values", "laboratory"),
        ("The creatinine is 2.4, what does that mean?", "laboratory"),
        ("Explain the elevated potassium", "laboratory"),
    ],
)
async def test_keyword_tier_routes_without_touching_the_llm(query, expected):
    assert await route_intent(query, None, _NoLLMClient()) == expected


# --------------------------------------------------------------------------
# Tier 1 — keyword rules, Spanish phrasing
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query,expected",
    [
        # Same intent-over-topic doctrine as the English cases: a lay
        # "qué hago si tengo X" symptom question is a request for cited
        # guidance, so it routes to evidence — the case that motivated this
        # rule set (`data/rag/corpus_primary_care.py`'s headache coverage).
        ("Qué hago si tengo dolor de cabeza", "evidence"),
        ("Cuál es la meta de A1C recomendada?", "evidence"),
        ("Cuál es el tratamiento de primera línea para la hipertensión?", "evidence"),
        ("Qué dicen las guías sobre las estatinas?", "evidence"),
        ("La warfarina y el ibuprofeno interactúan?", "drug_safety"),
        ("Son seguros estos medicamentos juntos?", "drug_safety"),
        ("Interpreta esta radiografía de tórax", "radiology"),
        ("Qué muestra la resonancia magnética?", "radiology"),
        ("Interpreta estos valores de laboratorio", "laboratory"),
        ("La creatinina está en 2.4, qué significa?", "laboratory"),
    ],
)
async def test_keyword_tier_routes_spanish_without_touching_the_llm(query, expected):
    assert await route_intent(query, None, _NoLLMClient()) == expected


# --------------------------------------------------------------------------
# Tier 2 — structured context signals
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "context,expected",
    [
        ({"image_path": "/scan.png"}, "radiology"),
        ({"lab_results": {"a1c": "7.2"}}, "laboratory"),
        ({"medications": ["warfarin", "aspirin"]}, "drug_safety"),
    ],
)
async def test_context_tier_routes_when_wording_is_ambiguous(context, expected):
    """Wording no keyword rule matches, but the request carries structured
    data that names its own specialist."""
    assert await route_intent("Please review this", context, _NoLLMClient()) == expected


async def test_keywords_take_precedence_over_context_signals():
    """An explicit question about drug interactions routes to drug safety
    even when an image is attached — what the clinician asked beats what
    happens to be in the payload."""
    context = {"image_path": "/scan.png", "medications": ["warfarin", "aspirin"]}
    assert await route_intent("Do these interact?", context, _NoLLMClient()) == "drug_safety"


# --------------------------------------------------------------------------
# Tier 3 — LLM classifier, and its degradation paths
# --------------------------------------------------------------------------


async def test_llm_tier_used_only_when_earlier_tiers_miss():
    client = _StubClassifier({"agent": "radiology"})
    assert await route_intent("Thoughts on this case?", None, client) == "radiology"


@pytest.mark.parametrize(
    "payload",
    [
        {"agent": "not-a-real-agent"},  # unknown name
        {"agent": 42},  # wrong type
        {},  # missing key
        ["radiology"],  # not a dict
        None,
    ],
)
async def test_malformed_classification_degrades_to_default(payload):
    client = _StubClassifier(payload)
    assert await route_intent("Thoughts on this case?", None, client) == DEFAULT_ROUTE


async def test_classification_exception_degrades_to_default():
    class _RaisingClient(FakeLLMClient):
        async def generate_json(self, prompt, schema, *, system_prompt=None):
            raise RuntimeError("model unavailable")

    assert await route_intent("Thoughts on this case?", None, _RaisingClient()) == DEFAULT_ROUTE


@pytest.mark.parametrize("query", ["", "   ", "\n"])
async def test_empty_query_short_circuits_to_default(query):
    assert await route_intent(query, None, _NoLLMClient()) == DEFAULT_ROUTE


async def test_returned_route_is_always_a_real_specialist():
    """Whatever tier resolves it, the result must be a node name the
    registry can look up — the executor calls `get_capability` on it."""
    from sephiroth.runtime.registry import get_capability

    for query in ["Do warfarin and aspirin interact?", "What is the target LDL?", "unclear question"]:
        node = await route_intent(query, None, _StubClassifier({"agent": "evidence"}))
        assert get_capability(node) is not None
