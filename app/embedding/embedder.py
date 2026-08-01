"""임베딩 생성 모듈 (Facade).

EMBEDDING_PROVIDER 설정에 따라 OpenAI API 또는 로컬 모델로 위임.
"""

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


class DocumentEmbedder:
    """문서 청크를 벡터 임베딩으로 변환.

    EMBEDDING_PROVIDER에 따라 OpenAI 또는 로컬 모델로 위임.
    """

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        dimension: int | None = None,
    ):
        self._provider = provider or settings.EMBEDDING_PROVIDER

        if self._provider == "local":
            from app.embedding.local_embedder import LocalEmbedder

            self._backend = LocalEmbedder(
                model_name=model or settings.EMBEDDING_LOCAL_MODEL,
                device=settings.EMBEDDING_LOCAL_DEVICE,
                dimension=dimension,
            )
            self.model = model or settings.EMBEDDING_LOCAL_MODEL
        else:
            from app.embedding.openai_embedder import OpenAIEmbedder

            self._backend = OpenAIEmbedder(
                model=model or settings.EMBEDDING_MODEL,
                dimension=dimension or settings.EMBEDDING_DIMENSION,
            )
            self.model = model or settings.EMBEDDING_MODEL

    @property
    def dimension(self) -> int:
        return self._backend.dimension

    async def embed(self, text: str) -> list[float]:
        """단일 텍스트를 벡터로 변환."""
        return await self._backend.embed(text)

    async def embed_batch(
        self, texts: list[str], batch_size: int = 100
    ) -> list[list[float]]:
        """텍스트 배치를 벡터로 일괄 변환."""
        return await self._backend.embed_batch(texts, batch_size)

    async def embed_batch_rated(
        self,
        texts: list[str],
        rate_limiter=None,
        max_batch_tokens: int = settings.EMBEDDING_BATCH_MAX_TOKENS,
    ) -> list[list[float]]:
        """레이트 제한을 준수하며 배치 임베딩 생성."""
        return await self._backend.embed_batch_rated(
            texts, rate_limiter, max_batch_tokens
        )
