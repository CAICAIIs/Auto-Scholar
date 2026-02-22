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

DRAFT_BASE_TOKENS = 1000
# Base token allocation for draft generation (title, structure, intro/conclusion)

DRAFT_TOKENS_PER_PAPER = 150
# Why 150: Each paper needs ~100-150 tokens for proper citation and discussion.
# Ensures adequate coverage without excessive length.

DRAFT_MAX_TOKENS = 4000
# Why 4000: Balances comprehensive review with cost/latency. Typical academic
# review section is 2000-4000 words. Sufficient for 4-6 thematic sections.

def get_draft_max_tokens(num_papers: int) -> int:
    """Calculate max tokens for draft based on paper count."""
    return min(DRAFT_MAX_TOKENS, DRAFT_BASE_TOKENS + num_papers * DRAFT_TOKENS_PER_PAPER)
