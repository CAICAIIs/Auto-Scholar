"""Qdrant vector store wrapper for semantic search."""

import logging
from typing import Any
from uuid import uuid4

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointIdsList,
    PointStruct,
    VectorParams,
)

from backend.constants import EMBEDDING_DIMENSIONS

logger = logging.getLogger(__name__)


class VectorStoreError(Exception):
    pass


class QdrantVectorStore:
    def __init__(
        self,
        client: AsyncQdrantClient,
        collection_name: str = "paper_chunks",
        vector_size: int = EMBEDDING_DIMENSIONS,
    ) -> None:
        self.client = client
        self.collection_name = collection_name
        self.vector_size = vector_size
        logger.info(
            "QdrantVectorStore initialized: collection=%s, vector_size=%d",
            collection_name,
            vector_size,
        )

    async def ensure_collection_exists(self) -> None:
        try:
            collections = await self.client.get_collections()
            collection_names = [c.name for c in collections.collections]

            if self.collection_name not in collection_names:
                await self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
                )
                logger.info("Created Qdrant collection: %s", self.collection_name)
            else:
                logger.debug("Qdrant collection exists: %s", self.collection_name)

        except VectorStoreError:
            raise
        except Exception as e:
            logger.error("Failed to ensure collection exists: %s", str(e))
            raise VectorStoreError(f"Collection creation failed: {e}") from e

    async def upsert_chunks(
        self,
        chunks: list[dict[str, Any]],
        embeddings: list[list[float]],
    ) -> list[str]:
        if len(chunks) != len(embeddings):
            raise VectorStoreError(
                f"Chunks and embeddings length mismatch: {len(chunks)} != {len(embeddings)}"
            )

        if not chunks:
            return []

        try:
            point_ids = [str(uuid4()) for _ in chunks]

            points = [
                PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload=chunk,
                )
                for point_id, chunk, embedding in zip(point_ids, chunks, embeddings)
            ]

            await self.client.upsert(
                collection_name=self.collection_name,
                points=points,
            )

            logger.info(
                "Upserted %d chunks to Qdrant collection: %s",
                len(points),
                self.collection_name,
            )

            return point_ids

        except VectorStoreError:
            raise
        except Exception as e:
            logger.error("Failed to upsert chunks: %s", str(e))
            raise VectorStoreError(f"Upsert failed: {e}") from e

    async def search(
        self,
        query_vector: list[float],
        limit: int = 10,
        score_threshold: float | None = None,
        filter_dict: Filter | None = None,
    ) -> list[dict[str, Any]]:
        try:
            response = await self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=limit,
                score_threshold=score_threshold,
                query_filter=filter_dict,
            )

            search_results = [
                {
                    "id": str(point.id),
                    "score": point.score,
                    "payload": point.payload,
                }
                for point in response.points
            ]

            logger.info(
                "Search completed: %d results (threshold=%.2f)",
                len(search_results),
                score_threshold or 0.0,
            )

            return search_results

        except VectorStoreError:
            raise
        except Exception as e:
            logger.error("Search failed: %s", str(e))
            raise VectorStoreError(f"Search failed: {e}") from e

    async def delete_by_paper_id(self, paper_id: str) -> int:
        try:
            scroll_filter = Filter(
                must=[FieldCondition(key="paper_id", match=MatchValue(value=paper_id))]
            )
            results = await self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=scroll_filter,
                limit=1000,
            )

            point_ids = [point.id for point in results[0]]

            if point_ids:
                await self.client.delete(
                    collection_name=self.collection_name,
                    points_selector=PointIdsList(points=point_ids),
                )

                logger.info("Deleted %d chunks for paper_id=%s", len(point_ids), paper_id)

            return len(point_ids)

        except VectorStoreError:
            raise
        except Exception as e:
            logger.error("Failed to delete chunks for paper_id=%s: %s", paper_id, str(e))
            raise VectorStoreError(f"Deletion failed: {e}") from e

    async def get_collection_info(self) -> dict[str, Any]:
        try:
            info = await self.client.get_collection(collection_name=self.collection_name)

            return {
                "name": self.collection_name,
                "indexed_vectors_count": info.indexed_vectors_count,
                "points_count": info.points_count,
                "status": info.status,
            }

        except VectorStoreError:
            raise
        except Exception as e:
            logger.error("Failed to get collection info: %s", str(e))
            raise VectorStoreError(f"Info retrieval failed: {e}") from e
