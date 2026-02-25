"""Configuration constants with trade-off documentation.

Each constant has a rationale explaining why this specific value was chosen.
This enables informed discussion during code reviews and interviews.
"""

import os

# =============================================================================
# Environment Variable Helpers
# =============================================================================


def _parse_int_env(name: str, default: int, min_val: int, max_val: int) -> int:
    """Parse an integer environment variable with bounds clamping.

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

LLM_CONCURRENCY = _parse_int_env("LLM_CONCURRENCY", default=2, min_val=1, max_val=20)
# Why 2: OpenAI free/low-tier limits ~3 RPM. Concurrency=2 avoids rate limits
# while being 2x faster than sequential. Increase for higher-tier API keys.
# Configurable via LLM_CONCURRENCY env var (clamped to 1-20).

LLM_DEFAULT_MAX_TOKENS = 8192
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

# =============================================================================
# Claim Verification Configuration
# =============================================================================

CLAIM_VERIFICATION_CONCURRENCY = _parse_int_env(
    "CLAIM_VERIFICATION_CONCURRENCY", default=2, min_val=1, max_val=20
)
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
CLAIM_VERIFICATION_ENABLED = os.getenv("CLAIM_VERIFICATION_ENABLED", "true").lower() == "true"
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

DEFAULT_MODEL_ID = os.getenv("LLM_MODEL_ID", "")
# Canonical model ID for per-request routing (e.g. "openai:gpt-4o", "ollama:llama3.1:8b").
# Empty string means use legacy env vars (LLM_BASE_URL + LLM_MODEL).

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_API_KEY = "ollama"

MODEL_REGISTRY_JSON = os.getenv("MODEL_REGISTRY", "")
# Optional JSON string defining available models. If empty, auto-detected from env vars.
