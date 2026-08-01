"""로컬 임베딩 (sentence-transformers) 단위 테스트.

CPU 모드로 소형 모델을 사용하여 빠르게 테스트.
"""

import math

import pytest

from app.embedding.local_embedder import LocalEmbedder

# 테스트용 소형 모델 (CPU, 빠른 로드)
TEST_MODEL = "sentence-transformers/paraphrase-MiniLM-L3-v2"


@pytest.fixture(scope="module")
def embedder():
    """테스트용 로컬 임베딩 (CPU 소형 모델)."""
    return LocalEmbedder(
        model_name=TEST_MODEL,
        device="cpu",
    )


class TestLocalEmbedder:
    @pytest.mark.asyncio
    async def test_single_embed(self, embedder):
        """단일 텍스트 임베딩."""
        vec = await embedder.embed("테스트 문장입니다.")
        assert isinstance(vec, list)
        assert len(vec) > 0
        assert all(isinstance(v, float) for v in vec)

    @pytest.mark.asyncio
    async def test_dimension_property(self, embedder):
        """dimension 속성이 모델 차원과 일치."""
        _ = await embedder.embed("test")
        assert embedder.dimension > 0
        assert isinstance(embedder.dimension, int)

    @pytest.mark.asyncio
    async def test_batch_embed(self, embedder):
        """배치 임베딩."""
        texts = ["문장 하나", "문장 둘", "문장 셋"]
        vecs = await embedder.embed_batch(texts, batch_size=2)
        assert len(vecs) == 3
        assert all(len(v) == embedder.dimension for v in vecs)

    @pytest.mark.asyncio
    async def test_normalized_vectors(self, embedder):
        """임베딩 벡터가 정규화됨 (L2 norm ≈ 1.0)."""
        vec = await embedder.embed("정규화 테스트")
        l2_norm = math.sqrt(sum(v * v for v in vec))
        assert abs(l2_norm - 1.0) < 0.01, f"L2 norm = {l2_norm}"

    @pytest.mark.asyncio
    async def test_embed_batch_rated_ignores_limiter(self, embedder):
        """embed_batch_rated는 rate_limiter를 무시하고 동작."""
        texts = ["테스트 A", "테스트 B"]
        # rate_limiter=None으로 호출해도 동작
        vecs = await embedder.embed_batch_rated(texts, rate_limiter=None)
        assert len(vecs) == 2

    @pytest.mark.asyncio
    async def test_empty_batch(self, embedder):
        """빈 배치 처리."""
        vecs = await embedder.embed_batch([], batch_size=10)
        assert vecs == []

    @pytest.mark.asyncio
    async def test_different_texts_different_vectors(self, embedder):
        """서로 다른 텍스트는 서로 다른 벡터."""
        vec1 = await embedder.embed("사과는 빨간색 과일입니다")
        vec2 = await embedder.embed("프로그래밍 언어에는 파이썬이 있습니다")
        # 완전히 같을 수 없음
        assert vec1 != vec2
