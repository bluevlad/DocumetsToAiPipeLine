"""파일 인덱스 + 중단/재개 단위 테스트."""

import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

from app.ingestion.progress_db import ProgressDB


@pytest_asyncio.fixture
async def db(tmp_path):
    """임시 SQLite DB."""
    db_path = str(tmp_path / "test_index.db")
    pdb = ProgressDB(db_path=db_path)
    await pdb.initialize()
    yield pdb
    await pdb.close()


def _create_temp_files(directory: Path, names: list[str]) -> list[Path]:
    """테스트용 임시 파일 생성."""
    files = []
    for name in names:
        fp = directory / name
        fp.write_text(f"content of {name}", encoding="utf-8")
        files.append(fp)
    return files


class TestBuildFileIndex:
    @pytest.mark.asyncio
    async def test_initial_build(self, db, tmp_path):
        """최초 스캔 시 모든 파일 인덱싱."""
        _create_temp_files(tmp_path, ["a.txt", "b.txt", "c.hwp"])
        new_count = await db.build_file_index(
            tmp_path, {".txt", ".hwp"},
        )
        assert new_count == 3
        assert await db.get_index_count() == 3

    @pytest.mark.asyncio
    async def test_incremental_build(self, db, tmp_path):
        """이미 인덱싱된 파일은 건너뛰고 새 파일만 추가."""
        _create_temp_files(tmp_path, ["a.txt", "b.txt"])
        await db.build_file_index(tmp_path, {".txt"})
        assert await db.get_index_count() == 2

        # 새 파일 추가
        _create_temp_files(tmp_path, ["c.txt"])
        new_count = await db.build_file_index(tmp_path, {".txt"})
        assert new_count == 1
        assert await db.get_index_count() == 3

    @pytest.mark.asyncio
    async def test_extension_filter(self, db, tmp_path):
        """지정된 확장자만 인덱싱."""
        _create_temp_files(tmp_path, ["a.txt", "b.pdf", "c.jpg"])
        await db.build_file_index(tmp_path, {".txt"})
        assert await db.get_index_count() == 1


class TestGetUnprocessedFromIndex:
    @pytest.mark.asyncio
    async def test_all_unprocessed(self, db, tmp_path):
        """인덱싱 후 모두 미처리."""
        files = _create_temp_files(tmp_path, ["a.txt", "b.txt"])
        await db.build_file_index(tmp_path, {".txt"})
        unprocessed = await db.get_unprocessed_from_index()
        assert len(unprocessed) == 2

    @pytest.mark.asyncio
    async def test_completed_excluded(self, db, tmp_path):
        """완료된 파일은 미처리 목록에서 제외."""
        files = _create_temp_files(tmp_path, ["a.txt", "b.txt", "c.txt"])
        await db.build_file_index(tmp_path, {".txt"})

        # a.txt 완료 처리
        await db.mark_processing(files[0], "run_001")
        await db.mark_completed(files[0], 3)

        unprocessed = await db.get_unprocessed_from_index()
        assert len(unprocessed) == 2
        unprocessed_strs = [str(p) for p in unprocessed]
        assert str(files[0]) not in unprocessed_strs

    @pytest.mark.asyncio
    async def test_failed_included(self, db, tmp_path):
        """실패한 파일은 미처리 목록에 포함."""
        files = _create_temp_files(tmp_path, ["a.txt"])
        await db.build_file_index(tmp_path, {".txt"})

        await db.mark_processing(files[0], "run_001")
        await db.mark_failed(files[0], "error")

        unprocessed = await db.get_unprocessed_from_index()
        assert len(unprocessed) == 1

    @pytest.mark.asyncio
    async def test_deterministic_order(self, db, tmp_path):
        """seq_id 순서로 결정적 반환."""
        _create_temp_files(tmp_path, ["c.txt", "a.txt", "b.txt"])
        await db.build_file_index(tmp_path, {".txt"})

        unprocessed = await db.get_unprocessed_from_index()
        assert len(unprocessed) == 3
        # seq_id는 INSERT 순서를 따르므로 항상 동일한 순서
        result1 = await db.get_unprocessed_from_index()
        result2 = await db.get_unprocessed_from_index()
        assert [str(p) for p in result1] == [str(p) for p in result2]


class TestResetStaleProcessing:
    @pytest.mark.asyncio
    async def test_reset_processing_to_pending(self, db, tmp_path):
        """processing 상태 파일을 pending으로 리셋."""
        files = _create_temp_files(tmp_path, ["a.txt", "b.txt"])
        await db.mark_processing(files[0], "run_001")
        await db.mark_processing(files[1], "run_001")

        reset_count = await db.reset_stale_processing()
        assert reset_count == 2

        stats = await db.get_stats()
        assert stats["processing"] == 0

    @pytest.mark.asyncio
    async def test_completed_not_reset(self, db, tmp_path):
        """완료 상태는 리셋하지 않음."""
        files = _create_temp_files(tmp_path, ["a.txt"])
        await db.mark_processing(files[0], "run_001")
        await db.mark_completed(files[0], 3)

        reset_count = await db.reset_stale_processing()
        assert reset_count == 0

    @pytest.mark.asyncio
    async def test_no_stale(self, db):
        """processing 파일이 없으면 0 반환."""
        reset_count = await db.reset_stale_processing()
        assert reset_count == 0


class TestCheckpoint:
    @pytest.mark.asyncio
    async def test_save_and_get(self, db):
        """체크포인트 저장/조회."""
        await db.save_checkpoint("last_seq_id", "1234")
        value = await db.get_checkpoint("last_seq_id")
        assert value == "1234"

    @pytest.mark.asyncio
    async def test_overwrite(self, db):
        """체크포인트 덮어쓰기."""
        await db.save_checkpoint("key1", "value1")
        await db.save_checkpoint("key1", "value2")
        assert await db.get_checkpoint("key1") == "value2"

    @pytest.mark.asyncio
    async def test_missing_key(self, db):
        """존재하지 않는 키는 None 반환."""
        assert await db.get_checkpoint("nonexistent") is None
