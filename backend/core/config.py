"""Centralized configuration using Pydantic BaseSettings.

This module consolidates all environment variable access into a single
type-safe configuration object. All env vars are mapped to typed fields
with sensible defaults matching the original behavior in constants.py.
"""

import sys

from pydantic import ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    All fields have defaults matching the original constants.py behavior.
    Environment variables are case-insensitive and loaded from .env file.
    """

    # =============================================================================
    # LLM Configuration
    # =============================================================================

    llm_api_key: str = Field(..., description="API key for LLM provider")
    llm_base_url: str = Field("https://api.openai.com/v1", description="Base URL for LLM API")
    llm_model: str = Field("gpt-4o", description="Default LLM model")
    llm_concurrency: int = Field(
        2,
        ge=1,
        le=20,
        description="Concurrent LLM calls (clamped 1-20)",
    )
    llm_default_max_tokens: int = Field(8192, description="Default max tokens for LLM responses")

    @field_validator("llm_api_key")
    @classmethod
    def validate_llm_api_key(cls, v: str) -> str:
        if not v or v.strip() == "":
            print("\n" + "=" * 80, file=sys.stderr)
            print("CONFIGURATION ERROR: Missing required environment variable", file=sys.stderr)
            print("=" * 80, file=sys.stderr)
            print("\nLLM_API_KEY is required but not set.", file=sys.stderr)
            print("\nPlease set it in your .env file or environment:", file=sys.stderr)
            print("  export LLM_API_KEY=your-api-key-here", file=sys.stderr)
            print("\nFor more information, see README.md", file=sys.stderr)
            print("=" * 80 + "\n", file=sys.stderr)
            sys.exit(1)
        return v

    # =============================================================================
    # Multi-Model Configuration
    # =============================================================================

    llm_model_id: str = Field(
        "",
        description="Canonical model ID for routing (e.g. 'openai:gpt-4o')",
    )
    model_registry_json: str = Field("", description="JSON string defining available models")
    model_config_path: str = Field("", description="Path to YAML model configuration file")

    # DeepSeek Configuration
    deepseek_api_key: str = Field("", description="DeepSeek API key")
    deepseek_base_url: str = Field(
        "https://api.deepseek.com/v1", description="DeepSeek API base URL"
    )

    # Ollama Configuration
    ollama_base_url: str = Field("http://localhost:11434/v1", description="Ollama API base URL")
    ollama_api_key: str = Field("ollama", description="Ollama API key (fixed)")
    ollama_models: str = Field("", description="Comma-separated list of Ollama models")

    # =============================================================================
    # Search Configuration
    # =============================================================================

    semantic_scholar_api_key: str = Field("", description="Semantic Scholar API key (optional)")

    # =============================================================================
    # Concurrency Limits
    # =============================================================================

    fulltext_concurrency: int = Field(3, description="Concurrent fulltext API requests")
    claim_verification_concurrency: int = Field(
        2,
        ge=1,
        le=20,
        description="Concurrent claim verification calls (clamped 1-20)",
    )

    # =============================================================================
    # Workflow Configuration
    # =============================================================================

    workflow_timeout_seconds: int = Field(300, description="Workflow timeout in seconds")
    claim_verification_enabled: bool = Field(True, description="Enable semantic claim verification")

    # =============================================================================
    # MinIO Configuration
    # =============================================================================

    minio_endpoint: str = Field("localhost:9000", description="MinIO endpoint")
    minio_access_key: str = Field("minioadmin", description="MinIO access key")
    minio_secret_key: str = Field("minioadmin", description="MinIO secret key")
    minio_secure: bool = Field(False, description="Use HTTPS for MinIO")
    minio_bucket_raw: str = Field("rag-raw", description="MinIO raw bucket name")
    minio_bucket_processed: str = Field("rag-processed", description="MinIO processed bucket name")
    minio_bucket_tmp: str = Field("rag-tmp", description="MinIO temp bucket name")

    # =============================================================================
    # Redis Configuration
    # =============================================================================

    redis_host: str = Field("localhost", description="Redis host")
    redis_port: int = Field(6379, ge=1, le=65535, description="Redis port")
    redis_db: int = Field(0, ge=0, le=15, description="Redis database number")
    redis_password: str = Field("", description="Redis password")
    redis_pdf_cache_ttl: int = Field(
        86400, ge=60, le=604800, description="Redis PDF cache TTL in seconds"
    )

    # =============================================================================
    # PDF Configuration
    # =============================================================================

    pdf_download_timeout: int = Field(
        30, ge=5, le=300, description="PDF download timeout in seconds"
    )
    pdf_max_size_mb: int = Field(50, ge=1, le=500, description="Maximum PDF size in MB")

    # =============================================================================
    # Embedding Configuration
    # =============================================================================

    embedding_model: str = Field("text-embedding-3-small", description="Embedding model name")

    # =============================================================================
    # PostgreSQL Configuration
    # =============================================================================

    postgres_host: str = Field("localhost", description="PostgreSQL host")
    postgres_port: int = Field(5432, ge=1, le=65535, description="PostgreSQL port")
    postgres_db: str = Field("autoscholar", description="PostgreSQL database name")
    postgres_user: str = Field("autoscholar", description="PostgreSQL username")
    postgres_password: str = Field("autoscholar", description="PostgreSQL password")

    # =============================================================================
    # Qdrant Configuration
    # =============================================================================

    qdrant_host: str = Field("localhost", description="Qdrant host")
    qdrant_port: int = Field(6333, ge=1, le=65535, description="Qdrant port")
    qdrant_collection_name: str = Field("paper_chunks", description="Qdrant collection name")

    # =============================================================================
    # Feature Flags
    # =============================================================================

    vector_pipeline_enabled: bool = Field(False, description="Enable vector pipeline processing")

    # =============================================================================
    # RAG Gateway Configuration
    # =============================================================================

    rag_gateway_url: str = Field("", description="RAG gateway URL (optional)")
    rag_gateway_timeout: int = Field(10, ge=1, le=60, description="RAG gateway timeout in seconds")

    # =============================================================================
    # Evaluation Configuration
    # =============================================================================

    human_ratings_db_path: str = Field(
        "human_ratings.db", description="Path to human ratings database"
    )

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    def get_postgres_url(self) -> str:
        """Get PostgreSQL connection URL."""
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"


# Global settings instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get or create settings instance (FastAPI dependency).

    This function can be used as a FastAPI dependency to inject
    settings into route handlers and services.

    Returns:
        Settings: The global settings instance
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
