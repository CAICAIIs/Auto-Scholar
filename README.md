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

### Language Options

- **UI Language**: Click the language button (中文/English) to switch interface language
- **Output Language**: Click EN/中 button to choose review generation language

## Tech Stack

### Backend
- **FastAPI** - Async web framework
- **LangGraph** - Workflow orchestration with checkpointing
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

## Performance

| Metric | Value | Validation Method |
|--------|-------|-------------------|
| SSE Network Reduction | 92% | Benchmark test with 263 tokens → 21 flushes |
| Citation Accuracy | 97.3% | Manual validation of 37 citations across 3 topics |
| Typical Workflow Time | ~45s | 3 papers end-to-end |
| Max QA Retries | 3 | Configurable in workflow.py (`MAX_RETRY_COUNT`) |

### Benchmark Details

**SSE Debouncing** (`tests/benchmark_sse.py`):
- Raw messages: 263 tokens
- After debounce: 21 network requests
- Compression ratio: 12.5x
- Mechanism: 200ms time window + semantic boundary detection (。！？.!?\n)

**Citation Validation** (`tests/validate_citations.py`):
- Topics validated: 3 (transformer architecture, medical imaging, robotics)
- Total citations: 37
- Correct citations: 36
- Error type: Citation index correct but context mismatch (QA validates existence, not semantic relevance)

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
