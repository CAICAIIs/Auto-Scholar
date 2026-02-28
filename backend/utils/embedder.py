"""Embedding generation with Redis caching.

This module provides async embedding generation using OpenAI's API with
Redis caching to reduce costs and improve performance.
"""

import hashlib
import logging

from openai import AsyncOpenAI
from redis.asyncio import Redis
from tenacity import retry, stop_after_attempt, wait_exponential

from backend.constants import (
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_CACHE_TTL,
    EMBEDDING_MAX_RETRIES,
    EMBEDDING_MODEL,
)

logger = logging.getLogger(__name__)


class EmbeddingError(Exception):
    """Raised when embedding generation fails."""

    pass


class Embedder:
    """Generate embeddings with Redis caching."""

    def __init__(
        self,
        redis_client: Redis,
        api_key: str | None = None,
        model: str = EMBEDDING_MODEL,
    ):
        """Initialize embedder.

        Args:
            redis_client: Redis client for caching
            api_key: OpenAI API key (uses env var if None)
            model: Embedding model name
        """
        self.redis_client = redis_client
        self.model = model
        self.client = AsyncOpenAI(api_key=api_key)
        logger.info("Embedder initialized: model=%s", model)

    async def embed_text(self, text: str) -> list[float]:
        """Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector

        Raises:
            EmbeddingError: If embedding generation fails
        """
        embeddings = await self.embed_batch([text])
        return embeddings[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts with caching.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors in same order as input

        Raises:
            EmbeddingError: If embedding generation fails
        """
        if not texts:
            return []

        logger.info("Embedding batch: %d texts", len(texts))

        # Check cache for all texts
        cache_keys = [self._generate_cache_key(text) for text in texts]
        cached_embeddings = await self._get_cached_embeddings(cache_keys)

        # Identify cache misses
        texts_to_embed = []
        indices_to_embed = []

        for i, (text, cached) in enumerate(zip(texts, cached_embeddings)):
            if cached is None:
                texts_to_embed.append(text)
                indices_to_embed.append(i)

        cache_hits = len(texts) - len(texts_to_embed)
        cache_hit_rate = cache_hits / len(texts) if texts else 0

        logger.info(
            "Embedding cache: hits=%d, misses=%d, hit_rate=%.1f%%",
            cache_hits,
            len(texts_to_embed),
            cache_hit_rate * 100,
        )

        # Generate embeddings for cache misses
        if texts_to_embed:
            new_embeddings = await self._embed_texts_batched(texts_to_embed)

            # Cache new embeddings
            await self._cache_embeddings([cache_keys[i] for i in indices_to_embed], new_embeddings)

            # Insert new embeddings into result list
            for idx, embedding in zip(indices_to_embed, new_embeddings):
                cached_embeddings[idx] = embedding

        return cached_embeddings  # type: ignore

    def _generate_cache_key(self, text: str) -> str:
        """Generate cache key for text.

        Args:
            text: Text to generate key for

        Returns:
            Redis cache key
        """
        # Hash text + model name for cache key
        content = f"{self.model}:{text}"
        hash_value = hashlib.sha256(content.encode()).hexdigest()
        return f"embedding:cache:{self.model}:{hash_value[:16]}"

    async def _get_cached_embeddings(self, cache_keys: list[str]) -> list[list[float] | None]:
        """Get cached embeddings for multiple keys.

        Args:
            cache_keys: List of cache keys

        Returns:
            List of embeddings (None for cache misses)
        """
        try:
            # Use pipeline for efficiency
            pipe = self.redis_client.pipeline()
            for key in cache_keys:
                pipe.get(key)

            results = await pipe.execute()

            embeddings = []
            for result in results:
                if result:
                    # Parse cached embedding (stored as comma-separated floats)
                    embedding = [float(x) for x in result.split(",")]
                    embeddings.append(embedding)
                else:
                    embeddings.append(None)

            return embeddings

        except Exception as e:
            logger.warning("Failed to get cached embeddings: %s", str(e))
            # Return all None on cache error
            return [None] * len(cache_keys)

    async def _cache_embeddings(self, cache_keys: list[str], embeddings: list[list[float]]) -> None:
        """Cache embeddings.

        Args:
            cache_keys: List of cache keys
            embeddings: List of embeddings to cache
        """
        try:
            # Use pipeline for efficiency
            pipe = self.redis_client.pipeline()

            for key, embedding in zip(cache_keys, embeddings):
                # Store as comma-separated floats
                value = ",".join(str(x) for x in embedding)
                pipe.setex(key, EMBEDDING_CACHE_TTL, value)

            await pipe.execute()

            logger.debug("Cached %d embeddings", len(embeddings))

        except Exception as e:
            logger.warning("Failed to cache embeddings: %s", str(e))
            # Don't raise - caching is optional

    async def _embed_texts_batched(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for texts in batches.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors

        Raises:
            EmbeddingError: If API call fails
        """
        all_embeddings = []

        # Process in batches
        for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
            batch = texts[i : i + EMBEDDING_BATCH_SIZE]
            batch_embeddings = await self._call_embedding_api(batch)
            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(EMBEDDING_MAX_RETRIES),
    )
    async def _call_embedding_api(self, texts: list[str]) -> list[list[float]]:
        """Call OpenAI embedding API with retry logic.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors

        Raises:
            EmbeddingError: If API call fails after retries
        """
        try:
            logger.debug("Calling embedding API: %d texts", len(texts))

            response = await self.client.embeddings.create(model=self.model, input=texts)

            embeddings = [item.embedding for item in response.data]

            logger.debug("Embedding API success: %d embeddings", len(embeddings))

            return embeddings

        except Exception as e:
            logger.error("Embedding API failed: %s", str(e))
            raise EmbeddingError(f"Failed to generate embeddings: {e}") from e
