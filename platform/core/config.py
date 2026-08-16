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

    # Fallback LLM — Groq (OpenAI-compatible API), free tier. Used only for
    # text/tool-calling when Gemini is unavailable (rate-limited or its
    # daily request quota is exhausted — a real constraint observed on
    # the free tier). No fallback for vision or embeddings; those stay on
    # Gemini only. Fallback is active only when GROQ_API_KEY is set.
    groq_api_key: Optional[str] = None
    groq_model: str = "llama-3.3-70b-versatile"
    groq_max_retries: int = 3
    llm_enable_fallback: bool = True

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
    retrieval_min_similarity: float = 0.70
    retrieval_mode: Literal["hybrid", "keyword_only"] = "hybrid"

    # Feature flags
    # Enforce each agent's `allowed_tools` whitelist at dispatch time, not just
    # when advertising schemas to the model. Set False to run permissively
    # (denials are logged, execution proceeds) when diagnosing whether a
    # specialist relies on a tool outside its declared scope.
    enforce_tool_authorization: bool = True

    enable_image_analysis: bool = True
    enable_vision_analysis: bool = True
    enable_rag: bool = True
    enable_rag_embeddings: bool = True
    enable_agents: bool = True

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


settings = Settings()
