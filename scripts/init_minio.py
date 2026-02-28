#!/usr/bin/env python3
"""Initialize MinIO buckets for PDF object storage."""

import asyncio
import json
import logging

from minio import Minio
from minio.error import S3Error

from backend.constants import (
    MINIO_ACCESS_KEY,
    MINIO_BUCKET_PROCESSED,
    MINIO_BUCKET_RAW,
    MINIO_BUCKET_TMP,
    MINIO_ENDPOINT,
    MINIO_SECRET_KEY,
    MINIO_SECURE,
)

logger = logging.getLogger(__name__)


def _build_tmp_lifecycle_config() -> str:
    """Build MinIO lifecycle config to expire temporary objects after 7 days."""
    lifecycle_policy = {
        "Rules": [
            {
                "ID": "expire-tmp-after-7-days",
                "Status": "Enabled",
                "Filter": {"Prefix": ""},
                "Expiration": {"Days": 7},
            }
        ]
    }
    return json.dumps(lifecycle_policy)


def _ensure_bucket(client: Minio, bucket_name: str) -> None:
    """Create bucket if it does not already exist."""
    if client.bucket_exists(bucket_name):
        logger.info("Bucket already exists: %s", bucket_name)
        return
    client.make_bucket(bucket_name)
    logger.info("Created bucket: %s", bucket_name)


def _set_tmp_bucket_lifecycle(client: Minio, bucket_name: str) -> None:
    """Apply a 7-day lifecycle rule to temporary bucket objects."""
    lifecycle_config = _build_tmp_lifecycle_config()
    client.set_bucket_lifecycle(bucket_name, lifecycle_config)
    logger.info("Applied 7-day lifecycle policy to bucket: %s", bucket_name)


def _initialize_minio_sync() -> None:
    """Perform blocking MinIO initialization operations."""
    client = Minio(
        endpoint=MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE,
    )

    for bucket_name in (MINIO_BUCKET_RAW, MINIO_BUCKET_PROCESSED, MINIO_BUCKET_TMP):
        _ensure_bucket(client, bucket_name)

    _set_tmp_bucket_lifecycle(client, MINIO_BUCKET_TMP)


async def initialize_minio() -> int:
    """Initialize required MinIO buckets and lifecycle policy asynchronously."""
    try:
        await asyncio.to_thread(_initialize_minio_sync)
        logger.info("MinIO initialization complete")
        return 0
    except S3Error:
        logger.exception("MinIO initialization failed due to S3 API error")
        return 1
    except Exception:
        logger.exception("MinIO initialization failed unexpectedly")
        return 1


async def _main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    return await initialize_minio()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
