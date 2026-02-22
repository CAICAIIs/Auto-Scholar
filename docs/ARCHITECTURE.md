# Architecture

## Overview

Auto-Scholar is a full-stack system for generating structured literature reviews with citation validation and a human approval step.

- Backend: FastAPI + LangGraph + SQLite checkpoint persistence
- Frontend: Next.js 16 + React 19 + Zustand + next-intl
- Main flow: `plan -> retrieve -> approve(interrupt) -> extract -> write -> QA`

## High-Level Components

### Backend

- `backend/main.py`: FastAPI app lifecycle, REST routes, SSE streaming, export/session APIs
- `backend/workflow.py`: LangGraph construction, retry router, interrupt configuration
- `backend/nodes.py`: 5 core agents
  - `planner_agent`: query decomposition and keyword generation
  - `retriever_agent`: multi-source academic search with deduplication
  - `extractor_agent`: contribution extraction and structured fields
  - `writer_agent`: outline + section drafting
  - `critic_agent`: citation QA and retry trigger
- `backend/state.py`: `AgentState` TypedDict with append reducers (`logs`, `messages`, `agent_handoffs`)
- `backend/schemas.py`: Pydantic v2 contracts for APIs and internal models
- `backend/utils/`
  - `scholar_api.py`: Semantic Scholar / arXiv / PubMed clients
  - `llm_client.py`: structured LLM calls
  - `event_queue.py`: SSE debouncing queue
  - `exporter.py`: Markdown/DOCX export
  - `claim_verifier.py`: citation claim verification

### Frontend

- `frontend/src/app/`: app shell and page entry
- `frontend/src/components/`
  - `console/`: query input, status, logs, history
  - `approval/`: candidate paper review modal/table
  - `workspace/`: generated review renderer, citations, charts, comparison table
- `frontend/src/store/research.ts`: global workflow state (thread, papers, draft, logs)
- `frontend/src/lib/api/`: backend API client wrappers
- `frontend/src/i18n/`: en/zh message catalogs

## Workflow and Control Flow

## 1) Start

`POST /api/research/start`

- Creates `thread_id`
- Initializes LangGraph state
- Runs until interrupt point (`extractor_agent`) to wait for human paper approval

## 2) Stream progress

`GET /api/research/stream/{thread_id}`

- Streams per-node logs via SSE
- Uses `StreamingEventQueue` to reduce network chatter through debounce + boundary flush

## 3) Approve and continue

`POST /api/research/approve`

- Marks candidate papers as approved
- Resumes graph execution from interrupt
- Produces `final_draft` if QA passes (or after retry limit)

## 4) Continue conversation

`POST /api/research/continue`

- Supports follow-up modifications to an existing draft
- Sets `is_continuation=True` and re-enters at writer path

## 5) Evaluate and export

- `GET /api/research/evaluate/{thread_id}`: quality metrics and evaluation report
- `POST /api/research/export`: Markdown/DOCX export with citation style

## Human-in-the-Loop and QA Retry

- Graph compile option `interrupt_before=["extractor_agent"]` enforces explicit user approval before extraction.
- `critic_agent` writes `qa_errors`; router behavior:
  - no errors -> end
  - errors and `retry_count < 3` -> back to `writer_agent`
  - retries exhausted -> end with latest draft

## Persistence Model

- Checkpointer: `AsyncSqliteSaver`
- Config key: `configurable.thread_id`
- State can be resumed using `ainvoke(None, config)`
- Session endpoints list and inspect persisted threads from checkpoint history

## Data and Citation Model

- `PaperMetadata`: unified schema for all paper sources
- Draft sections initially use `{cite:N}` placeholders
- Backend post-processes to `[N]` and maps to `cited_paper_ids`
- QA checks citation existence/coverage and optional claim verification summary

## Reliability and Performance

- Async-first external I/O (`aiohttp`)
- Timeout guard for long workflow operations (`WORKFLOW_TIMEOUT_SECONDS`)
- Retry strategy in API client layer (tenacity)
- Concurrency controls for LLM extraction and fulltext enrichment
- SSE debouncing to reduce request frequency and improve UI smoothness
