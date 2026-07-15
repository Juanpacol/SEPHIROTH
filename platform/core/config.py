"""Configuration management for SEPHIROTH."""

from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings (overridable via environment / .env)."""

    # API
    api_title: str = "SEPHIROTH"
    api_version: str = "0.1.0"
    debug: bool = False

    # Database (async driver; host port 5433 — see docker-compose.yml)
    database_url: str = "postgresql+asyncpg://clinical_ai:clinical_ai_password@localhost:5433/clinical_ai_db"

    # Auth
    jwt_secret: str = "dev-secret-change-in-production-0000"  # >=32 bytes for HS256
    jwt_expires_minutes: int = 1440

    # Redis
    redis_url: str = "redis://localhost:6379"

    # LLM — 100% local via Ollama. Ollama must run natively on the host
    # (Metal GPU); from Docker use http://host.docker.internal:11434.
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    # Multimodal model for medical image description (ollama pull llava:7b).
    # Swap for a lighter model (e.g. moondream) via env if RAM is tight.
    ollama_vision_model: str = "llava:7b"

    # Medical AI model weights (optional — features degrade gracefully)
    medcat_model_path: Optional[str] = None
    monai_model_path: Optional[str] = None

    # RAG
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Feature flags
    enable_image_analysis: bool = True
    enable_vision_analysis: bool = True
    enable_rag: bool = True
    enable_agents: bool = True

    class Config:
        env_file = ".env"


settings = Settings()
