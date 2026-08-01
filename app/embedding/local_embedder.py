"""로컬 sentence-transformers 기반 임베딩.

GPU 활용으로 API 비용 없이 임베딩 생성.
"""

import asyncio
import logging

from sentence_transformers import SentenceTransformer

from app.core.config import settings

logger = logging.getLogger(__name__)


class LocalEmbedder:
    """sentence-transformers 기반 로컬 임베딩."""

    def __init__(
        self,
        model_name: str = settings.EMBEDDING_LOCAL_MODEL,
        device: str = settings.EMBEDDING_LOCAL_DEVICE,
        dimension: int | None = None,
    ):
        self.model_name = model_name
        self.device = device
        self._model: SentenceTransformer | None = None
        self._dimension = dimension

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            logger.info(
                "Loading local embedding model: %s on %s",
                self.model_name, self.device,
            )
            self._model = SentenceTransformer(
                self.model_name, device=self.device
            )
            if self._dimension is None:
                self._dimension = self._model.get_sentence_embedding_dimension()
            logger.info("Model loaded. Dimension: %d", self._dimension)
        return self._model

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            _ = self.model  # 로딩 트리거
        return self._dimension  # type: ignore[return-value]

    @staticmethod
    def _sanitize_text(text) -> str:
        """토크나이저 호환 텍스트 정제."""
        if not isinstance(text, str):
            return " "
        # null 바이트, 서로게이트, 제어 문자 제거
        cleaned = text.replace("\x00", "")
        cleaned = cleaned.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")
        cleaned = cleaned.strip()
        return cleaned if cleaned else " "

    def _encode_sync(
        self, texts: list[str], batch_size: int
    ) -> list[list[float]]:
        """동기 배치 인코딩. 실패 시 개별 폴백."""
        if not texts:
            return []

        safe_texts = [self._sanitize_text(t) for t in texts]

        try:
            embeddings = self.model.encode(
                safe_texts,
                batch_size=batch_size,
                show_progress_bar=False,
                normalize_embeddings=True,
                convert_to_numpy=True,
            )
            return embeddings.tolist()
        except Exception as e:
            logger.warning("Batch encode failed (%d texts): %s. Falling back to individual.", len(safe_texts), e)
            # 개별 인코딩 폴백
            import numpy as np
            dim = self.dimension
            results = []
            for i, t in enumerate(safe_texts):
                try:
                    emb = self.model.encode(
                        [t], show_progress_bar=False,
                        normalize_embeddings=True, convert_to_numpy=True,
                    )
                    results.append(emb[0].tolist())
                except Exception:
                    logger.warning("Single encode failed at index %d, using zero vector", i)
                    results.append([0.0] * dim)
            return results

    async def embed(self, text: str) -> list[float]:
        """단일 텍스트를 벡터로 변환."""
        results = await asyncio.to_thread(self._encode_sync, [text], 1)
        return results[0]

    async def embed_batch(
        self, texts: list[str], batch_size: int | None = None
    ) -> list[list[float]]:
        """배치 임베딩. GPU로 한 번에 처리."""
        if batch_size is None:
            batch_size = settings.EMBEDDING_LOCAL_BATCH_SIZE
        return await asyncio.to_thread(self._encode_sync, texts, batch_size)

    async def embed_batch_rated(
        self,
        texts: list[str],
        rate_limiter=None,
        max_batch_tokens: int = 0,
    ) -> list[list[float]]:
        """embed_batch_rated 호환 인터페이스. rate_limiter는 무시."""
        return await self.embed_batch(texts)
