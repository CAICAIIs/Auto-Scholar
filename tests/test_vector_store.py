from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.constants import EMBEDDING_DIMENSIONS
from backend.utils.vector_store import QdrantVectorStore, VectorStoreError


@pytest.fixture
def mock_qdrant_client():
    return AsyncMock()


@pytest.fixture
def store(mock_qdrant_client):
    return QdrantVectorStore(
        client=mock_qdrant_client,
        collection_name="test_chunks",
        vector_size=128,
    )


class TestQdrantVectorStoreInit:
    def test_init_stores_params(self, mock_qdrant_client):
        store = QdrantVectorStore(
            client=mock_qdrant_client,
            collection_name="my_col",
            vector_size=256,
        )
        assert store.client is mock_qdrant_client
        assert store.collection_name == "my_col"
        assert store.vector_size == 256

    def test_init_defaults(self, mock_qdrant_client):
        store = QdrantVectorStore(client=mock_qdrant_client)
        assert store.collection_name == "paper_chunks"
        assert store.vector_size == EMBEDDING_DIMENSIONS


class TestEnsureCollectionExists:
    async def test_creates_collection_when_not_exists(self, store, mock_qdrant_client):
        collections_resp = MagicMock()
        collections_resp.collections = []
        mock_qdrant_client.get_collections.return_value = collections_resp

        await store.ensure_collection_exists()

        mock_qdrant_client.create_collection.assert_awaited_once()
        call_kwargs = mock_qdrant_client.create_collection.call_args
        assert call_kwargs.kwargs["collection_name"] == "test_chunks"

    async def test_skips_creation_when_exists(self, store, mock_qdrant_client):
        col = MagicMock()
        col.name = "test_chunks"
        collections_resp = MagicMock()
        collections_resp.collections = [col]
        mock_qdrant_client.get_collections.return_value = collections_resp

        await store.ensure_collection_exists()

        mock_qdrant_client.create_collection.assert_not_awaited()

    async def test_raises_vector_store_error_on_failure(self, store, mock_qdrant_client):
        mock_qdrant_client.get_collections.side_effect = RuntimeError("connection refused")

        with pytest.raises(VectorStoreError, match="Collection creation failed"):
            await store.ensure_collection_exists()


class TestUpsertChunks:
    async def test_upsert_success_returns_point_ids(self, store, mock_qdrant_client):
        chunks = [
            {"paper_id": "p1", "chunk_index": 0, "chunk_text": "hello"},
            {"paper_id": "p1", "chunk_index": 1, "chunk_text": "world"},
        ]
        embeddings = [[0.1, 0.2], [0.3, 0.4]]

        result = await store.upsert_chunks(chunks, embeddings)

        assert len(result) == 2
        assert all(isinstance(pid, str) for pid in result)
        mock_qdrant_client.upsert.assert_awaited_once()

    async def test_upsert_empty_chunks_returns_empty(self, store, mock_qdrant_client):
        result = await store.upsert_chunks([], [])
        assert result == []
        mock_qdrant_client.upsert.assert_not_awaited()

    async def test_upsert_length_mismatch_raises(self, store):
        with pytest.raises(VectorStoreError, match="length mismatch"):
            await store.upsert_chunks([{"a": 1}], [[0.1], [0.2]])

    async def test_upsert_failure_raises_vector_store_error(self, store, mock_qdrant_client):
        mock_qdrant_client.upsert.side_effect = RuntimeError("timeout")

        with pytest.raises(VectorStoreError, match="Upsert failed"):
            await store.upsert_chunks([{"a": 1}], [[0.1]])


class TestSearch:
    async def test_search_returns_results(self, store, mock_qdrant_client):
        point1 = MagicMock(id="id1", score=0.95, payload={"paper_id": "p1"})
        point2 = MagicMock(id="id2", score=0.85, payload={"paper_id": "p2"})
        response = MagicMock()
        response.points = [point1, point2]
        mock_qdrant_client.query_points.return_value = response

        results = await store.search(query_vector=[0.1, 0.2], limit=5)

        assert len(results) == 2
        assert results[0]["id"] == "id1"
        assert results[0]["score"] == 0.95
        assert results[0]["payload"] == {"paper_id": "p1"}

    async def test_search_empty_results(self, store, mock_qdrant_client):
        response = MagicMock()
        response.points = []
        mock_qdrant_client.query_points.return_value = response

        results = await store.search(query_vector=[0.1])

        assert results == []

    async def test_search_passes_score_threshold(self, store, mock_qdrant_client):
        response = MagicMock()
        response.points = []
        mock_qdrant_client.query_points.return_value = response

        await store.search(query_vector=[0.1], score_threshold=0.8)

        call_kwargs = mock_qdrant_client.query_points.call_args.kwargs
        assert call_kwargs["score_threshold"] == 0.8

    async def test_search_passes_filter(self, store, mock_qdrant_client):
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        f = Filter(must=[FieldCondition(key="paper_id", match=MatchValue(value="p1"))])
        response = MagicMock()
        response.points = []
        mock_qdrant_client.query_points.return_value = response

        await store.search(query_vector=[0.1], filter_dict=f)

        call_kwargs = mock_qdrant_client.query_points.call_args.kwargs
        assert call_kwargs["query_filter"] is f

    async def test_search_failure_raises_vector_store_error(self, store, mock_qdrant_client):
        mock_qdrant_client.query_points.side_effect = RuntimeError("search error")

        with pytest.raises(VectorStoreError, match="Search failed"):
            await store.search(query_vector=[0.1])


class TestDeleteByPaperId:
    async def test_delete_found_points(self, store, mock_qdrant_client):
        point1 = MagicMock(id="uuid-1")
        point2 = MagicMock(id="uuid-2")
        mock_qdrant_client.scroll.return_value = ([point1, point2], None)

        count = await store.delete_by_paper_id("p1")

        assert count == 2
        mock_qdrant_client.delete.assert_awaited_once()

    async def test_delete_no_points_found(self, store, mock_qdrant_client):
        mock_qdrant_client.scroll.return_value = ([], None)

        count = await store.delete_by_paper_id("p_nonexistent")

        assert count == 0
        mock_qdrant_client.delete.assert_not_awaited()

    async def test_delete_failure_raises_vector_store_error(self, store, mock_qdrant_client):
        mock_qdrant_client.scroll.side_effect = RuntimeError("scroll error")

        with pytest.raises(VectorStoreError, match="Deletion failed"):
            await store.delete_by_paper_id("p1")


class TestGetCollectionInfo:
    async def test_get_collection_info_success(self, store, mock_qdrant_client):
        info = MagicMock()
        info.indexed_vectors_count = 1000
        info.points_count = 500
        info.status = "green"
        mock_qdrant_client.get_collection.return_value = info

        result = await store.get_collection_info()

        assert result["name"] == "test_chunks"
        assert result["indexed_vectors_count"] == 1000
        assert result["points_count"] == 500
        assert result["status"] == "green"

    async def test_get_collection_info_failure(self, store, mock_qdrant_client):
        mock_qdrant_client.get_collection.side_effect = RuntimeError("not found")

        with pytest.raises(VectorStoreError, match="Info retrieval failed"):
            await store.get_collection_info()
