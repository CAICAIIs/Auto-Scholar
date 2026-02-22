# Backend Dockerfile for Auto-Scholar
# FastAPI + LangGraph backend (uv-based)

FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app

# Install system dependencies for python-docx and aiohttp
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy metadata and lockfile first for better caching
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code
COPY backend/ ./backend/
RUN uv sync --frozen --no-dev

# Create non-root user for security (principle of least privilege)
# UID 1000 is standard for first non-root user
RUN useradd -m -u 1000 appuser

# Create directory for SQLite checkpoint database with proper ownership
RUN mkdir -p /data && chown appuser:appuser /data

# Environment variables (can be overridden)
ENV LLM_BASE_URL=https://api.openai.com/v1
ENV LLM_MODEL=gpt-4o

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Run the application
CMD ["uv", "run", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
