"""Configuration constants with trade-off documentation.

Each constant has a rationale explaining why this specific value was chosen.
This enables informed discussion during code reviews and interviews.

NOTE: Environment variables are now centralized in backend.core.config.Settings.
This file maintains backward compatibility by importing from the settings instance.
"""

import os

from backend.core.config import get_settings

# Get settings instance
settings = get_settings()

# =============================================================================
# Environment Variable Helpers (DEPRECATED - use settings.field_name instead)
# =============================================================================


def _parse_int_env(name: str, default: int, min_val: int, max_val: int) -> int:
    """Parse an integer environment variable with bounds clamping.

    DEPRECATED: This function is kept for backward compatibility.
    New code should use settings fields directly.

    Returns default if env var is unset or unparseable. Clamps to [min_val, max_val].
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(min_val, min(max_val, value))


# =============================================================================
# Search Configuration
# =============================================================================

MAX_KEYWORDS = 5
# Why 5: LLM generates 3-5 keywords covering core concept + methodology + application.
# >5 introduces noise (overly broad terms), <3 insufficient coverage.

PAPERS_PER_QUERY = 5
# Why 5: Each source returns top-5 most relevant papers per keyword.
# 5 keywords × 5 papers × 3 sources = 75 candidates (pre-dedup), ~15-25 after dedup.
# Keeps approved papers in the 10-20 range — ideal for a focused literature review.
# Previous value of 10 caused 50+ candidates, leading to LLM output truncation.

# =============================================================================
# Concurrency Limits
# =============================================================================

LLM_CONCURRENCY = settings.llm_concurrency
# Why 2: OpenAI free/low-tier limits ~3 RPM. Concurrency=2 avoids rate limits
# while being 2x faster than sequential. Increase for higher-tier API keys.
# Configurable via LLM_CONCURRENCY env var (clamped to 1-20).

LLM_DEFAULT_MAX_TOKENS = settings.llm_default_max_tokens
# Why 8192: DeepSeek defaults to 4096 when max_tokens is not set, which causes
# JSON truncation on longer outputs. 8192 is DeepSeek's maximum supported value.
# For OpenAI models this is also a safe default (well within their limits).

FULLTEXT_CONCURRENCY = 3
# Why 3: Unpaywall has no official rate limit docs. Testing showed 5 concurrent
# requests occasionally trigger 429. 3 is safe and acceptable for <20 papers.

# =============================================================================
# Workflow Configuration
# =============================================================================

WORKFLOW_TIMEOUT_SECONDS = 300
# Why 300: Measured 5-paper workflow ~45s, 20-paper ~180s. 300s (5min) provides
# 1.5x buffer for slow networks/APIs. Prevents infinite hangs on failures.

MAX_QA_RETRIES = 3
# Why 3: Citation errors usually fixed in 1-2 retries. 3 catches edge cases
# without wasting tokens on fundamentally broken generations.

MAX_CONVERSATION_TURNS = 5
# Why 5: Context window efficiency. Recent 5 turns capture relevant history
# without bloating prompts. Older context rarely affects current generation.

# =============================================================================
# Draft Generation
# =============================================================================

DRAFT_BASE_TOKENS = 2000
DRAFT_TOKENS_PER_PAPER = 300
DRAFT_MAX_TOKENS = 8000

SECTION_BASE_TOKENS = 1500
SECTION_TOKENS_PER_PAPER = 100
SECTION_MAX_TOKENS = 4000


def get_draft_max_tokens(num_papers: int) -> int:
    return min(DRAFT_MAX_TOKENS, DRAFT_BASE_TOKENS + num_papers * DRAFT_TOKENS_PER_PAPER)


def get_section_max_tokens(num_papers: int) -> int:
    return min(SECTION_MAX_TOKENS, SECTION_BASE_TOKENS + num_papers * SECTION_TOKENS_PER_PAPER)


# =============================================================================
# Source Failure Tracking
# =============================================================================

SOURCE_SKIP_THRESHOLD = 3
# Why 3: After 3 consecutive failures, the source is likely down.
# Fewer retries waste time; more delays user unnecessarily.

SOURCE_SKIP_WINDOW_SECONDS = 120
# Why 120: 2-minute window balances quick recovery detection with
# avoiding repeated failures. Sources typically recover within minutes.

MODEL_SKIP_THRESHOLD = 3
# Why 3: Same threshold as source failure tracking. Repeated failures strongly
# indicate an unhealthy model/provider route and justify temporary bypass.

MODEL_SKIP_WINDOW_SECONDS = 120
# Why 120: Same 2-minute window as source tracking, balancing resilience and
# recovery without requiring manual intervention.

# =============================================================================
# Claim Verification Configuration
# =============================================================================

CLAIM_VERIFICATION_CONCURRENCY = settings.claim_verification_concurrency
# Why 2: Same as LLM_CONCURRENCY. Each claim verification is an LLM call.
# Keeps within rate limits while parallelizing verification.
# Configurable via CLAIM_VERIFICATION_CONCURRENCY env var (clamped to 1-20).

CLAIM_BATCH_SIZE = 3
# Why 3: Groups sections for batch claim extraction (1 LLM call per batch).
# 3 sections per batch balances prompt size vs call reduction.
# 5 sections → 2 LLM calls instead of 5. Fallback to per-section on failure.

# Claim verification can be disabled for time-sensitive scenarios
# Default: true (maintains 97.3% citation accuracy)
# Opt-out: Set to "false" to disable claim verification
CLAIM_VERIFICATION_ENABLED = settings.claim_verification_enabled
# Feature flag to enable/disable semantic claim verification.
# Set to False to skip claim-level checks and use only rule-based validation.

MIN_ENTAILMENT_RATIO = 0.8
# Why 0.8: At least 80% of claim-citation pairs must be "entails".
# Below this threshold, QA fails and triggers retry.
# 0.8 balances strictness with tolerance for edge cases.

# =============================================================================
# Evaluation Framework Configuration
# =============================================================================

REQUIRED_SECTIONS_EN = ["Introduction", "Background", "Methods", "Discussion", "Conclusion"]
REQUIRED_SECTIONS_ZH = ["引言", "背景", "方法", "讨论", "结论"]

SECTION_ALIASES: dict[str, list[str]] = {
    "Introduction": ["Overview", "Preface", "概述", "前言"],
    "Background": ["Related Work", "Literature Review", "相关工作", "文献综述"],
    "Methods": ["Methodology", "Approach", "Techniques", "方法论", "技术方法"],
    "Discussion": ["Analysis", "Results", "Findings", "分析", "结果", "发现"],
    "Conclusion": ["Summary", "Conclusions", "总结", "结论与展望"],
}

HEDGING_PATTERNS_EN = [
    r"\bmay\b",
    r"\bmight\b",
    r"\bcould\b",
    r"\bpossibly\b",
    r"\bperhaps\b",
    r"\bsuggests?\b",
    r"\bindicates?\b",
    r"\bappears?\b",
    r"\bseems?\b",
    r"\blikely\b",
    r"\bunlikely\b",
    r"\bprobably\b",
    r"\bpotentially\b",
]
HEDGING_PATTERNS_ZH = [r"可能", r"或许", r"似乎", r"大概", r"也许", r"表明", r"显示"]

PASSIVE_PATTERN_EN = r"\b(is|are|was|were|been|being)\s+\w+ed\b"
PASSIVE_PATTERN_ZH = r"被\w+"

MIN_HEDGING_RATIO = 0.05
MAX_HEDGING_RATIO = 0.20
MIN_CITATION_DENSITY = 2.0

# =============================================================================
# Context Engineering (P3)
# =============================================================================

CONTEXT_TOKEN_BUDGET = 40000
# Why 40000: Safety net only. In normal use, ALL approved papers are included.
# 100 papers × ~180 tokens = ~18,000 tokens (well within 128K context window).
# This budget only triggers in extreme edge cases (200+ papers with full
# structured contributions). Academic reviews should cite ALL approved papers.

CONTEXT_TOKENS_PER_PAPER_ESTIMATE = 180
# Why 180: Average across papers with full structured_contribution (8 fields).
# Papers with only abstract fallback are shorter (~100 tokens).
# Used as fallback when per-paper estimation is unavailable.

CONTEXT_MAX_PAPERS = 200
# Why 200: Safety net only, not a functional limit. ALL approved papers should
# be extracted and cited. This prevents truly pathological cases (e.g., a bug
# that approves thousands of papers). Normal workflows never hit this.

CONTEXT_OVERFLOW_WARNING_THRESHOLD = 100
# Why 100: Normal workflows produce 15-75 approved papers. Exceeding 100
# signals something unusual that deserves attention (but is not blocked).

# =============================================================================
# Multi-Model Configuration
# =============================================================================

DEFAULT_MODEL_ID = settings.llm_model_id
# Canonical model ID for per-request routing (e.g. "openai:gpt-4o", "ollama:llama3.1:8b").
# Empty string means use legacy env vars (LLM_BASE_URL + LLM_MODEL).

OLLAMA_BASE_URL = settings.ollama_base_url
OLLAMA_API_KEY = settings.ollama_api_key

MODEL_REGISTRY_JSON = settings.model_registry_json
# Optional JSON string defining available models. If empty, auto-detected from env vars.

MODEL_CONFIG_PATH = settings.model_config_path
# Path to YAML model configuration file. If set and file exists, takes priority
# over MODEL_REGISTRY JSON and auto-detected env vars.
# Example: MODEL_CONFIG_PATH=config/models.yaml

# =============================================================================
# PDF Object Storage (MinIO + Redis)
# =============================================================================

MINIO_ENDPOINT = settings.minio_endpoint
# Why localhost:9000: Matches Docker Compose MinIO API binding and keeps local
# development zero-config. Production can override with an internal endpoint.

MINIO_ACCESS_KEY = settings.minio_access_key
# Why minioadmin default: MinIO's standard local bootstrap credential keeps
# onboarding simple. Must be overridden in production deployments.

MINIO_SECRET_KEY = settings.minio_secret_key
# Why minioadmin default: Pairs with local dev defaults for frictionless startup;
# production environments should always inject a strong secret.

MINIO_SECURE = settings.minio_secure
# Why false by default: Local Docker networking commonly uses HTTP without TLS.
# This flag allows strict HTTPS enablement in staging/production.

MINIO_BUCKET_RAW = settings.minio_bucket_raw
# Why rag-raw: Separates original PDFs from downstream artifacts for traceability
# and reprocessing workflows.

MINIO_BUCKET_PROCESSED = settings.minio_bucket_processed
# Why rag-processed: Dedicated bucket avoids mixing transformed outputs with raw
# source files and simplifies lifecycle/access policy tuning.

MINIO_BUCKET_TMP = settings.minio_bucket_tmp
# Why rag-tmp: Isolates ephemeral artifacts so they can be aggressively expired
# without affecting durable raw/processed research data.

REDIS_HOST = settings.redis_host
# Why localhost: Supports default local deployment where Redis runs in the same
# Docker network or host machine; can be overridden for managed Redis.

REDIS_PORT = settings.redis_port
# Why 6379: Standard Redis port minimizes configuration overhead and matches the
# official container defaults.

REDIS_DB = settings.redis_db
# Why DB 0: Redis default logical database keeps compatibility with most clients;
# bounded range prevents invalid DB indices.

REDIS_PASSWORD = settings.redis_password
# Why empty default: Local development Redis commonly runs without auth. Secrets
# should be injected in production where Redis is network-exposed.

REDIS_PDF_CACHE_TTL = settings.redis_pdf_cache_ttl
# Why 86400 seconds: 24-hour cache window balances hit rate for repeated PDF
# access against staleness and memory pressure.

PDF_DOWNLOAD_TIMEOUT = settings.pdf_download_timeout
# Why 30 seconds: Long enough for typical academic PDF downloads over moderate
# networks while preventing hung requests from stalling the pipeline.

PDF_MAX_SIZE_MB = settings.pdf_max_size_mb
# Why 50 MB: Covers most research PDFs while guarding against unusually large
# files that can degrade throughput and memory usage.

# =============================================================================
# PDF Parsing Configuration
# =============================================================================

PDF_EXTRACTION_TIMEOUT = 60
# Why 60: Large PDFs (100+ pages) can take 30-45s to parse. 60s provides buffer.

# =============================================================================
# Text Chunking Configuration
# =============================================================================

CHUNK_SIZE_TOKENS = 512
# Why 512: Balances context window usage vs semantic coherence.
# Embedding models typically support 512-8192 tokens. 512 is safe default.

CHUNK_OVERLAP_TOKENS = 50
# Why 50: ~10% overlap ensures context continuity across chunks.
# Prevents information loss at chunk boundaries.

TIKTOKEN_MODEL = "cl100k_base"
# Why cl100k_base: Standard for GPT-4 and most modern embedding models.
# Consistent token counting across pipeline.

# =============================================================================
# Embedding Configuration
# =============================================================================

EMBEDDING_MODEL = settings.embedding_model
# Why text-embedding-3-small: OpenAI's latest, 1536 dimensions, $0.02/1M tokens.
# Balances cost vs quality. Upgrade to text-embedding-3-large for higher accuracy.

EMBEDDING_DIMENSIONS = 1536
# Why 1536: Standard for text-embedding-3-small. Qdrant/Milvus support this.

EMBEDDING_BATCH_SIZE = 100
# Why 100: OpenAI allows up to 2048 inputs per request. 100 balances latency vs throughput.
# Reduces API calls while keeping request size manageable.

EMBEDDING_CACHE_TTL = 2592000  # 30 days in seconds
# Why 30 days: Embeddings are deterministic for same text+model.
# Long TTL reduces costs. Invalidate on model upgrade.

EMBEDDING_MAX_RETRIES = 3
# Why 3: Same as LLM_CONCURRENCY pattern. Handles transient API failures.

# =============================================================================
# PostgreSQL Configuration
# =============================================================================

POSTGRES_HOST = settings.postgres_host
POSTGRES_PORT = settings.postgres_port
POSTGRES_DB = settings.postgres_db
POSTGRES_USER = settings.postgres_user
POSTGRES_PASSWORD = settings.postgres_password


def get_postgres_url() -> str:
    return settings.get_postgres_url()


# =============================================================================
# Vector Store Configuration
# =============================================================================

QDRANT_HOST = settings.qdrant_host
QDRANT_PORT = settings.qdrant_port
QDRANT_COLLECTION_NAME = settings.qdrant_collection_name

VECTOR_SEARCH_LIMIT = 10
VECTOR_SEARCH_THRESHOLD = 0.7

# =============================================================================
# Vector Pipeline Feature Flag
# =============================================================================

VECTOR_PIPELINE_ENABLED = settings.vector_pipeline_enabled

# =============================================================================
# RAG Ingestion Gateway
# When RAG_GATEWAY_URL is set, extractor_agent delegates PDF ingestion to the
# Go gateway instead of running the inline Python pipeline. The gateway handles
# download → chunk → embed → index asynchronously with ~64KB peak memory per PDF.
# =============================================================================

RAG_GATEWAY_URL = settings.rag_gateway_url
RAG_GATEWAY_TIMEOUT = settings.rag_gateway_timeout
