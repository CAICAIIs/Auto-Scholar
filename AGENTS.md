# AGENTS.md — auto-scholar

> Agentic coding guide for auto-scholar: FastAPI + LangGraph backend with Next.js 16 frontend.

## Quick Commands

```bash
# Backend
pip install -r requirements.txt              # Install deps
find app -name '*.py' -exec python -m py_compile {} +  # Compile check all
python -m py_compile app/schemas.py          # Compile check single file

# Backend tests (pytest)
pytest tests/ -v                             # Run all tests
pytest tests/test_integration.py -v          # Run single file
pytest tests/test_integration.py::test_full_workflow -v  # Run single test
pytest -x                                    # Stop on first failure

# Frontend
cd frontend && npm install                   # Install deps
cd frontend && npx tsc --noEmit              # Type check
cd frontend && npm run lint                  # ESLint

# Frontend tests (vitest + playwright)
cd frontend && npm test                      # Run unit tests (vitest)
cd frontend && npm test -- src/__tests__/store.test.ts  # Single test file
cd frontend && npm run test:e2e              # Run E2E tests (playwright)

# DO NOT run these from agents (long-running):
# uvicorn app.main:app --reload --port 8000
# cd frontend && npm run dev
```

## Project Structure

```
auto-scholar/
├── app/                    # FastAPI + LangGraph backend
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
- Absolute imports only (`from app.schemas import X`, never `from .schemas`)
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
- Use fixtures from `conftest.py` for mocking external APIs:
  ```python
  async def test_feature(mock_external_apis_success):
      # External APIs are mocked
  ```
- Test DB: `test_checkpoints_{uuid}.db` (auto-cleaned)

### Frontend (vitest)
- jsdom environment, globals enabled
- `@testing-library/react` for component tests
- Cleanup runs automatically via setup.ts

### E2E (playwright)
- `npm run test:e2e` for headless
- `npm run test:e2e:ui` for UI mode
