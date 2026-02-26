# API Reference

Base URL (local): `http://localhost:8000`

## Research Workflow

### POST /api/research/start

Start a new research session.

Request body:

- `query` (string, required)
- `language` (string, optional, default `en`)
- `sources` (array, optional): `semantic_scholar | arxiv | pubmed`
- `model_id` (string, optional): Model to use (e.g., `openai:gpt-4o`)

Response:

- `thread_id`
- `candidate_papers` (initial search results)
- `logs`

### GET /api/research/stream/{thread_id}

Stream workflow logs via SSE.

Event payloads include:

- `{ "node": "planner_agent", "log": "..." }`
- `{ "event": "cost_update", "node": "extraction", "total_cost_usd": 0.045 }`
- `{ "event": "draft_token", "token": "..." }`
- `{ "event": "done" }`
- `{ "event": "error", "detail": "..." }`

### POST /api/research/approve

Approve selected papers and resume from interrupt point.

Request body:

- `thread_id` (string)
- `paper_ids` (string[])

Response:

- `thread_id`
- `final_draft` (nullable)
- `approved_count`
- `logs`

### POST /api/research/continue

Continue an existing session with follow-up instructions.

Request body:

- `thread_id` (string)
- `message` (string)
- `model_id` (string, optional): Model to use (e.g., `openai:gpt-4o`)

Response:

- `thread_id`
- `message` (assistant summary message)
- `final_draft` (nullable)
- `candidate_papers`
- `logs`

### GET /api/research/status/{thread_id}

Get current workflow state.

Response fields:

- `next_nodes`
- `logs`
- `has_draft`
- `candidate_count`
- `approved_count`

## Export and Visualization

### POST /api/research/export

Export review draft to Markdown or DOCX.

Query params:

- `format`: `markdown | docx`
- `citation_style`: `apa | mla | ieee | gb-t7714`

Request body:

- `draft`
- `papers`

### POST /api/research/charts

Generate chart assets from selected papers.

Request body:

- `papers`

Response:

- `year_trend`
- `source_distribution`
- `author_frequency`

## Session Management

### GET /api/research/sessions

List sessions from checkpoint storage.

Query params:

- `limit` (default 50, max 100)

### GET /api/research/sessions/{thread_id}

Get full session detail, including:

- candidate/approved papers
- final draft
- logs
- conversation messages

## Model Management

### GET /api/models

List all enabled model configurations.

Response: array of `ModelConfig` objects with `id`, `provider`, `display_name`, `cost_tier`, `is_local`, etc.

## Evaluation and Ratings

### GET /api/research/evaluate/{thread_id}

Run evaluation for a completed draft.

### POST /api/ratings

Submit a human rating.

### GET /api/ratings/{thread_id}

Get ratings for a specific session.

## Error Semantics

- `404`: unknown `thread_id` / session not found
- `400`: invalid workflow state (e.g., approving when not at interrupt point)
- `504`: workflow timeout
- `500`: internal execution errors
