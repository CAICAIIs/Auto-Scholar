"""Configuration constants with trade-off documentation.

Each constant has a rationale explaining why this specific value was chosen.
This enables informed discussion during code reviews and interviews.
"""

# =============================================================================
# Search Configuration
# =============================================================================

MAX_KEYWORDS = 5
# Why 5: LLM generates 3-5 keywords covering core concept + methodology + application.
# >5 introduces noise (overly broad terms), <3 insufficient coverage.

PAPERS_PER_QUERY = 10
# Why 10: Semantic Scholar returns up to 100, but top 10 have highest relevance.
# 5 keywords × 10 papers = 50 candidates, ~20-30 after dedup. Sufficient for review.

# =============================================================================
# Concurrency Limits
# =============================================================================

LLM_CONCURRENCY = 2
# Why 2: OpenAI free/low-tier limits ~3 RPM. Concurrency=2 avoids rate limits
# while being 2x faster than sequential. Increase for higher-tier API keys.

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
DRAFT_TOKENS_PER_PAPER = 200
DRAFT_MAX_TOKENS = 8000


def get_draft_max_tokens(num_papers: int) -> int:
    return min(DRAFT_MAX_TOKENS, DRAFT_BASE_TOKENS + num_papers * DRAFT_TOKENS_PER_PAPER)


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

CLAIM_VERIFICATION_CONCURRENCY = 2
# Why 2: Same as LLM_CONCURRENCY. Each claim verification is an LLM call.
# Keeps within rate limits while parallelizing verification.

CLAIM_VERIFICATION_ENABLED = True
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

CONTEXT_TOKEN_BUDGET = 12000
# Why 12000: Measured ~177 tokens/paper (8-dimension structured info).
# 12000 tokens ≈ 67 papers. Leaves headroom for system prompt + output tokens
# within 128K context window. Covers 3-source × 5-keyword scenarios comfortably.

CONTEXT_TOKENS_PER_PAPER_ESTIMATE = 180
# Why 180: Average across papers with full structured_contribution (8 fields).
# Papers with only abstract fallback are shorter (~100 tokens).
# Used as fallback when per-paper estimation is unavailable.

CONTEXT_MAX_PAPERS = 60
# Why 60: Hard ceiling before any token estimation. At ~180 tokens/paper,
# 60 papers ≈ 10,800 tokens (within 12K budget). Prevents pathological cases
# where token estimation underestimates and context explodes.

CONTEXT_OVERFLOW_WARNING_THRESHOLD = 30
# Why 30: Log a warning when paper count exceeds this. Normal single-source
# queries yield 20-30 papers. Exceeding 30 signals multi-source or multi-turn
# accumulation that may need attention.
