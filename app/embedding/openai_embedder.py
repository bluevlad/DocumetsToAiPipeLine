"""OpenAI API 기반 임베딩.

text-embedding-3-large 모델 사용.
"""

import asyncio
import logging

from openai import AsyncOpenAI, OpenAI

from app.core.config import settings
from app.ingestion.rate_limiter import RateLimiter
from app.ingestion.token_counter import count_tokens, create_batches

logger = logging.getLogger(__name__)


class OpenAIEmbedder:
    """OpenAI API 기반 임베딩."""

    def __init__(
        self,
        model: str = settings.EMBEDDING_MODEL,
        dimension: int = settings.EMBEDDING_DIMENSION,
    ):
        self.model = model
        self.dimension = dimension
        self._client: OpenAI | None = None
        self._async_client: AsyncOpenAI | None = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI()
        return self._client

    @property
    def async_client(self) -> AsyncOpenAI:
        if self._async_client is None:
            self._async_client = AsyncOpenAI()
        return self._async_client

    async def embed(self, text: str) -> list[float]:
        """단일 텍스트를 벡터로 변환."""
        return await asyncio.to_thread(self._embed_sync, text)

    def _embed_sync(self, text: str) -> list[float]:
        response = self.client.embeddings.create(
            model=self.model,
            input=text,
            dimensions=self.dimension,
        )
        return response.data[0].embedding

    async def embed_batch(self, texts: list[str], batch_size: int = 100) -> list[list[float]]:
        """텍스트 배치를 벡터로 일괄 변환."""
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            embeddings = await asyncio.to_thread(self._embed_batch_sync, batch)
            all_embeddings.extend(embeddings)
        return all_embeddings

    def _embed_batch_sync(self, texts: list[str]) -> list[list[float]]:
        response = self.client.embeddings.create(
            model=self.model,
            input=texts,
            dimensions=self.dimension,
        )
        return [d.embedding for d in sorted(response.data, key=lambda x: x.index)]

    async def embed_batch_rated(
        self,
        texts: list[str],
        rate_limiter: RateLimiter,
        max_batch_tokens: int = settings.EMBEDDING_BATCH_MAX_TOKENS,
    ) -> list[list[float]]:
        """레이트 제한을 준수하며 배치 임베딩 생성."""
        batches = create_batches(texts, max_tokens=max_batch_tokens)
        all_embeddings: list[list[float]] = [[] for _ in texts]

        for batch_indices in batches:
            batch_texts = [texts[i] for i in batch_indices]
            batch_token_count = sum(count_tokens(t) for t in batch_texts)

            await rate_limiter.acquire(batch_token_count)

            response = await self.async_client.embeddings.create(
                model=self.model,
                input=batch_texts,
                dimensions=self.dimension,
            )
            sorted_data = sorted(response.data, key=lambda x: x.index)
            for local_idx, global_idx in enumerate(batch_indices):
                all_embeddings[global_idx] = sorted_data[local_idx].embedding

        return all_embeddings
