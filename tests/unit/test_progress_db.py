"""progress_db 단위 테스트 (in-memory SQLite)."""

import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

from app.ingestion.progress_db import ProgressDB


@pytest_asyncio.fixture
async def db(tmp_path):
    """임시 SQLite DB."""
    db_path = str(tmp_path / "test_progress.db")
    pdb = ProgressDB(db_path=db_path)
    await pdb.initialize()
    yield pdb
    await pdb.close()


class TestProgressDB:
    @pytest.mark.asyncio
    async def test_create_run(self, db):
        await db.create_run("run_001", total_files=100)
        run = await db.get_run("run_001")
        assert run is not None
        assert run["total_files"] == 100

    @pytest.mark.asyncio
    async def test_mark_processing_and_completed(self, db):
        # 임시 파일 생성
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test")
            fp = Path(f.name)

        await db.create_run("run_001", total_files=1)
        await db.mark_processing(fp, "run_001")

        stats = await db.get_stats("run_001")
        assert stats["processing"] == 1

        await db.mark_completed(fp, chunks_count=5)
        stats = await db.get_stats("run_001")
        assert stats["completed"] == 1
        assert stats["total_chunks"] == 5

        fp.unlink()

    @pytest.mark.asyncio
    async def test_mark_failed(self, db):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test")
            fp = Path(f.name)

        await db.create_run("run_001", total_files=1)
        await db.mark_processing(fp, "run_001")
        await db.mark_failed(fp, "conversion error")

        stats = await db.get_stats("run_001")
        assert stats["failed"] == 1

        fp.unlink()

    @pytest.mark.asyncio
    async def test_get_unprocessed_files(self, db):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test")
            fp1 = Path(f.name)

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test2")
            fp2 = Path(f.name)

        # fp1만 완료 처리
        await db.mark_processing(fp1, "run_001")
        await db.mark_completed(fp1, 3)

        unprocessed = await db.get_unprocessed_files([fp1, fp2])
        assert len(unprocessed) == 1
        assert unprocessed[0] == fp2

        fp1.unlink()
        fp2.unlink()

    @pytest.mark.asyncio
    async def test_get_retryable_files(self, db):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test")
            fp = Path(f.name)

        await db.mark_processing(fp, "run_001")
        await db.mark_failed(fp, "error 1")  # retry_count = 1

        retryable = await db.get_retryable_files(max_retries=3)
        assert len(retryable) == 1

        fp.unlink()

    @pytest.mark.asyncio
    async def test_get_dead_letters(self, db):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test")
            fp = Path(f.name)

        await db.mark_processing(fp, "run_001")
        # 3번 실패 (retry_count=3)
        await db.mark_failed(fp, "error 1")
        await db.mark_failed(fp, "error 2")
        await db.mark_failed(fp, "error 3")

        dead = await db.get_dead_letters(max_retries=3)
        assert len(dead) == 1
        assert dead[0]["retry_count"] == 3

        fp.unlink()

    @pytest.mark.asyncio
    async def test_finish_run(self, db):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test")
            fp = Path(f.name)

        await db.create_run("run_001", total_files=1)
        await db.mark_processing(fp, "run_001")
        await db.mark_completed(fp, 5)
        await db.finish_run("run_001")

        run = await db.get_run("run_001")
        assert run["finished_at"] is not None
        assert run["completed_files"] == 1

        fp.unlink()

    @pytest.mark.asyncio
    async def test_get_runs(self, db):
        await db.create_run("run_001", total_files=10)
        await db.create_run("run_002", total_files=20)

        runs = await db.get_runs()
        assert len(runs) == 2
