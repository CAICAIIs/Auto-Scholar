#!/bin/bash
set -e

echo "=== Auto-Scholar Infrastructure Initialization ==="
echo ""

MINIO_ENDPOINT="${MINIO_ENDPOINT:-localhost:9000}"
MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-minioadmin}"
MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-minioadmin}"
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-autoscholar}"
POSTGRES_USER="${POSTGRES_USER:-autoscholar}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-autoscholar}"

echo "Waiting for services to be ready..."
echo ""

echo "Checking PostgreSQL..."
until PGPASSWORD=$POSTGRES_PASSWORD psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c '\q' 2>/dev/null; do
  echo "  PostgreSQL is unavailable - sleeping"
  sleep 2
done
echo "  PostgreSQL is ready"

echo "Checking Redis..."
until redis-cli -h "${REDIS_HOST:-localhost}" -p "${REDIS_PORT:-6379}" ping 2>/dev/null | grep -q PONG; do
  echo "  Redis is unavailable - sleeping"
  sleep 2
done
echo "  Redis is ready"

echo "Checking MinIO..."
until curl -sf "http://${MINIO_ENDPOINT}/minio/health/live" >/dev/null 2>&1; do
  echo "  MinIO is unavailable - sleeping"
  sleep 2
done
echo "  MinIO is ready"

echo "Checking Qdrant..."
until curl -sf "http://${QDRANT_HOST:-localhost}:${QDRANT_PORT:-6333}/healthz" >/dev/null 2>&1; do
  echo "  Qdrant is unavailable - sleeping"
  sleep 2
done
echo "  Qdrant is ready"

echo ""
echo "All services are ready. Initializing..."
echo ""

echo "Creating MinIO buckets..."
mc alias set myminio "http://${MINIO_ENDPOINT}" "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY" >/dev/null 2>&1 || true

for bucket in rag-raw rag-processed rag-tmp; do
  if mc ls "myminio/${bucket}" >/dev/null 2>&1; then
    echo "  Bucket ${bucket} already exists"
  else
    mc mb "myminio/${bucket}"
    echo "  Created bucket ${bucket}"
  fi
done

echo "  Setting lifecycle policy for rag-tmp (7-day expiration)..."
cat > /tmp/lifecycle.json <<EOF
{
  "Rules": [
    {
      "ID": "expire-tmp-files",
      "Status": "Enabled",
      "Expiration": {
        "Days": 7
      }
    }
  ]
}
EOF
mc ilm import "myminio/rag-tmp" < /tmp/lifecycle.json >/dev/null 2>&1 || true
rm /tmp/lifecycle.json

echo ""
echo "=== Infrastructure initialization complete ==="
echo ""
echo "Services:"
echo "  PostgreSQL: ${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"
echo "  Redis: ${REDIS_HOST:-localhost}:${REDIS_PORT:-6379}"
echo "  MinIO: http://${MINIO_ENDPOINT}"
echo "  MinIO Console: http://${MINIO_ENDPOINT%:*}:9001"
echo "  Qdrant: http://${QDRANT_HOST:-localhost}:${QDRANT_PORT:-6333}"
echo ""
echo "MinIO Buckets:"
echo "  - rag-raw (raw PDFs)"
echo "  - rag-processed (processed text)"
echo "  - rag-tmp (temporary files, 7-day expiration)"
echo ""
