#!/bin/bash
set -e

echo "=== Verifying Auto-Scholar Infrastructure ==="
echo ""

POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-autoscholar}"
POSTGRES_USER="${POSTGRES_USER:-autoscholar}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-autoscholar}"
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"
MINIO_ENDPOINT="${MINIO_ENDPOINT:-localhost:9000}"
QDRANT_HOST="${QDRANT_HOST:-localhost}"
QDRANT_PORT="${QDRANT_PORT:-6333}"

FAILED=0

echo "Checking PostgreSQL..."
if PGPASSWORD=$POSTGRES_PASSWORD psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c '\q' 2>/dev/null; then
  echo "  ✓ PostgreSQL is accessible"
else
  echo "  ✗ PostgreSQL connection failed"
  FAILED=$((FAILED + 1))
fi

echo "Checking Redis..."
if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping 2>/dev/null | grep -q PONG; then
  echo "  ✓ Redis is accessible"
else
  echo "  ✗ Redis connection failed"
  FAILED=$((FAILED + 1))
fi

echo "Checking MinIO..."
if curl -sf "http://${MINIO_ENDPOINT}/minio/health/live" >/dev/null 2>&1; then
  echo "  ✓ MinIO is accessible"
  
  if command -v mc >/dev/null 2>&1; then
    mc alias set myminio "http://${MINIO_ENDPOINT}" "${MINIO_ACCESS_KEY:-minioadmin}" "${MINIO_SECRET_KEY:-minioadmin}" >/dev/null 2>&1 || true
    
    for bucket in rag-raw rag-processed rag-tmp; do
      if mc ls "myminio/${bucket}" >/dev/null 2>&1; then
        echo "  ✓ Bucket ${bucket} exists"
      else
        echo "  ✗ Bucket ${bucket} not found"
        FAILED=$((FAILED + 1))
      fi
    done
  else
    echo "  ⚠ mc (MinIO client) not installed, skipping bucket verification"
  fi
else
  echo "  ✗ MinIO connection failed"
  FAILED=$((FAILED + 1))
fi

echo "Checking Qdrant..."
if curl -sf "http://${QDRANT_HOST}:${QDRANT_PORT}/healthz" >/dev/null 2>&1; then
  echo "  ✓ Qdrant is accessible"
else
  echo "  ✗ Qdrant connection failed"
  FAILED=$((FAILED + 1))
fi

echo ""
if [ $FAILED -eq 0 ]; then
  echo "=== All infrastructure services verified successfully ==="
  exit 0
else
  echo "=== Verification failed: $FAILED service(s) not accessible ==="
  exit 1
fi
