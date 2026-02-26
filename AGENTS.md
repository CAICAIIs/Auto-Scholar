# AGENTS.md — auto-scholar

> Agentic coding guide for auto-scholar: FastAPI + LangGraph backend with Next.js 16 frontend.

**Generated:** 2026-02-26 | **Commit:** 129b58d | **Branch:** main

## Quick Commands

```bash
# Backend
uv sync --extra dev                        # Install deps
find backend -name '*.py' -exec python -m py_compile {} +  # Compile check all
python -m py_compile backend/schemas.py      # Compile check single file
ruff check backend/                          # Lint all
ruff check backend/main.py                   # Lint single file
ruff format backend/ --check                 # Check formatting
ruff format backend/                         # Auto-format

# Backend tests (pytest)
uv run pytest tests/ -v                             # Run all tests
uv run pytest tests/test_integration.py -v          # Run single file
uv run pytest tests/test_integration.py::test_full_workflow -v  # Run single test
uv run pytest tests/test_exporter.py::test_export_markdown -v   # Another example
uv run pytest -x                                    # Stop on first failure
uv run pytest -m "not slow"                         # Skip slow tests
uv run pytest -m "not integration"                  # Skip integration tests
uv run pytest --cov=backend tests/                  # With coverage

# Frontend
cd frontend && bun install                   # Install deps
cd frontend && bun run build                 # Production build
cd frontend && bun x tsc --noEmit            # Type check
cd frontend && bun run lint                  # ESLint

# Frontend tests (vitest + playwright)
cd frontend && bun test                      # Run unit tests (vitest)
cd frontend && bun test src/__tests__/store.test.ts  # Single test file
cd frontend && bun run test:e2e              # Run E2E tests (playwright)

# Docker
docker compose up --build                    # Full stack (backend:8000 + frontend:3000)

# DO NOT run these from agents (long-running):
# uvicorn backend.main:app --reload --port 8000
# cd frontend && bun run dev
```

## Project Structure

```
auto-scholar/
├── backend/                    # FastAPI + LangGraph backend
│   ├── main.py            # REST endpoints (start, stream, approve, status, export, sessions)
│   ├── workflow.py        # LangGraph graph + QA retry router + reflection loop
│   ├── nodes.py           # 6 agent nodes (plan, search, extract, draft, QA, reflection) — 948 lines, largest file
│   ├── state.py           # AgentState TypedDict with Annotated reducers
│   ├── schemas.py         # Pydantic V2 models — single source of truth for 40+ types
│   ├── constants.py       # Config constants with trade-off rationale comments
│   ├── prompts.py         # Centralized LLM prompt templates
│   ├── config/
│   │   └── loader.py      # YAML model config loader with ${ENV_VAR:-default} substitution
│   ├── llm/
│   │   ├── router.py      # Task-aware model selection (scoring by reasoning/creativity/latency)
│   │   └── task_types.py  # TaskType enum + per-task requirements
│   ├── evaluation/        # 7-dimension evaluation framework (see backend/evaluation/AGENTS.md)
│   └── utils/
│       ├── llm_client.py  # AsyncOpenAI wrapper + multi-provider fallback chains
│       ├── scholar_api.py # Semantic Scholar + arXiv + PubMed clients (590 lines)
│       ├── event_queue.py # SSE debouncing engine (200ms window + semantic boundaries)
│       ├── exporter.py    # Markdown/DOCX export with 4 citation styles
│       ├── citations.py   # {cite:N} → [N] normalization
│       ├── claim_verifier.py  # Batch claim extraction + entailment verification
│       ├── source_tracker.py  # Circuit breaker for failed sources (3 fails = skip 2min)
│       ├── http_pool.py   # Connection pooling (limit=50, TTL=300s)
│       ├── fulltext_api.py    # Unpaywall + OpenAlex PDF URL resolution
│       ├── charts.py      # Matplotlib chart generation
│       └── logging.py     # JSON structured logging with thread_id context
├── config/
│   └── models.yaml        # Multi-model config (OpenAI, DeepSeek, Ollama) with capability scores
├── frontend/              # Next.js 16 + React 19
│   └── src/
│       ├── app/           # App router (page.tsx — 320 lines, layout.tsx)
│       ├── components/    # UI components (console/, workspace/, approval/, ui/)
│       ├── store/         # Zustand state (research.ts — 363 lines)
│       ├── lib/api/       # API client with SSE + REST
│       ├── i18n/          # Internationalization (en/zh) via next-intl
│       ├── types/         # TypeScript types mirroring backend schemas 1:1
│       └── __tests__/     # Vitest unit tests
├── tests/                 # Backend pytest tests (34 files, ~4300 lines)
├── .github/workflows/ci.yml  # 3 parallel jobs: lint, test (matrix 3.11/3.12), frontend
└── pyproject.toml         # Python >=3.11, pytest asyncio_mode=auto
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Add/modify workflow node | `backend/nodes.py` | 6 agents, uses prompts from `prompts.py` |
| Change workflow graph | `backend/workflow.py` | LangGraph StateGraph, `_qa_router` for retry logic |
| Add API endpoint | `backend/main.py` | FastAPI, all routes under `/api/` |
| Add/change data model | `backend/schemas.py` | Pydantic V2, then mirror in `frontend/src/types/index.ts` |
| Modify LLM prompts | `backend/prompts.py` | All templates centralized here |
| Tune constants | `backend/constants.py` | Each has rationale comment — read before changing |
| Add model provider | `config/models.yaml` + `backend/config/loader.py` | YAML with env var substitution |
| Change model routing | `backend/llm/router.py` + `task_types.py` | Scoring by task requirements |
| Add evaluation | `backend/evaluation/` | See `backend/evaluation/AGENTS.md` |
| Frontend state | `frontend/src/store/research.ts` | Zustand, sessionStorage persistence |
| API client | `frontend/src/lib/api/client.ts` | SSE + REST, 300s timeout |
| Add UI component | `frontend/src/components/` | `"use client"`, barrel exports via `index.ts` |
| i18n strings | `frontend/src/i18n/messages/{en,zh}.json` | Both locales required |

## Backend Code Style (Python)

### Imports
- Absolute imports only (`from backend.schemas import X`, never `from .schemas`)
- Order: stdlib → third-party → local. Blank line between groups.

### Type Annotations
- Python 3.11+ generics: `list[str]`, `dict[str, Any]`, not `List`, `Dict`
- Union syntax: `X | None`, not `Optional[X]`
- Annotate all function params and return types

### Naming
| Element | Convention | Example |
|---------|------------|---------|
| Classes | PascalCase | `PaperMetadata` |
| Functions/vars | snake_case | `search_papers` |
| Constants | UPPER_SNAKE | `SEMANTIC_SCHOLAR_URL` |
| Private | `_` prefix | `_fetch_page` |

### Ruff Configuration (ruff.toml)
- Line length: 100
- Enabled rule sets: `E` (pycodestyle errors), `F` (pyflakes), `W` (pycodestyle warnings), `I` (isort), `N` (pep8-naming), `UP` (pyupgrade)
- `E501` ignored (formatter handles line length)
- Indent style: spaces

### Async & Error Handling
- All network I/O MUST be async (`aiohttp`, not `requests`)
- Use `tenacity` `@retry` for transient failures:
  ```python
  @retry(wait=wait_exponential(min=2, max=10), stop=stop_after_attempt(3))
  ```
- Custom exceptions per module inheriting from base class
- Logging: `logger = logging.getLogger(__name__)`, use `%s` formatting

### Data Models
- Pydantic V2 `BaseModel` for all data structures
- LangGraph state: `TypedDict` with `Annotated` reducers
- `logs` field: `Annotated[list[str], operator.add]` for append

## Frontend Code Style (TypeScript)

### Imports
- Use `@/` path alias for src imports
- Order: react → third-party → local components → local utils

### Components
- All components use `"use client"` directive (client components)
- Barrel exports via `index.ts` in feature directories
- Zustand for global state (`useResearchStore`)

### Naming
| Element | Convention | Example |
|---------|------------|---------|
| Components | PascalCase | `QueryInput` |
| Hooks | camelCase with `use` | `useResearchStore` |
| Files | kebab-case | `query-input.tsx` |
| Types | PascalCase | `PaperSource` |

### Hydration Safety
- Use `suppressHydrationWarning` on SVGs (browser extensions modify them)
- Use `useState` + `useEffect` pattern for client-only state

## Environment Variables

| Variable | Required | Default |
|----------|----------|---------|
| `LLM_API_KEY` | Yes | — |
| `LLM_BASE_URL` | No | `https://api.openai.com/v1` |
| `LLM_MODEL` | No | `gpt-4o` |
| `MODEL_CONFIG_PATH` | No | `config/models.yaml` |
| `LLM_MODEL_ID` | No | — (format: `provider:model_name`) |
| `LLM_CONCURRENCY` | No | `2` (clamped 1-20) |
| `CLAIM_VERIFICATION_CONCURRENCY` | No | `2` (clamped 1-20) |
| `CLAIM_VERIFICATION_ENABLED` | No | `true` |
| `DEEPSEEK_API_KEY` | No | — |
| `OLLAMA_BASE_URL` | No | `http://localhost:11434/v1` |
| `SEMANTIC_SCHOLAR_API_KEY` | No | — |
| `NEXT_PUBLIC_API_URL` | No | `http://localhost:8000` |

## Key Architecture Patterns

1. **LangGraph Workflow**: 6 nodes (plan → search → extract → draft → QA → reflection) with human-in-the-loop at extract node via `interrupt_before`. QA retry router (`_qa_router`) loops back to writer on citation errors (max 3 retries). Reflection agent provides structural feedback.

2. **Citation System**: LLM uses `{cite:N}` placeholders (N = paper index). Backend replaces with `[N]` format. QA validates citations from content, never trusts LLM's `cited_paper_ids`. Claim verification (97.3% accuracy) via batch extraction + entailment.

3. **AI Runtime Layer**: Task-aware model routing in `llm/router.py` scores models by reasoning/creativity/latency per task type. Fallback chains auto-retry on failure. Config via `config/models.yaml` with `${ENV_VAR:-default}` substitution.

4. **SSE Streaming**: `StreamingEventQueue` with debouncing (92% network reduction). 200ms time window + semantic boundary detection (。！？.!?) + newline. Events: `{node, log}`, `{event: "done"}`, `{event: "error"}`.

5. **State Persistence**: `AsyncSqliteSaver` with `thread_id` in config. Resume via `ainvoke(None, config)`.

6. **Multi-Source Search**: Parallel queries to Semantic Scholar + arXiv + PubMed with deduplication by normalized title. Circuit breaker via `source_tracker.py` (3 failures = skip 2min).

7. **Type Mirroring**: `backend/schemas.py` (Pydantic) is single source of truth. `frontend/src/types/index.ts` mirrors 1:1. When adding/changing a model, update both files.

## Testing Patterns

### Backend (pytest)
- `asyncio_mode = "auto"` in pyproject.toml (no `@pytest.mark.asyncio` needed)
- Markers: `@pytest.mark.slow`, `@pytest.mark.integration` — skip with `-m "not slow"` or `-m "not integration"`
- Use fixtures from `conftest.py` for mocking external APIs:
  ```python
  async def test_feature(mock_external_apis_success):
      # External APIs are mocked
  ```
- Test DB: `test_checkpoints_{uuid}.db` (auto-cleaned)
- Coverage: `uv run pytest --cov=backend tests/` — branch coverage enabled, excludes `__init__.py`

### Frontend (vitest)
- jsdom environment, globals enabled
- `@testing-library/react` for component tests
- Cleanup runs automatically via setup.ts

### E2E (playwright)
- `bun run test:e2e` for headless
- `bun run test:e2e:ui` for UI mode

## Pre-Commit Checklist (MANDATORY)

**Before EVERY commit, you MUST run these checks and ensure they pass:**

```bash
# Backend (ALL must pass)
ruff check backend/                          # Lint - must show "All checks passed!"
ruff format backend/ --check                 # Format - must show "X files already formatted"
find backend -name '*.py' -exec python -m py_compile {} +  # Compile check

# Frontend (ALL must pass)
cd frontend && bun x tsc --noEmit            # Type check - must exit 0
cd frontend && bun run lint                  # ESLint - warnings OK, errors NOT OK
```

**If any check fails:**
1. Fix the issue (e.g., `ruff format backend/` to auto-format)
2. Re-run the check to confirm it passes
3. Only then proceed with `git add` and `git commit`

**CI will reject commits that fail these checks. Save time by running locally first.**

## Pre-Commit Hooks

Pre-commit is configured (`.pre-commit-config.yaml`) with:
- `ruff` — lint with `--fix` (auto-fixes safe issues)
- `ruff-format` — auto-format
- `mypy` — type checking with `--ignore-missing-imports`

Install hooks: `pre-commit install`. They run automatically on `git commit`.
If a hook modifies files, re-stage and commit again.

## Commit Message Rules (MANDATORY)

- NEVER add "Ultraworked with Sisyphus" or any similar agent attribution footer to commit messages.
- NEVER add `Co-authored-by: Sisyphus` or any AI agent co-author trailers.
- NEVER add any third-party branding, links, or promotional text to commit messages.
- Commit messages must contain ONLY: subject line + optional body describing the change. Nothing else.
