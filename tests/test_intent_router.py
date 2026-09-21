"""`intent_router.route_intent` — the three-tier single-specialist router
(keywords → structured signals → LLM) that single-agent mode dispatches on.

Two properties matter most here and get the most cases:

1. **Intent beats topic.** "What A1C goal is appropriate?" names a lab test
   but asks for a guideline, so it must reach `evidence`. A router that
   matched on domain vocabulary alone would answer the wrong question —
   this is the failure the rule ordering exists to prevent.
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


@pytest.mark.xfail(
    reason="SPEC-029 not yet implemented — laboratory keyword rule removal lands in SF059", strict=False
)
@pytest.mark.parametrize(
    "query",
    [
        "Interpret these lab values",
        "The creatinine is 2.4, what does that mean?",
        "Explain the elevated potassium",
    ],
)
async def test_lab_interpretation_question_falls_through_to_evidence(query):
    """SPEC-029 AC-029-05: `laboratory` no longer exists as a keyword-tier
    match — a query shaped like the old laboratory rule must not raise or
    resolve to a removed agent. No keyword or context signal matches it, so
    it reaches the LLM tier; when that tier itself names `evidence` (the
    correct call once `laboratory` is gone), the route is `evidence`."""
    client = _StubClassifier({"agent": "evidence"})
    assert await route_intent(query, None, client) == "evidence"


@pytest.mark.xfail(
    reason="SPEC-029 not yet implemented — laboratory keyword rule removal lands in SF059", strict=False
)
async def test_lab_interpretation_question_degrades_to_evidence_by_default():
    """Same shape, but the LLM tier itself fails — must still land on
    `evidence` (`DEFAULT_ROUTE`), never on the removed `laboratory` name."""

    class _RaisingClient(FakeLLMClient):
        async def generate_json(self, prompt, schema, *, system_prompt=None):
            raise RuntimeError("model unavailable")

    assert await route_intent("Interpret these lab values", None, _RaisingClient()) == DEFAULT_ROUTE


@pytest.mark.xfail(
    reason="SPEC-029 not yet implemented — lab_results context-tier mapping removal lands in SF059",
    strict=False,
)
async def test_lab_result_context_no_longer_routes_to_a_removed_agent():
    """SPEC-029 AC-029-01/02: `lab_results` in context used to select
    `laboratory` directly (tier 2). That mapping is gone — the signal must
    not resolve to a name `get_capability` can no longer look up."""
    from sephiroth.runtime.registry import get_capability

    client = _StubClassifier({"agent": "evidence"})
    node = await route_intent("Please review this", {"lab_results": {"a1c": "7.2"}}, client)
    assert get_capability(node) is not None
    assert node != "laboratory"


async def test_returned_route_is_always_a_real_specialist():
    """Whatever tier resolves it, the result must be a node name the
    registry can look up — the executor calls `get_capability` on it."""
    from sephiroth.runtime.registry import get_capability

    for query in ["Do warfarin and aspirin interact?", "What is the target LDL?", "unclear question"]:
        node = await route_intent(query, None, _StubClassifier({"agent": "evidence"}))
        assert get_capability(node) is not None
