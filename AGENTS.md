# AGENTS.md — auto-scholar

> Agentic coding guide for auto-scholar: FastAPI + LangGraph backend with Next.js 16 frontend.

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
uv run pytest -m                          # Skip slow tests
uv run pytest -m "not integration"                  # Skip integration tests
uv run pytest --cov=backend tests/                  # With coverage

# Frontend
cd frontend && bun install                   # Install deps
cd frontend && bun run build                 # Production build
cd frontend && bun x tsc --noEmit            # Type check
cd frontend && bun run lint                  # ESLint

# Frontend tests (vitest + playwright)
cd frontend && bun test                      # Run unit tests (vitest)
cd frontend && bun test src/__tests__/store.test. Single test file
cd frontend && bun run test:e2e              # Run E2E tests (playwright)

# DO NOT run these from agents (long-running):
# uvicorn backend.main:app --reload --port 8000
# cd frontend && bun run dev
```

## Project Structure

```
auto-scholar/
├── backend/                    # FastAPI + LangGraph backend
│   ├── main.py            # REST endpoints (start, stream, approve, status, export, sessions)
│   ├── workflow.py        # LangGraph graph + QA retry router
│   ├── nodes.py           # 5 workflow nodes (plan, search, extract, draft, QA)
│   ├── state.py           # AgentState TypedDict
│   ├── schemas.py         # Pydantic V2 models
│   └── utils/
│       ├── llm_client.py  # AsyncOpenAI wrapper (structured outputs)
│       ├── scholar_api.py # Semantic Scholar + arXiv + PubMed clients
│       ├── event_queue.py # SSE debouncing engine
│       └── exporter.py    # Markdown/DOCX export
├── frontend/              # Next.js 16 + React 19
│   └── src/
│       ├── app/           # App router (page.tsx, layout.tsx)
│       ├── components/    # UI components (console/, workspace/, approval/, ui/)
│       ├── store/         # Zustand state (research.ts)
│       ├── lib/api/       # API client
│       ├── i18n/          # Internationalization (en/zh)
│       └── __tests__/     # Vitest unit tests
├── tests/                 # Backend pytest tests
└── pyproject.toml         # Python >=3.11, pytest asyncio_mode=auto
```

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
| `SEMANTIC_SCHOLAR_API_KEY` | No | — |
| `NEXT_PUBLIC_API_URL` | No | `http://localhost:8000` |

## Key Architecture Patterns

1. **LangGraph Workflow**: 5 nodes (plan → search → extract → draft → QA) with human-in-the-loop at extract node via `interrupt_before`

2. **Citation System**: LLM uses `{cite:N}` placeholders (N = paper index). Backend replaces with `[N]` format. QA validates citations from content, never trusts LLM's `cited_paper_ids`.

3. **SSE Streaming**: `StreamingEventQueue` with debouncing (85-98% network reduction). Events: `{node, log}`, `{event: "done"}`, `{event: "error"}`

4. **State Persistence**: `AsyncSqliteSaver` with `thread_id` in config. Resume via `ainvoke(None, config)`.

5. **Multi-Source Search**: Parallel queries to Semantic Scholar + arXiv + PubMed with deduplication by normalized title.

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

When the Write or Edit tool has content size limits, always comply silently. Never suggest bypassing these limits via alternative tools. Never ask the user whether to switch approaches. Complete all chunked operations without commentary.

## Commit Message Rules (MANDATORY)

- NEVER add "Ultraworked with Sisyphus" or any similar agent attribution footer to commit messages.
- NEVER add `Co-authored-by: Sisyphus` or any AI agent co-author trailers.
- NEVER add any third-party branding, links, or promotional text to commit messages.
- Commit messages must contain ONLY: subject line + optional body describing the change. Nothing else.
