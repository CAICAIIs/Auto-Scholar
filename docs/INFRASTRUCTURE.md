# Auto-Scholar Infrastructure Setup Guide

## Quick Start with Vector Pipeline

### Prerequisites

- Docker & Docker Compose
- Python 3.11+
- uv
- bun

### 1. Start Infrastructure Services

```bash
docker compose up -d postgres redis minio qdrant
```

This starts:
- PostgreSQL (port 5432) - Metadata storage
- Redis (port 6379) - Caching layer
- MinIO (port 9000, console 9001) - Object storage for PDFs
- Qdrant (port 6333) - Vector database

### 2. Initialize Database Schema

```bash
uv run python scripts/init_db.py
```

### 3. Verify Infrastructure

```bash
./scripts/verify_infrastructure.sh
```

### 4. Configure Environment

Copy `.env.example` to `.env` and set:

```env
VECTOR_PIPELINE_ENABLED=true
LLM_API_KEY=your-api-key

# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=autoscholar
POSTGRES_USER=autoscholar
POSTGRES_PASSWORD=autoscholar

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# MinIO
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin

# Qdrant
QDRANT_HOST=localhost
QDRANT_PORT=6333
```

### 5. Start Application

```bash
# Backend
uv run uvicorn backend.main:app --reload --port 8000

# Frontend (in another terminal)
cd frontend && bun run dev
```

## Architecture Overview

### With Vector Pipeline Enabled

```
User Query
    ↓
Planner Agent → Search Keywords
    ↓
Retriever Agent → Fetch Papers from APIs
    ↓
Extractor Agent → Download PDFs to MinIO
    ↓           → Extract Full Text
    ↓           → Chunk Text (512 tokens)
    ↓           → Generate Embeddings (cached in Redis)
    ↓           → Store in Qdrant Vector DB
    ↓           → Save Metadata to PostgreSQL
    ↓
Writer Agent → Generate Literature Review
    ↓
Critic Agent → Verify Claims with Full-Text
    ↓           → Vector Search for Relevant Chunks
    ↓           → Page-Level Source Tracing
    ↓
Final Review with Citations
```

### Key Features

1. **PDF Storage**: PDFs downloaded once, stored in MinIO, deduplicated by SHA256 hash
2. **Vector Search**: Full-text semantic search via Qdrant for claim verification
3. **Page-Level Tracing**: Claims verified against specific pages in source papers
4. **Caching**: Redis caches PDF metadata and embeddings to reduce costs
5. **Metadata**: PostgreSQL stores papers, chunks, and embeddings metadata

## Infrastructure Services

### PostgreSQL

**Purpose**: Metadata storage for papers, chunks, and embeddings

**Schema**:
- `papers`: Paper metadata, PDF info, processing status
- `chunks`: Text chunks with page ranges
- `embeddings`: Vector IDs and metadata

**Access**:
```bash
psql -h localhost -U autoscholar -d autoscholar
```

### Redis

**Purpose**: Caching layer for PDFs and embeddings

**Keys**:
- `pdf:{paper_id}:{hash}`: PDF metadata cache (24h TTL)
- `embedding:cache:{model}:{hash}`: Embedding cache (30d TTL)

**Access**:
```bash
redis-cli -h localhost -p 6379
```

### MinIO

**Purpose**: Object storage for PDF files

**Buckets**:
- `rag-raw`: Original PDFs
- `rag-processed`: Processed text
- `rag-tmp`: Temporary files (7-day lifecycle)

**Access**:
- API: http://localhost:9000
- Console: http://localhost:9001 (minioadmin/minioadmin)

### Qdrant

**Purpose**: Vector database for semantic search

**Collections**:
- `paper_chunks`: Text chunks with embeddings (1536 dimensions)

**Access**:
- API: http://localhost:6333
- Dashboard: http://localhost:6333/dashboard

## Troubleshooting

### Services Not Starting

```bash
# Check service status
docker compose ps

# View logs
docker compose logs postgres
docker compose logs redis
docker compose logs minio
docker compose logs qdrant

# Restart services
docker compose restart
```

### Database Connection Issues

```bash
# Test PostgreSQL connection
psql -h localhost -U autoscholar -d autoscholar -c '\l'

# Test Redis connection
redis-cli -h localhost ping
```

### MinIO Bucket Issues

```bash
# List buckets (requires mc client)
mc alias set myminio http://localhost:9000 minioadmin minioadmin
mc ls myminio
```

### Vector Pipeline Not Working

Check logs:
```bash
# Backend logs will show:
# "MinIO client initialized: localhost:9000"
# "Redis client initialized: localhost:6379"
# "Qdrant client initialized: localhost:6333"
# "Vector pipeline initialized successfully"
```

If you see warnings, check:
1. `VECTOR_PIPELINE_ENABLED=true` in `.env`
2. All services are running (`docker compose ps`)
3. Network connectivity (`./scripts/verify_infrastructure.sh`)

## Performance Tuning

### Concurrency Settings

```env
# Increase for paid API tiers
LLM_CONCURRENCY=4
CLAIM_VERIFICATION_CONCURRENCY=4
```

### Embedding Batch Size

```env
# Increase for faster embedding generation
EMBEDDING_BATCH_SIZE=100
```

### Cache TTL

```env
# Adjust cache duration
REDIS_PDF_CACHE_TTL=86400  # 24 hours
EMBEDDING_CACHE_TTL=2592000  # 30 days
```

## Disabling Vector Pipeline

To run without infrastructure services:

```env
VECTOR_PIPELINE_ENABLED=false
```

The system will fall back to:
- Abstract-only claim verification
- No PDF storage
- No vector search
- No page-level tracing

## Migration from SQLite-Only

If you have existing checkpoints in SQLite:

1. Checkpoints remain in SQLite (LangGraph state)
2. New papers will be stored in PostgreSQL
3. No data migration needed - systems coexist

## Security Notes

**Default credentials are for development only!**

For production:
- Change PostgreSQL password
- Change MinIO access/secret keys
- Set Redis password
- Use TLS for all connections
- Set `MINIO_SECURE=true`

## Next Steps

- Read `docs/ARCHITECTURE.md` for detailed architecture
- Read `docs/DEVELOPMENT.md` for development guide
- Check `backend/constants.py` for configuration options
