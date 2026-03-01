#!/bin/bash
set -e

echo "=== Auto-Scholar Dev Setup ==="
echo ""

has_error=0

if ! command -v python3 &>/dev/null; then
    echo "ERROR: Python 3.11+ required. Install from https://www.python.org/downloads/"
    has_error=1
else
    py_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    echo "Python $py_version"
fi

if ! command -v uv &>/dev/null; then
    echo "ERROR: uv required. Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
    has_error=1
else
    echo "uv $(uv --version 2>/dev/null | head -1)"
fi

if ! command -v bun &>/dev/null; then
    echo "ERROR: bun required. Install: curl -fsSL https://bun.sh/install | bash"
    has_error=1
else
    echo "bun $(bun --version 2>/dev/null)"
fi

if [ "$has_error" -eq 1 ]; then
    echo ""
    echo "Fix the above errors and re-run this script."
    exit 1
fi

echo ""
echo "Installing Python dependencies..."
uv sync --extra dev

echo ""
echo "Installing frontend dependencies..."
(cd frontend && bun install)

if [ ! -f .env ]; then
    cp .env.minimal .env
    echo ""
    echo "Created .env from .env.minimal"
    echo "IMPORTANT: Edit .env and set your LLM_API_KEY"
else
    echo ""
    echo ".env already exists, skipping"
fi

echo ""
echo "=== Setup complete ==="
echo ""
echo "Start backend:  uv run uvicorn backend.main:app --reload --port 8000"
echo "Start frontend: cd frontend && bun run dev"
echo ""
echo "Optional: For RAG pipeline, run 'make rag' then set VECTOR_PIPELINE_ENABLED=true in .env"
