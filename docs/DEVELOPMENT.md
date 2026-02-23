# Development Guide

## Prerequisites

- Python 3.11+
- uv
- bun

Optional but recommended:

- `SEMANTIC_SCHOLAR_API_KEY` for higher API limits
- OpenAI-compatible endpoint via `LLM_BASE_URL`

## Environment Setup

### 1) Install dependencies

```bash
uv sync --extra dev
cd frontend && bun install && cd ..
```

### 2) Configure environment variables

Create `.env` in project root:

```env
LLM_API_KEY=your-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o
SEMANTIC_SCHOLAR_API_KEY=optional
NEXT_PUBLIC_API_URL=http://localhost:8000

# Optional - LLM concurrency for parallel operations
# Default: 2 (safe for free/low-tier API keys)
# Recommended: 2-4 for free tier, 4-8 for paid tier
# Higher values improve performance but may trigger rate limits
LLM_CONCURRENCY=2

# Optional - claim verification concurrency
# Default: 2 (safe for free/low-tier API keys)
# Recommended: 2-4 for free tier, 4-8 for paid tier
CLAIM_VERIFICATION_CONCURRENCY=2
```

### Performance Tuning Guidance

**LLM Concurrency (`LLM_CONCURRENCY`)**
- **Free/Low-tier OpenAI**: Use 2-4 (default is 2)
  - Higher values may trigger 429 rate limit errors
  - Recommended: Start with 2, increase gradually to 4 if rate limits don't occur
- **Paid/Team-tier OpenAI**: Use 4-8
  - Higher tiers allow more concurrent requests
  - Recommended: 4-6 for balanced performance, up to 8 for maximum throughput
- **DeepSeek/Zhipu APIs**: Check provider-specific rate limits
  - May have lower limits than OpenAI
  - Start conservative, monitor logs for 429 errors

**Claim Verification Concurrency (`CLAIM_VERIFICATION_CONCURRENCY`)**
- Follows same guidance as `LLM_CONCURRENCY`
- Lower values (2-4) reduce rate limit risk
- Higher values (4-8) improve critic_agent speed

## Run Locally

### Backend

```bash
uv run uvicorn backend.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
bun run dev
```

## Quality Checks (Before PR)

Run all checks and ensure they pass.

### Backend

```bash
ruff check backend/
ruff format backend/ --check
find backend -name '*.py' -exec python -m py_compile {} +
```

### Frontend

```bash
cd frontend && bun x tsc --noEmit
cd frontend && bun run lint
```

## Test Commands

### Backend tests

```bash
uv run pytest tests/ -v
uv run pytest tests/test_integration.py -v
uv run pytest tests/test_exporter.py::test_export_markdown -v
```

### Frontend tests

```bash
cd frontend && bun test
cd frontend && bun run test:e2e
```

## Common Developer Workflows

### Add or update backend API

1. Update models in `backend/schemas.py` if contract changes
2. Implement route behavior in `backend/main.py`
3. Add/adjust tests in `tests/`
4. Update `docs/API.md`

### Modify workflow behavior

1. Adjust node logic in `backend/nodes.py`
2. Update routing/interrupt/retry in `backend/workflow.py`
3. Verify session resume behavior (`/api/research/status`, `/sessions`)
4. Add regression tests for changed flow

### Update frontend workflow UX

1. Extend store state in `frontend/src/store/research.ts`
2. Wire API calls in `frontend/src/lib/api/`
3. Reflect state in console/workspace components
4. Add vitest coverage in `frontend/src/__tests__/`

## Sprint 3: Performance Validation

### Performance Benchmarking

**Workflow Benchmark Script** (`tests/benchmark_workflow.py`)

Measures end-to-end workflow performance including:
- Per-node timing breakdown (planner, retriever, extractor, writer, critic)
- LLM call estimation
- Total workflow time

**Usage:**

```bash
# Single benchmark run
python tests/benchmark_workflow.py --query "transformer architecture in NLP" --papers 3

# Multiple iterations for consistency
python tests/benchmark_workflow.py --query "deep learning for medical imaging" --iterations 3

# Compare concurrency configurations
python tests/benchmark_workflow.py --query "reinforcement learning" --compare --papers 3
```

**Requirements:**
- Backend must be running (`uvicorn backend.main:app --reload --port 8000`)
- Valid `LLM_API_KEY` configured in `.env`

**Expected Results:**
- Baseline (LLM_CONCURRENCY=2): ~45s for 3 papers, ~60-80s for 10 papers
- Optimized (LLM_CONCURRENCY=4): ~30s for 3 papers, ~40-50s for 10 papers

### Quality Regression Testing

**Citation Validation Script** (`tests/validate_citations.py`)

Validates citation accuracy across multiple research topics to ensure optimization work doesn't degrade quality.

**Usage:**

```bash
# Manual validation on 3 topics (original baseline)
python tests/validate_citations.py

# Regression testing against previous session
python tests/validate_citations.py --compare <session_id>
```

**Success Criteria:**
- Citation accuracy ≥ 97.0% (maintained from 97.3% baseline)
- No increase in hallucinated citations
- Citation index errors remain minimal

### Performance Targets

| Metric | Baseline | Target | Status |
|--------|----------|--------|--------|
| 10-paper workflow time | 50-95s | 35-65s | ✅ Implemented |
| LLM call count (10 papers) | ~26-36 | ~20-28 | ✅ Achieved |
| Citation accuracy | 97.3% | ≥97.0% | ✅ Maintained |

### Quality Guards

- **No regression in `tests/test_claim_verification.py`**: All existing tests must pass
- **No regression in `tests/test_integration.py`**: End-to-end workflows remain functional
- **Citation accuracy ≥ 97%**: Verified by manual validation on 3 topics

### Reliability Guards

- **429 error handling**: RateLimitError properly retried with exponential backoff (implemented in `llm_client.py`)
- **Batch extraction fallback**: Per-section fallback activated on batch failure (implemented in `claim_verifier.py`)
- **Fulltext enrichment merge**: Tested with edge cases (papers with/without PDFs) (test_extractor_parallel.py)

## Project Conventions

- Backend imports: stdlib -> third-party -> local
- Absolute imports for backend modules (`from backend...`)
- Python typing with built-in generics (`list[str]`, `dict[str, Any]`)
- Frontend import aliases via `@/`
- Keep docs and API contracts synchronized in the same PR
