# Auto-Scholar

AI-powered academic literature review generator with human-in-the-loop workflow.

**[中文文档](README_zh.md)** | English

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-purple.svg)](https://github.com/langchain-ai/langgraph)
[![Next.js](https://img.shields.io/badge/Next.js-16+-black.svg)](https://nextjs.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## What is Auto-Scholar?

Auto-Scholar helps researchers quickly generate structured literature reviews. Enter a research topic, review candidate papers, and get a well-cited academic review in minutes.

**Key Features:**
- **Smart Paper Search**: Automatically generates search keywords and finds relevant papers from Semantic Scholar, arXiv, and PubMed
- **AI Runtime Layer**: Task-aware model routing automatically selects the optimal model for each task, with multi-layer fallback support
- **Multi-Model Support**: Supports OpenAI, DeepSeek, Ollama (local), and other LLM providers
- **YAML Model Configuration**: Flexibly configure model capability scores and cost tiers via `config/models.yaml`
- **Real-Time Cost Tracking**: Break down LLM usage costs by task type with USD real-time display
- **Human-in-the-Loop**: Review and approve papers before they're included in your review
- **Anti-Hallucination QA**: Validates all citations exist and are properly referenced
- **Bilingual Support**: Generate reviews in English or Chinese, with UI in both languages
- **Real-time Progress**: Watch the AI work with live streaming logs

## Quick Start

### Prerequisites

- Python 3.11+
- uv
- bun
- OpenAI API key (or compatible endpoint like DeepSeek/Zhipu)

### 1. Clone and Install

```bash
git clone https://github.com/CAICAIIs/Auto-Scholar.git
cd Auto-Scholar

# Backend
uv sync --extra dev

# Frontend
cd frontend && bun install && cd ..
```

### 2. Configure Environment

Create `.env` file in project root:

```env
# Required
LLM_API_KEY=your-openai-api-key

# Optional - for compatible APIs (DeepSeek, Zhipu, etc.)
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o

# Optional - increases Semantic Scholar rate limits
SEMANTIC_SCHOLAR_API_KEY=your-key

# Optional - LLM concurrency for parallel operations
# Default: 2 (safe for free/low-tier API keys)
# Recommended: 2-4 for free tier, 4-8 for paid tier
# Higher values improve performance but may trigger rate limits
LLM_CONCURRENCY=2

# Optional - claim verification concurrency
# Default: 2 (safe for free/low-tier API keys)
# Recommended: 2-4 for free tier, 4-8 for paid tier
CLAIM_VERIFICATION_CONCURRENCY=2

# Optional - disable claim verification for time-sensitive scenarios
# Default: true (maintains 97.3% citation accuracy)
# Set to "false" to disable and reduce workflow time
CLAIM_VERIFICATION_ENABLED=true

# === AI Runtime Layer Configuration ===

# Optional - Path to YAML model configuration file
# If set, takes priority over MODEL_REGISTRY and auto-detection
# Default: "" (auto-detect from environment variables)
MODEL_CONFIG_PATH=config/models.yaml

# Optional - JSON string defining available models (alternative to YAML)
# Example: MODEL_REGISTRY=[{"id":"openai:gpt-4o","provider":"openai",...}]
# Default: "" (auto-detect from environment variables)
MODEL_REGISTRY=

# Optional - Default model ID for per-request routing
# Format: "provider:model_name" (e.g., "openai:gpt-4o", "deepseek:deepseek-chat")
# If empty, uses legacy LLM_BASE_URL + LLM_MODEL as default
LLM_MODEL_ID=

# Optional - DeepSeek API configuration (auto-detected if set)
DEEPSEEK_API_KEY=your-deepseek-key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1

# Optional - Ollama local models (auto-detected if set)
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODELS=llama3.1:8b,mistral:7b
```

### 3. Start Services

**Terminal 1 - Backend:**
```bash
uv run uvicorn backend.main:app --reload --port 8000
```

**Terminal 2 - Frontend:**
```bash
cd frontend && bun run dev
```

### 4. Open Browser

Visit `http://localhost:3000` and start researching!

## Usage Guide

### Step 1: Enter Research Topic

Type your research topic in the query input. Examples:
- "transformer architecture in natural language processing"
- "deep learning for medical image analysis"
- "reinforcement learning in robotics"

### Step 2: Review Candidate Papers

The system will:
1. Generate 3-5 search keywords from your topic
2. Search Semantic Scholar, arXiv, and PubMed for relevant papers
3. Present candidate papers for your review

Select the papers you want included in your literature review.

### Step 3: Get Your Review

After approval, the system will:
1. Extract core contributions from each paper
2. Generate a structured literature review with proper citations
3. Validate all citations (auto-retry if issues found)

### Agent Console

The agent console shows real-time progress with live streaming logs:

- **Console Title**: "控制台" (Chinese) or "Console" (English)
- **Collapse/Expand**: Click the collapse button to minimize the console to a sidebar
- **Model Selection**: Choose the LLM model for generation (default: gpt-4o)
  - Displays cost tier (Low/Medium/High)
  - Shows local model indicator [Local] for Ollama models
  - Shows fallback chain indicators
- **Cost Tracking**: Real-time cost display in USD
  - Aggregated from all LLM calls
  - Persists in localStorage
  - Shows per-task breakdown in status bar
- **Language Controls**: Unified interface for language switching:
  - **界面**: Toggle between [中|EN] to switch UI language
  - **综述**: Toggle between [中|EN] to choose review generation language

**State Preservation:**
- Switching UI locale preserves all session data (threadId, draft, messages, logs)
- Uses sessionStorage to maintain state across page reloads
- Model selection persists via localStorage

**Auto-Regeneration:**
- When changing the output language, the review automatically regenerates in the new language
- State is preserved during regeneration with duplicate-request prevention

## Tech Stack

### Backend
- **FastAPI** - Async web framework
- **LangGraph** - Workflow orchestration with checkpointing
- **AI Runtime Layer** - Task-aware model routing with fallback chains
- **OpenAI** - LLM for keyword generation and review writing
- **aiohttp** - Async HTTP client for Semantic Scholar, arXiv, and PubMed
- **Pydantic** - Data validation and serialization
- **tenacity** - Retry logic for API calls

### Frontend
- **Next.js 16** - React framework
- **Zustand** - State management
- **next-intl** - Internationalization
- **Tailwind CSS** - Styling
- **react-markdown** - Review rendering
- **Radix UI** - Accessible components

## AI Runtime Layer

Auto-Scholar includes a task-aware AI runtime layer that optimizes model selection based on the specific task requirements.

### Task-Aware Model Routing

The system automatically selects the most appropriate model for each workflow task:

| Task Type | Requirements | Model Selection Criteria |
|-----------|-------------|------------------------|
| **Planning** | High reasoning, structured output | Prioritizes `reasoning_score`, requires `supports_structured_output` |
| **Extraction** | Structured output, cost-effective | Balances `cost_tier` and `latency_score` |
| **Writing** | Long context, creative | Requires `supports_long_context`, prioritizes `creativity_score` |
| **QA** | Structured output, low latency | Favors low `cost_tier`, high `latency_score` |
| **Reflection** | High reasoning, structured output | Similar to planning but with cost considerations |

### Multi-Model Support

Auto-Scholar supports multiple LLM providers and models through a flexible configuration system:

**Supported Providers:**
- OpenAI (GPT-4o, GPT-4o-mini)
- DeepSeek (DeepSeek Chat, DeepSeek Reasoner)
- Ollama (Local models)
- Custom providers (Any OpenAI-compatible endpoint)

**Model Configuration:**

Models are configured via YAML at `config/models.yaml`. Each model defines:
- `id`: Canonical identifier (e.g., `openai:gpt-4o`)
- `display_name`: Human-readable name for UI
- `provider`: Provider type
- `api_base` / `api_key_env`: Connection details
- **Capability scores** (1-10):
  - `reasoning_score`: Reasoning ability
  - `creativity_score`: Creative writing ability
  - `latency_score`: Speed (1=slow, 10=fast)
- **Flags:**
  - `supports_json_mode`: JSON response format
  - `supports_structured_output`: Reliable JSON generation
  - `supports_long_context`: ≥32K context window
- `cost_tier`: LOW, MEDIUM, or HIGH classification
- `max_output_tokens`: Maximum generation tokens

**Example Configuration:**

```yaml
models:
  - id: "openai:gpt-4o"
    provider: "openai"
    model_name: "gpt-4o"
    display_name: "GPT-4o (OpenAI)"
    api_base: "${LLM_BASE_URL:-https://api.openai.com/v1}"
    api_key_env: "LLM_API_KEY"
    supports_json_mode: true
    supports_structured_output: true
    max_output_tokens: 8192
    is_local: false
    max_context_tokens: 128000
    supports_long_context: true
    cost_tier: 3          # HIGH
    reasoning_score: 8
    creativity_score: 8
    latency_score: 6
```

**Environment Variables:**

```env
# YAML model configuration (takes priority)
MODEL_CONFIG_PATH=config/models.yaml

# Fallback: JSON-based registry
MODEL_REGISTRY=[{"id":"custom:model","provider":"custom",...}]

# Default model for requests without model_id
LLM_MODEL_ID=openai:gpt-4o

# Provider-specific keys (auto-detected if set)
DEEPSEEK_API_KEY=your-deepseek-key
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODELS=llama3.1:8b,mistral:7b
```

**Fallback Chains:**

When a model fails (rate limit, timeout, error), the runtime automatically tries the next best model in the fallback chain. Chains are generated based on task requirements and model capabilities.

**Client Caching:**

LLM clients are cached by `(base_url, api_key)` to avoid connection overhead across multiple requests.

### Cost Tracking

The system tracks LLM usage costs in real-time:

**Per-Task Breakdown:**
Costs are aggregated by task type (planning, extraction, writing, QA, reflection) for detailed analysis.

**Real-Time Updates:**
- SSE event: `{"event":"cost_update","node":"extraction","total_cost_usd":0.045}`
- Frontend displays cost in the agent console status bar
- Stored in Zustand state with localStorage persistence

**Cost Estimation:**
Uses provider-specific pricing models to convert token counts to USD. OpenAI and DeepSeek pricing is built-in; custom providers use fallback rates.

**Access:**
```python
from backend.evaluation.cost_tracker import get_total_cost_usd
total_cost = get_total_cost_usd()  # Returns float USD
```

## Performance

### Performance Targets

| Metric | Baseline | Target | Status |
|--------|----------|--------|--------|
| 10-paper workflow time | 50-95s | 35-65s | Implemented |
| LLM call count (10 papers) | ~26-36 | ~20-28 | Achieved |
| Citation accuracy | 97.3% | ≥97.0% | Maintained |

### Current Performance Metrics

| Metric | Value | Validation Method |
|--------|-------|-------------------|
| SSE Network Reduction | 92% | Benchmark test with 263 tokens → 21 flushes |
| Citation Accuracy | 97.3% | Manual validation of 37 citations across 3 topics |
| Max QA Retries | 3 | Configurable in workflow.py (`MAX_RETRY_COUNT`) |

### Performance Tuning

The following environment variables allow performance tuning for users with higher-tier API keys:

| Variable | Default | Recommended Values | Description |
|----------|----------|-------------------|-------------|
| `LLM_CONCURRENCY` | 2 | 2-4 (free tier), 4-8 (paid tier) | Concurrent LLM calls during extraction |
| `CLAIM_VERIFICATION_CONCURRENCY` | 2 | 2-4 (free tier), 4-8 (paid tier) | Concurrent claim verification calls |
| `CLAIM_VERIFICATION_ENABLED` | true | true (recommended), false (time-sensitive) | Enable/disable claim verification (maintains 97.3% accuracy when true) |

**Expected improvements with increased concurrency:**
- `LLM_CONCURRENCY=4`: ~50% reduction in extraction time (25-40s → 13-20s)
- `LLM_CONCURRENCY=4` + Phase 1.2 + Phase 2.1: 10-paper workflow 50-95s → 35-65s
- `CLAIM_VERIFICATION_ENABLED=false`: ~8-20s reduction in critic_agent time (trade-off: lower citation accuracy)

**Note:**
- Increasing concurrency may trigger rate limits on lower-tier API plans. Start with default values and increase gradually.
- Disabling claim verification (`CLAIM_VERIFICATION_ENABLED=false`) reduces workflow time but may decrease citation accuracy below 97.3%. Only use for time-sensitive scenarios where speed is more important than accuracy.

### Benchmark and Validation Tools

**Workflow Benchmark** (`tests/benchmark_workflow.py`):
- End-to-end performance measurement
- Concurrency comparison (baseline vs optimized)
- Per-node timing breakdown

**Citation Validation** (`tests/validate_citations.py`):
- Regression testing for citation accuracy
- Manual validation across multiple topics
- Batch validation support for continuous testing

**SSE Debouncing** (`tests/benchmark_sse.py`):
- Raw messages: 263 tokens
- After debounce: 21 network requests
- Compression ratio: 12.5x
- Mechanism: 200ms time window + semantic boundary detection (。！？.!?) + newline

## Testing

```bash
# Backend compile check
find backend -name '*.py' -exec python -m py_compile {} +

# Frontend type check
cd frontend && bun x tsc --noEmit

# Run tests
uv run pytest tests/ -v
```

## Documentation

- [Documentation Index](docs/README.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Development Guide](docs/DEVELOPMENT.md)
- [API Reference](docs/API.md)
- [Contributing](CONTRIBUTING.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Security Policy](SECURITY.md)

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

MIT License - see [LICENSE](LICENSE) for details.

## Acknowledgments

- [LangGraph](https://github.com/langchain-ai/langgraph) - Workflow orchestration
- [Semantic Scholar](https://www.semanticscholar.org/) - Academic paper API
- [arXiv](https://arxiv.org/) - Preprint server for scientific papers
- [PubMed](https://pubmed.ncbi.nlm.nih.gov/) - Biomedical literature database
- [FastAPI](https://fastapi.tiangolo.com/) - Async web framework
- [Next.js](https://nextjs.org/) - React framework
