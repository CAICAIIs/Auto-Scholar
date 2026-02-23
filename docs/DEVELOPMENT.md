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

## Project Conventions

- Backend imports: stdlib -> third-party -> local
- Absolute imports for backend modules (`from backend...`)
- Python typing with built-in generics (`list[str]`, `dict[str, Any]`)
- Frontend import aliases via `@/`
- Keep docs and API contracts synchronized in the same PR
