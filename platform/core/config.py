"""Configuration management for SEPHIROTH."""

import logging
from typing import Literal, Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

DEFAULT_JWT_SECRET = "dev-secret-change-in-production-0000"
_INSECURE_JWT_SECRETS = {
    DEFAULT_JWT_SECRET.lower(),
    "change-me-in-production",
    "secret",
    "changeme",
}


class Settings(BaseSettings):
    """Application settings (overridable via environment / .env)."""

    # API
    api_title: str = "SEPHIROTH"
    api_version: str = "0.1.0"
    debug: bool = False
    environment: Literal["development", "test", "staging", "production"] = "development"

    # Database (async driver; host port 5433 — see docker-compose.yml)
    database_url: str = "postgresql+asyncpg://clinical_ai:clinical_ai_password@localhost:5433/clinical_ai_db"

    # Auth
    jwt_secret: str = DEFAULT_JWT_SECRET  # >=32 bytes for HS256
    jwt_expires_minutes: int = 1440

    # POST /api/auth/register is clinician-only once a clinician account
    # exists (a patient account is created only via the invite/claim
    # flow — see PatientInvite). This flag lets the *first* account on a
    # fresh database be created without one; default on in dev/test so
    # local setup and the test suite don't need a bootstrap step, off in
    # staging/production where an operator provisions the first account
    # out of band.
    allow_bootstrap_registration: bool = True

    # LLM — Google Gemini API (AI Studio free tier). PHI leaves the machine;
    # see README's privacy notice. Requests are unauthenticated/degraded
    # gracefully when GEMINI_API_KEY is unset (health() returns False).
    gemini_api_key: Optional[str] = None
    # "gemini-flash-latest" is a Google-maintained alias for the current
    # recommended flash model — pinned model names (e.g. "gemini-2.5-flash")
    # get deprecated/blocked for new API keys over time; the alias tracks
    # whatever replaces them automatically.
    gemini_model: str = "gemini-flash-latest"
    # Multimodal override for medical image description; None -> gemini_model.
    gemini_vision_model: Optional[str] = None
    gemini_max_output_tokens: int = 2048
    gemini_timeout_seconds: int = 60
    gemini_max_retries: int = 3
    # Free-tier requests-per-minute budget shared by all agents + vision.
    gemini_rpm_limit: int = 10
    llm_max_tool_rounds: int = 6

    # OpenAI API (for data generation, testing, etc.)
    openai_api_key: Optional[str] = None

    # Which provider `get_llm_client()` builds as primary. "gemini" (default)
    # preserves all pre-Phase-1 behavior, including Groq fallback below.
    # "groq" returns a bare GroqClient, never wrapped the other way around.
    # "ollama" returns a bare OllamaClient — local dev only, no fallback.
    # "split" routes vision to Gemini only and chat/tool-calling to Ollama
    # (nemotron via OpenRouter's OpenAI-compatible endpoint by default,
    # `ollama_base_url`/`ollama_model`), falling back to Groq for chat —
    # see `VisionChatSplitClient` and the runtime audit's model comparison.
    llm_provider: Literal["gemini", "groq", "ollama", "split"] = "gemini"

    # Fallback LLM — Groq (OpenAI-compatible API), free tier. Used only for
    # text/tool-calling when Gemini is unavailable (rate-limited or its
    # daily request quota is exhausted — a real constraint observed on
    # the free tier). Fallback is active only when GROQ_API_KEY is set.
    groq_api_key: Optional[str] = None
    groq_model: str = "llama-3.3-70b-versatile"
    # Vision fallback is opt-in and OFF by default (None) — Groq's vision
    # models have historically churned (Llama 4 Scout/Maverick both
    # deprecated in favor of text-only replacements as of this setting's
    # introduction; only older "-preview" vision models remain, which can
    # be pulled with little notice). Set this to a vision-capable Groq
    # model id (e.g. "llama-3.2-90b-vision-preview") to accept that
    # instability in exchange for imaging staying up when Gemini's vision
    # quota is exhausted, instead of degrading to "unavailable."
    groq_vision_model: Optional[str] = None
    groq_max_retries: int = 3
    # Defaults match the values the factory borrowed from Gemini/GroqClient
    # before these existed, so default behavior is unchanged.
    groq_timeout_seconds: int = 60
    groq_max_output_tokens: int = 2048
    # 0 disables rate limiting entirely — Groq had no throttle before Phase 1.
    groq_rpm_limit: int = 0
    llm_enable_fallback: bool = True

    # Local dev via Ollama (`llm_provider="ollama"`) — free, no rate limits,
    # no key required by default. `ollama_base_url` can also point at
    # OpenRouter's OpenAI-compatible endpoint (with `ollama_api_key` set) to
    # run the same client against a hosted version of the same model.
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen2.5:14b"
    ollama_vision_model: Optional[str] = None
    ollama_api_key: Optional[str] = None
    ollama_max_retries: int = 3
    ollama_timeout_seconds: int = 120
    ollama_max_output_tokens: int = 2048
    ollama_rpm_limit: int = 0

    # Medical AI model weights (optional — features degrade gracefully)
    medcat_model_path: Optional[str] = None
    monai_model_path: Optional[str] = None

    # RAG — dense retrieval (Gemini embeddings), fused with keyword scoring.
    # A cached, committed artifact backs offline/CI use; see data/embeddings/.
    embedding_model: str = "gemini-embedding-001"
    gemini_embedding_model: str = "gemini-embedding-001"
    embedding_dimension: int = 768
    # Cosine-similarity floor below which a dense hit is dropped entirely —
    # keeps adversarial/off-topic queries returning zero results, since
    # dense embeddings (unlike keyword overlap) almost never score exactly 0.
    # 0.60, not 0.70: measured against the local nomic-embed-text artifact
    # (2026-09-01, once Gemini quota was reserved for vision-only use —
    # see data/embeddings/ollama.py), a genuinely relevant compound-query
    # match scored as low as 0.638, while the one true off-topic case in
    # tests/test_embeddings_matching.py (unrelated tax-filing question)
    # topped out at 0.4737 — 0.70 was calibrated for Gemini's embedding
    # score distribution and silently dropped real matches under Ollama's.
    retrieval_min_similarity: float = 0.60
    retrieval_mode: Literal["hybrid", "keyword_only"] = "hybrid"
    # Floor for `api/fast_path.py`'s guideline branch, which skips citation
    # guard and verification entirely (see that module's docstring) — a weak
    # top-1 hit must never become the final answer unchecked. NOT a cosine
    # similarity like `retrieval_min_similarity` above: `RAGPipeline.retrieve`'s
    # "score" is the RRF-fused value from `data/rag/__init__.py::_fuse`
    # (RRF_K=60, dense weight 2.0, keyword weight 1.0), whose whole range sits
    # under ~0.05 — a rank-0 dense-only hit scores ~0.0328, a rank-0
    # keyword-only hit (no embedding signal at all) scores ~0.0164. 0.02 sits
    # between those two: it requires at least a real embedding-corroborated
    # match, rejecting a hit that only coincidentally shares a keyword.
    # Calibrated against the seed corpus at write time (see
    # `data/rag/corpus_primary_care.py`); recalibrate against the rebuilt
    # embeddings artifact if the corpus changes materially.
    fast_path_min_score: float = 0.02

    # Feature flags
    # Enforce each agent's `allowed_tools` whitelist at dispatch time, not just
    # when advertising schemas to the model. Set False to run permissively
    # (denials are logged, execution proceeds) when diagnosing whether a
    # specialist relies on a tool outside its declared scope.
    enforce_tool_authorization: bool = True

    # Bounds a single tool dispatch (intelligence/mcp -> FastMCP call). Two
    # tools perform real I/O (search_pubmed over the network, describe_medical_image
    # via a model call) and could otherwise hang a consultation indefinitely.
    tool_call_timeout_seconds: float = 30.0

    # Character-count budget (approximate, not a real tokenizer) for the
    # coordinator's assembled specialist sections (src/sephiroth/context/budget.py) —
    # bounds what was previously an unbounded concatenation of up to 4
    # specialist answers.
    max_context_chars: int = 4000

    # SPEC-006 (ADR-009): when False, sephiroth.telemetry.traced_span is a
    # pure no-op — a run must produce an identical RunState with tracing
    # disabled vs. enabled, apart from the (then-empty) .spans list.
    enable_tracing: bool = True

    # SPEC-008 (closes SPEC-003 NG-1): when True, routing asks the model
    # which specialists are relevant instead of the static key-presence
    # heuristic, falling back to that heuristic on any model failure.
    # Default False — the offline eval (--mode ci) has no live model, so
    # leaving this off keeps eval deterministic.
    enable_dynamic_planner: bool = False

    # When True, a consultation routes to exactly ONE specialist
    # (`sephiroth.runtime.intent_router`) whose answer is returned
    # directly, skipping both the parallel fan-out and the coordinator
    # turn that merges its results. Cuts a consultation from 4-8
    # sequential model round-trips to 3 (1 answer + 2 verification),
    # which is what makes the chat usable on a free/local model.
    # Verification, citation guard, and abstention are unaffected —
    # they run identically in both modes. Set False to restore the
    # multi-agent fan-out; `enable_dynamic_planner` only applies then.
    enable_single_agent_mode: bool = True

    # Claim extraction and claim verification are two strictly sequential
    # `generate_json` calls (the second needs the first's claim ids).
    # Measured on a local model they were 47s of a 74s consultation — more
    # than producing the answer. When True, `verification.combined`
    # does both in one call. Every guarantee is preserved: same claim
    # fields, the same deterministic low-overlap downgrade from
    # `verify.py`, contradictions, and the same degrade-to-empty on any
    # failure. Set False to restore the two-call path.
    enable_combined_verification: bool = True

    # Attachment byte storage (platform/core/storage.py). "postgres"
    # (default) keeps today's behavior unchanged; "s3" requires
    # s3_bucket plus standard AWS credentials (env vars or IAM role —
    # never hardcoded here). Switching backends does not migrate
    # already-stored bytes.
    storage_backend: Literal["postgres", "s3"] = "postgres"
    s3_bucket: Optional[str] = None
    s3_region: str = "us-east-1"

    # No production frontend origin is deployed yet -- add it here (and in
    # render.yaml) once one exists, rather than hardcoding it in main.py.
    cors_allow_origins: list[str] = ["http://localhost:3000", "http://localhost:3100"]

    enable_image_analysis: bool = True
    enable_vision_analysis: bool = True
    enable_rag: bool = True
    enable_rag_embeddings: bool = True
    enable_agents: bool = True

    # SPEC-009: the workflow-automation substrate. Off by default -- there
    # is no worker process, so a cron (cron-job.org, free tier) POSTs to
    # POST /internal/tick, authenticated by internal_tick_token. False
    # keeps the endpoint a harmless 200 {"status":"disabled"} rather than
    # a 404, so pointing cron at a not-yet-enabled deploy is a no-op, not
    # an error.
    enable_workflow_engine: bool = False
    internal_tick_token: Optional[str] = None
    workflow_tick_batch_size: int = 25
    workflow_step_timeout_seconds: float = 5.0
    workflow_tick_budget_seconds: float = 20.0
    workflow_step_lease_seconds: int = 120

    # Optional ops monitoring: a tick posts a health summary to this Slack
    # incoming-webhook URL when set, and stays silent (no notifier, no
    # error) when unset -- same degrade-gracefully posture as
    # groq_api_key/s3_bucket above. No separate enable flag: the URL's
    # presence IS the switch, see platform/api/workflows/ops_notify.py.
    slack_webhook_url: Optional[str] = None

    # Clinician-facing Slack channel -- deliberately a SEPARATE webhook
    # from slack_webhook_url above. That one is engineering/ops (workflow
    # health, PHI-free by contract); this one exists BECAUSE a clinician
    # needs patient-identifying clinical signal (a new critical alert, an
    # AI answer flagged for review, a daily digest). See
    # platform/api/workflows/clinical_notify.py's module docstring for the
    # privacy posture. Same degrade-gracefully pattern: unset = silent.
    clinical_slack_webhook_url: Optional[str] = None

    class Config:
        env_file = ".env"

    @model_validator(mode="after")
    def _check_jwt_secret(self) -> "Settings":
        if self.environment in ("development", "test"):
            if self.jwt_secret.lower() in _INSECURE_JWT_SECRETS:
                logger.warning(
                    "jwt_secret is using an insecure default value; this is only "
                    "acceptable in development/test environments."
                )
            return self
        if self.jwt_secret.lower() in _INSECURE_JWT_SECRETS:
            raise ValueError(
                f"jwt_secret must not be a known insecure default in "
                f"environment={self.environment!r}. Set JWT_SECRET to a random "
                "value >=32 chars, e.g. `openssl rand -hex 32`."
            )
        if len(self.jwt_secret) < 32:
            raise ValueError(
                f"jwt_secret must be >=32 chars in environment={self.environment!r} "
                "(HS256 requires a sufficiently long key)."
            )
        return self

    @model_validator(mode="after")
    def _check_tick_token(self) -> "Settings":
        if not self.enable_workflow_engine or self.environment not in ("staging", "production"):
            return self
        if not self.internal_tick_token or len(self.internal_tick_token) < 32:
            raise ValueError(
                "internal_tick_token must be set to a random value >=32 chars "
                f"when enable_workflow_engine=True in environment={self.environment!r}, "
                "e.g. `openssl rand -hex 32`."
            )
        return self


settings = Settings()
