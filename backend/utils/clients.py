import logging
from typing import Any

from backend.constants import (
    MINIO_ACCESS_KEY,
    MINIO_ENDPOINT,
    MINIO_SECRET_KEY,
    MINIO_SECURE,
    QDRANT_COLLECTION_NAME,
    QDRANT_HOST,
    QDRANT_PORT,
    REDIS_DB,
    REDIS_HOST,
    REDIS_PASSWORD,
    REDIS_PORT,
    VECTOR_PIPELINE_ENABLED,
)

logger = logging.getLogger(__name__)

_minio_client: Any | None = None
_redis_client: Any | None = None
_qdrant_client: Any | None = None
_embedder: Any | None = None
_vector_store: Any | None = None


def get_minio_client() -> Any | None:
    global _minio_client
    if not VECTOR_PIPELINE_ENABLED:
        return None
    if _minio_client is None:
        try:
            from minio import Minio

            _minio_client = Minio(
                MINIO_ENDPOINT,
                access_key=MINIO_ACCESS_KEY,
                secret_key=MINIO_SECRET_KEY,
                secure=MINIO_SECURE,
            )
            logger.info("MinIO client initialized: %s", MINIO_ENDPOINT)
        except Exception as e:
            logger.warning("Failed to initialize MinIO client: %s", e)
            return None
    return _minio_client


async def get_redis_client() -> Any | None:
    global _redis_client
    if not VECTOR_PIPELINE_ENABLED:
        return None
    if _redis_client is None:
        try:
            import asyncio

            from redis.asyncio import Redis

            _redis_client = Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                password=REDIS_PASSWORD if REDIS_PASSWORD else None,
                decode_responses=False,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            await asyncio.wait_for(_redis_client.ping(), timeout=2.0)
            logger.info("Redis client initialized: %s:%d", REDIS_HOST, REDIS_PORT)
        except Exception as e:
            logger.warning("Failed to initialize Redis client: %s", e)
            _redis_client = None
            return None
    return _redis_client


async def get_qdrant_client() -> Any | None:
    global _qdrant_client
    if not VECTOR_PIPELINE_ENABLED:
        return None
    if _qdrant_client is None:
        try:
            import asyncio

            from qdrant_client import AsyncQdrantClient

            _qdrant_client = AsyncQdrantClient(
                host=QDRANT_HOST,
                port=QDRANT_PORT,
                timeout=2.0,
            )
            await asyncio.wait_for(_qdrant_client.get_collections(), timeout=2.0)
            logger.info("Qdrant client initialized: %s:%d", QDRANT_HOST, QDRANT_PORT)
        except Exception as e:
            logger.warning("Failed to initialize Qdrant client: %s", e)
            _qdrant_client = None
            return None
    return _qdrant_client


async def get_embedder() -> Any | None:
    global _embedder
    if not VECTOR_PIPELINE_ENABLED:
        return None
    if _embedder is None:
        redis_client = await get_redis_client()
        if redis_client is None:
            return None
        try:
            from backend.utils.embedder import Embedder

            _embedder = Embedder(redis_client=redis_client)
            logger.info("Embedder initialized")
        except Exception as e:
            logger.warning("Failed to initialize Embedder: %s", e)
            return None
    return _embedder


async def get_vector_store() -> Any | None:
    global _vector_store
    if not VECTOR_PIPELINE_ENABLED:
        return None
    if _vector_store is None:
        qdrant_client = await get_qdrant_client()
        if qdrant_client is None:
            return None
        try:
            from backend.utils.vector_store import QdrantVectorStore

            _vector_store = QdrantVectorStore(
                client=qdrant_client, collection_name=QDRANT_COLLECTION_NAME
            )
            await _vector_store.ensure_collection_exists()
            logger.info("Vector store initialized")
        except Exception as e:
            logger.warning("Failed to initialize Vector store: %s", e)
            return None
    return _vector_store


async def cleanup_clients() -> None:
    global _redis_client, _qdrant_client
    if _redis_client:
        await _redis_client.aclose()
        logger.info("Redis client closed")
    if _qdrant_client:
        await _qdrant_client.close()
        logger.info("Qdrant client closed")
