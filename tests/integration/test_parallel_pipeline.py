"""parallel_pipeline 통합 테스트 (임베딩/스토어 모킹)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ingestion.parallel_pipeline import ParallelIngestionPipeline


def _create_test_files(directory: Path, count: int = 20) -> list[Path]:
    """테스트용 텍스트 파일 생성."""
    files = []
    for i in range(count):
        fp = directory / f"test_doc_{i:03d}.txt"
        fp.write_text(f"테스트 문서 {i}번입니다. " * 50, encoding="utf-8")
        files.append(fp)
    return files


def _mock_embed_batch_rated(dimension: int = 384):
    """embed_batch_rated를 모킹하는 AsyncMock."""
    async def _embed(texts, rate_limiter=None, max_batch_tokens=0):
        return [[0.1] * dimension for _ in texts]
    return AsyncMock(side_effect=_embed)


class TestParallelPipeline:
    @pytest.mark.asyncio
    async def test_pipeline_with_text_files(self, tmp_path):
        """20개 텍스트 파일로 전체 파이프라인 검증."""
        test_dir = tmp_path / "test_docs"
        test_dir.mkdir()
        _create_test_files(test_dir, count=20)

        progress_db_path = str(tmp_path / "progress.db")

        pipeline = ParallelIngestionPipeline(
            converter_concurrency=3,
            store_batch_size=100,
            embedding_batch_max_tokens=4000,
        )
        pipeline.progress_db.db_path = progress_db_path

        # 임베딩 모킹 (Facade의 _backend 메서드)
        pipeline.embedder._backend = MagicMock()
        pipeline.embedder._backend.embed_batch_rated = _mock_embed_batch_rated()

        # ChromaDB 모킹
        mock_collection = MagicMock()
        mock_collection.upsert = MagicMock()
        mock_collection.count.return_value = 0
        pipeline.store._collection = mock_collection

        result = await pipeline.run(
            directory=test_dir,
            max_files=20,
            resume=False,
        )

        assert result["completed"] >= 15  # 최소 75% 성공
        assert result["total_chunks"] > 0

    @pytest.mark.asyncio
    async def test_resume_skips_completed(self, tmp_path):
        """이미 처리된 파일은 건너뛰는지 확인."""
        test_dir = tmp_path / "test_docs"
        test_dir.mkdir()
        _create_test_files(test_dir, count=5)

        progress_db_path = str(tmp_path / "progress.db")

        pipeline = ParallelIngestionPipeline(converter_concurrency=2)
        pipeline.progress_db.db_path = progress_db_path

        pipeline.embedder._backend = MagicMock()
        pipeline.embedder._backend.embed_batch_rated = _mock_embed_batch_rated()

        mock_collection = MagicMock()
        mock_collection.upsert = MagicMock()
        pipeline.store._collection = mock_collection

        # 첫 실행
        result1 = await pipeline.run(directory=test_dir, resume=False)
        completed_first = result1["completed"]

        # 두 번째 실행 (resume=True)
        pipeline2 = ParallelIngestionPipeline(converter_concurrency=2)
        pipeline2.progress_db.db_path = progress_db_path

        pipeline2.embedder._backend = MagicMock()
        pipeline2.embedder._backend.embed_batch_rated = _mock_embed_batch_rated()

        mock_collection2 = MagicMock()
        mock_collection2.upsert = MagicMock()
        pipeline2.store._collection = mock_collection2

        result2 = await pipeline2.run(directory=test_dir, resume=True)

        # resume 시 이미 완료된 파일은 처리하지 않음
        assert result2.get("completed", 0) + result2.get("failed", 0) + result2.get("processing", 0) == 0

    @pytest.mark.asyncio
    async def test_empty_directory(self, tmp_path):
        """빈 디렉토리에서 에러 없이 완료."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        pipeline = ParallelIngestionPipeline(converter_concurrency=2)
        pipeline.progress_db.db_path = str(tmp_path / "progress.db")

        result = await pipeline.run(directory=empty_dir, resume=False)
        # 빈 디렉토리 → 통계 0
        assert result.get("completed", 0) == 0
