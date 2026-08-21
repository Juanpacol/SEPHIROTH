"""Matching-quality tests against the REAL committed embeddings artifact —
deliberately not mocked, since the point is to catch a bad model/dimension/
threshold choice, which a synthetic vector would hide (see
tests/test_rag_pipeline.py for the synthetic-vector fusion/threshold unit
tests, which do not require this artifact).

These tests are skipped until `data/embeddings/artifacts/seed_embeddings.json.gz`
exists — build it once with a real GEMINI_API_KEY:

    PYTHONPATH=.:platform .venv/bin/python -m data.embeddings.build_artifact

Each case below documents a specific, previously-diagnosed retrieval
failure from the RAG eval golden dataset (intelligence/evaluation/datasets/
golden.json) — see the plan's motivating table. Recall@k/MRR test the
aggregate; these pin the individual cases so a regression in one is never
masked by an average that still looks fine.
"""

import pytest

from data.embeddings.cached import DEFAULT_ARTIFACT_PATH, CachedEmbeddingProvider
from data.rag import RAGPipeline

pytestmark = pytest.mark.skipif(
    not DEFAULT_ARTIFACT_PATH.exists(),
    reason="embeddings artifact not built — run `python -m data.embeddings.build_artifact`",
)


@pytest.fixture(scope="module")
def rag_pipeline_with_artifact():
    provider = CachedEmbeddingProvider(inner=None)
    return RAGPipeline(embedding_provider=provider)


@pytest.fixture(scope="module")
def embedding_provider():
    return CachedEmbeddingProvider(inner=None)


# --- D.6.1: lay-language <-> clinical-term matching -------------------------
# Each pair is a colloquial rephrasing that shares little to no vocabulary
# with the target guideline's text — exactly what keyword-overlap scoring
# (Recall@1 = 0.7826 on the golden dataset) fails on.

LAY_LANGUAGE_CASES = [
    pytest.param(
        "My kid has an ear infection — what's the go-to antibiotic?",
        "aap-2013-otitis",
        id="ear-infection-to-otitis-media",
    ),
    pytest.param(
        "Should a high-risk pregnant patient start baby aspirin, and when?",
        "acog-2020-preeclampsia",
        id="baby-aspirin-to-preeclampsia",
    ),
    pytest.param(
        "Is a DOAC or warfarin better for most people needing blood thinners for AFib?",
        "accp-2024-afib",
        id="blood-thinners-to-anticoagulation",
    ),
    pytest.param(
        "Should a healthy 65-year-old take a daily aspirin to prevent a heart attack?",
        "acc-aha-2019-primary-prevention",
        id="heart-attack-to-primary-prevention",
    ),
    pytest.param(
        "How long do you treat regular TB that isn't drug resistant?",
        "who-2022-tb",
        id="regular-tb-to-drug-susceptible-tb",
    ),
]


@pytest.mark.parametrize("query,expected_id", LAY_LANGUAGE_CASES)
def test_lay_language_query_matches_clinical_document(query, expected_id, rag_pipeline_with_artifact):
    results = rag_pipeline_with_artifact.retrieve(query, top_k=3)
    ids = [r["id"] for r in results]
    assert expected_id in ids, f"expected {expected_id!r} in top-3 for {query!r}, got {ids}"


# --- D.6.2: compound queries needing multiple relevant documents -----------


def test_compound_query_surfaces_all_relevant_documents(rag_pipeline_with_artifact):
    query = (
        "For a diabetic patient with high blood pressure and protein in the urine, "
        "which BP medication class fits best?"
    )
    ids = {r["id"] for r in rag_pipeline_with_artifact.retrieve(query, top_k=5)}
    expected = {"ada-2024-hypertension-dm", "ada-2024-ckd", "acc-aha-2023-htn"}
    missing = expected - ids
    assert not missing, f"expected all of {expected} in top-5, missing {missing} (got {ids})"


# --- D.6.3: adversarial abstention -----------------------------------------
#
# IMPORTANT, empirically-verified finding: three of the four adversarial
# queries below are topically ON-TOPIC (semaglutide IS a real diabetes/
# obesity drug; septic shock IS covered by sscm-2021-sepsis) — they're
# adversarial because they ask about an unsupported/pseudo-scientific
# *treatment* for a real clinical topic, not because they're unrelated to
# the corpus. Confirmed by running the ORIGINAL keyword-only retriever
# (pre-dating this hybrid change) against them directly: it already
# returns non-empty, topically-correct hits for semaglutide/crystal-
# healing/homeopathy (e.g. "homeopathic remedy for septic shock" already
# matched sscm-2021-sepsis on keyword overlap alone, score 0.85). That is
# retrieval doing its job correctly — surfacing the real guideline for the
# real topic. The genuine safety boundary is the Citation Guard
# (src/sephiroth/verification/citation_guard.py), which checks whether the LLM's
# specific *claims* are grounded in what a retrieved document actually
# says, not whether retrieval returns nothing for a topic it covers.
#
# Only the truly unrelated case (tax advice — zero clinical vocabulary
# overlap with any guideline) is a valid "must return nothing" assertion,
# and it must hold under hybrid retrieval exactly as it already did under
# keyword-only.

TOPICALLY_UNRELATED_ADVERSARIAL_QUERIES = [
    pytest.param(
        "What do the guidelines recommend for filing quarterly small-business tax returns?",
        id="unrelated-tax-advice",
    ),
]

# These are topically on-topic but ask about an unsupported treatment —
# retrieval MAY surface a real, related guideline (that's correct and
# expected); it must never return MORE than top_k results or crash.
TOPICALLY_RELATED_ADVERSARIAL_QUERIES = [
    pytest.param(
        "What do the clinical guidelines say about using semaglutide to treat autism spectrum disorder?",
        id="semaglutide-for-autism",
    ),
    pytest.param(
        "What is the recommended crystal healing protocol for treating pancreatic cancer?",
        id="crystal-healing-for-cancer",
    ),
    pytest.param(
        "What homeopathic remedy is recommended as first-line treatment for septic shock?",
        id="homeopathy-for-sepsis",
    ),
]


@pytest.mark.parametrize("query", TOPICALLY_UNRELATED_ADVERSARIAL_QUERIES)
def test_unrelated_adversarial_query_returns_no_results(query, rag_pipeline_with_artifact):
    assert rag_pipeline_with_artifact.retrieve(query, top_k=5) == []


@pytest.mark.parametrize("query", TOPICALLY_RELATED_ADVERSARIAL_QUERIES)
def test_topically_related_adversarial_query_does_not_overflow_top_k(query, rag_pipeline_with_artifact):
    results = rag_pipeline_with_artifact.retrieve(query, top_k=5)
    assert len(results) <= 5


# --- D.6.4: near-duplicate topic disambiguation ----------------------------
# ada-2024-ckd and ada-2024-hypertension-dm both discuss diabetes + kidneys
# + blood pressure — a weak embedding model or a mis-tuned fusion could
# easily rank the wrong one first for a query specific to one of them.


def test_ckd_specific_query_ranks_ckd_document_first(rag_pipeline_with_artifact):
    results = rag_pipeline_with_artifact.retrieve(
        "When is an SGLT2 inhibitor recommended for chronic kidney disease in type 2 diabetes?",
        top_k=1,
    )
    assert results
    assert results[0]["id"] == "ada-2024-ckd"


def test_bp_target_specific_query_does_not_default_to_ckd_document(rag_pipeline_with_artifact):
    results = rag_pipeline_with_artifact.retrieve(
        "What blood pressure target is recommended for most adults with hypertension?",
        top_k=1,
    )
    assert results
    assert results[0]["id"] == "acc-aha-2023-htn"


# --- D.6.5: the similarity floor itself must separate signal from noise ---


def test_similarity_floor_separates_adversarial_from_relevant_scores(
    embedding_provider, rag_pipeline_with_artifact
):
    from core.config import settings

    relevant_vec = embedding_provider.embed_query(
        "What A1C goal is appropriate for most nonpregnant adults with type 2 diabetes?"
    )
    adversarial_vec = embedding_provider.embed_query(
        "What is the recommended crystal healing protocol for treating pancreatic cancer?"
    )
    store = rag_pipeline_with_artifact._vector_store
    best_relevant = store.search(relevant_vec, top_k=1, min_score=-1.0)[0].score
    best_adversarial = store.search(adversarial_vec, top_k=1, min_score=-1.0)[0].score

    assert best_adversarial < settings.retrieval_min_similarity < best_relevant
