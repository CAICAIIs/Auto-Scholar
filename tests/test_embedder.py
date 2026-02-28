from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.constants import (
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_CACHE_TTL,
    EMBEDDING_MAX_RETRIES,
    EMBEDDING_MODEL,
)
from backend.utils.embedder import EmbeddingError, Embedder


@pytest.fixture(autouse=True)
def _patch_openai():
    with patch("backend.utils.embedder.AsyncOpenAI"):
        yield


class TestEmbedderInit:
    def test_init_creates_async_openai_client(self):
        redis_client = MagicMock()

        with patch("backend.utils.embedder.AsyncOpenAI") as mock_openai:
            embedder = Embedder(redis_client=redis_client, api_key="test-key")

        mock_openai.assert_called_once_with(api_key="test-key")
        assert embedder.redis_client is redis_client
        assert embedder.model == EMBEDDING_MODEL


class TestEmbedPublicMethods:
    async def test_embed_text_delegates_to_embed_batch(self):
        redis_client = MagicMock()
        embedder = Embedder(redis_client=redis_client)
        expected = [0.1, 0.2, 0.3]
        embedder.embed_batch = AsyncMock(return_value=[expected])

        result = await embedder.embed_text("hello")

        assert result == expected
        embedder.embed_batch.assert_awaited_once_with(["hello"])

    async def test_embed_batch_empty_input_returns_empty_list(self):
        redis_client = MagicMock()
        embedder = Embedder(redis_client=redis_client)

        result = await embedder.embed_batch([])

        assert result == []

    async def test_embed_batch_all_cache_hits(self):
        redis_client = MagicMock()
        embedder = Embedder(redis_client=redis_client)
        texts = ["a", "b"]
        cached = [[1.0, 2.0], [3.0, 4.0]]
        embedder._get_cached_embeddings = AsyncMock(return_value=cached.copy())
        embedder._embed_texts_batched = AsyncMock()
        embedder._cache_embeddings = AsyncMock()

        result = await embedder.embed_batch(texts)

        assert result == cached
        embedder._embed_texts_batched.assert_not_awaited()
        embedder._cache_embeddings.assert_not_awaited()

    async def test_embed_batch_all_cache_misses(self):
        redis_client = MagicMock()
        embedder = Embedder(redis_client=redis_client)
        texts = ["a", "b"]
        keys = [embedder._generate_cache_key(text) for text in texts]
        generated = [[9.0], [8.0]]
        embedder._get_cached_embeddings = AsyncMock(return_value=[None, None])
        embedder._embed_texts_batched = AsyncMock(return_value=generated)
        embedder._cache_embeddings = AsyncMock()

        result = await embedder.embed_batch(texts)

        assert result == generated
        embedder._embed_texts_batched.assert_awaited_once_with(texts)
        embedder._cache_embeddings.assert_awaited_once_with(keys, generated)

    async def test_embed_batch_mixed_hits_and_misses_keeps_order(self):
        redis_client = MagicMock()
        embedder = Embedder(redis_client=redis_client)
        texts = ["hit", "miss", "hit2"]
        miss_embedding = [7.7, 8.8]
        cached = [[1.0], None, [3.0]]
        embedder._get_cached_embeddings = AsyncMock(return_value=cached)
        embedder._embed_texts_batched = AsyncMock(return_value=[miss_embedding])
        embedder._cache_embeddings = AsyncMock()

        result = await embedder.embed_batch(texts)

        assert result == [[1.0], miss_embedding, [3.0]]
        embedder._embed_texts_batched.assert_awaited_once_with(["miss"])
        expected_miss_key = [embedder._generate_cache_key("miss")]
        embedder._cache_embeddings.assert_awaited_once_with(expected_miss_key, [miss_embedding])


class TestEmbedderCacheMethods:
    def test_generate_cache_key_is_deterministic_and_model_scoped(self):
        embedder_a = Embedder(redis_client=MagicMock(), model="model-a")
        embedder_b = Embedder(redis_client=MagicMock(), model="model-b")

        key1 = embedder_a._generate_cache_key("same text")
        key2 = embedder_a._generate_cache_key("same text")
        key3 = embedder_b._generate_cache_key("same text")

        assert key1 == key2
        assert key1.startswith("embedding:cache:model-a:")
        assert key3.startswith("embedding:cache:model-b:")
        assert key1 != key3

    async def test_get_cached_embeddings_all_cached(self):
        pipe = AsyncMock()
        pipe.get = MagicMock()
        pipe.execute = AsyncMock(return_value=["0.1,0.2", "3.0,4.0"])
        redis_client = MagicMock()
        redis_client.pipeline.return_value = pipe
        embedder = Embedder(redis_client=redis_client)

        result = await embedder._get_cached_embeddings(["k1", "k2"])

        assert result == [[0.1, 0.2], [3.0, 4.0]]
        assert pipe.get.call_count == 2

    async def test_get_cached_embeddings_partial_and_none(self):
        pipe = AsyncMock()
        pipe.get = MagicMock()
        pipe.execute = AsyncMock(return_value=[None, "5.5,6.5", None])
        redis_client = MagicMock()
        redis_client.pipeline.return_value = pipe
        embedder = Embedder(redis_client=redis_client)

        result = await embedder._get_cached_embeddings(["k1", "k2", "k3"])

        assert result == [None, [5.5, 6.5], None]

    async def test_get_cached_embeddings_redis_error_returns_all_none(self):
        pipe = AsyncMock()
        pipe.get = MagicMock()
        pipe.execute = AsyncMock(side_effect=RuntimeError("redis down"))
        redis_client = MagicMock()
        redis_client.pipeline.return_value = pipe
        embedder = Embedder(redis_client=redis_client)

        result = await embedder._get_cached_embeddings(["k1", "k2"])

        assert result == [None, None]

    async def test_cache_embeddings_success_uses_ttl_and_serialization(self):
        pipe = AsyncMock()
        pipe.setex = MagicMock()
        pipe.execute = AsyncMock(return_value=[])
        redis_client = MagicMock()
        redis_client.pipeline.return_value = pipe
        embedder = Embedder(redis_client=redis_client)

        await embedder._cache_embeddings(["k1", "k2"], [[0.1, 0.2], [3.0, 4.0]])

        pipe.setex.assert_any_call("k1", EMBEDDING_CACHE_TTL, "0.1,0.2")
        pipe.setex.assert_any_call("k2", EMBEDDING_CACHE_TTL, "3.0,4.0")
        assert pipe.setex.call_count == 2
        pipe.execute.assert_awaited_once()

    async def test_cache_embeddings_redis_error_does_not_raise(self):
        pipe = AsyncMock()
        pipe.setex = MagicMock(side_effect=RuntimeError("set failed"))
        pipe.execute = AsyncMock()
        redis_client = MagicMock()
        redis_client.pipeline.return_value = pipe
        embedder = Embedder(redis_client=redis_client)

        await embedder._cache_embeddings(["k1"], [[1.0]])


class TestEmbedderBatchingAndApi:
    async def test_embed_texts_batched_single_batch(self):
        redis_client = MagicMock()
        embedder = Embedder(redis_client=redis_client)
        texts = ["a", "b", "c"]
        embedder._call_embedding_api = AsyncMock(return_value=[[1.0], [2.0], [3.0]])

        result = await embedder._embed_texts_batched(texts)

        assert result == [[1.0], [2.0], [3.0]]
        embedder._call_embedding_api.assert_awaited_once_with(texts)

    async def test_embed_texts_batched_splits_multiple_batches(self):
        redis_client = MagicMock()
        embedder = Embedder(redis_client=redis_client)
        texts = [f"text-{i}" for i in range(EMBEDDING_BATCH_SIZE + 2)]

        async def side_effect(batch):
            return [[float(len(item))] for item in batch]

        embedder._call_embedding_api = AsyncMock(side_effect=side_effect)

        result = await embedder._embed_texts_batched(texts)

        assert len(result) == len(texts)
        assert embedder._call_embedding_api.await_count == 2
        first_call_batch = embedder._call_embedding_api.await_args_list[0].args[0]
        second_call_batch = embedder._call_embedding_api.await_args_list[1].args[0]
        assert len(first_call_batch) == EMBEDDING_BATCH_SIZE
        assert len(second_call_batch) == 2

    async def test_call_embedding_api_success(self):
        redis_client = MagicMock()
        embedder = Embedder(redis_client=redis_client)

        item1 = MagicMock(embedding=[0.1, 0.2])
        item2 = MagicMock(embedding=[0.3, 0.4])
        response = MagicMock(data=[item1, item2])
        embedder.client.embeddings.create = AsyncMock(return_value=response)

        result = await embedder._call_embedding_api(["x", "y"])

        assert result == [[0.1, 0.2], [0.3, 0.4]]
        embedder.client.embeddings.create.assert_awaited_once_with(
            model=embedder.model,
            input=["x", "y"],
        )

    async def test_call_embedding_api_failure_raises_embedding_error(self):
        redis_client = MagicMock()
        embedder = Embedder(redis_client=redis_client)
        embedder.client.embeddings.create = AsyncMock(side_effect=RuntimeError("api failure"))

        with pytest.raises(EmbeddingError):
            await embedder._call_embedding_api.__wrapped__(embedder, ["x"])

    def test_call_embedding_api_retry_configuration(self):
        retrying = Embedder._call_embedding_api.retry
        assert retrying.stop.max_attempt_number == EMBEDDING_MAX_RETRIES
        assert retrying.wait.multiplier == 1
        assert retrying.wait.min == 2
        assert retrying.wait.max == 10
