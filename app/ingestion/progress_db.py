"""SQLite 기반 진행률 추적 DB.

WAL 모드로 동시 읽기/쓰기 최적화.
중단 후 재개(resume) 기능 지원.
"""

import hashlib
import logging
import time
from pathlib import Path

import aiosqlite

from app.core.config import settings

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ingestion_runs (
    run_id TEXT PRIMARY KEY,
    started_at REAL NOT NULL,
    finished_at REAL,
    total_files INTEGER DEFAULT 0,
    completed_files INTEGER DEFAULT 0,
    failed_files INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS processed_files (
    file_path TEXT PRIMARY KEY,
    file_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'processing',
    chunks_count INTEGER DEFAULT 0,
    error_msg TEXT,
    retry_count INTEGER DEFAULT 0,
    run_id TEXT,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS file_index (
    seq_id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT UNIQUE NOT NULL,
    file_hash TEXT NOT NULL,
    file_size INTEGER DEFAULT 0,
    indexed_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS checkpoint (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_processed_status ON processed_files(status);
CREATE INDEX IF NOT EXISTS idx_processed_run ON processed_files(run_id);
"""


def _file_hash(file_path: Path) -> str:
    """파일 크기 + 수정 시간으로 빠른 해시 생성."""
    try:
        stat = file_path.stat()
        raw = f"{file_path}:{stat.st_size}:{stat.st_mtime}"
        return hashlib.md5(raw.encode()).hexdigest()
    except OSError:
        return ""


class ProgressDB:
    """진행률 추적 DB."""

    def __init__(self, db_path: str = settings.PROGRESS_DB_PATH):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self):
        """DB 초기화 및 스키마 생성."""
        self._db = await aiosqlite.connect(self.db_path)
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA synchronous=NORMAL")
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def close(self):
        if self._db:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("ProgressDB not initialized. Call initialize() first.")
        return self._db

    async def create_run(self, run_id: str, total_files: int):
        """새 실행 레코드 생성."""
        await self.db.execute(
            "INSERT OR REPLACE INTO ingestion_runs (run_id, started_at, total_files) VALUES (?, ?, ?)",
            (run_id, time.time(), total_files),
        )
        await self.db.commit()

    async def finish_run(self, run_id: str):
        """실행 완료 기록."""
        async with self.db.execute(
            "SELECT COUNT(*) FROM processed_files WHERE run_id=? AND status='completed'",
            (run_id,),
        ) as cur:
            row = await cur.fetchone()
            completed = row[0] if row else 0

        async with self.db.execute(
            "SELECT COUNT(*) FROM processed_files WHERE run_id=? AND status='failed'",
            (run_id,),
        ) as cur:
            row = await cur.fetchone()
            failed = row[0] if row else 0

        await self.db.execute(
            "UPDATE ingestion_runs SET finished_at=?, completed_files=?, failed_files=? WHERE run_id=?",
            (time.time(), completed, failed, run_id),
        )
        await self.db.commit()

    async def get_unprocessed_files(self, file_paths: list[Path]) -> list[Path]:
        """완료된 파일을 제외하고 미처리 파일 반환. 파일 변경 감지 포함."""
        unprocessed = []

        for fp in file_paths:
            current_hash = _file_hash(fp)
            async with self.db.execute(
                "SELECT file_hash, status FROM processed_files WHERE file_path=?",
                (str(fp),),
            ) as cur:
                row = await cur.fetchone()

            if row is None:
                unprocessed.append(fp)
            elif row[1] != "completed" or row[0] != current_hash:
                # 미완료이거나 파일이 변경됨
                unprocessed.append(fp)

        return unprocessed

    # --- 파일 인덱스 ---

    async def build_file_index(
        self,
        directory: Path,
        extensions: set[str],
        batch_size: int = 1000,
    ) -> int:
        """파일 인덱스 구축. 최초 1회 전체 스캔, 이후 증분만 추가.

        Returns:
            인덱스에 새로 추가된 파일 수.
        """
        # 기존 인덱스의 파일 경로 집합
        existing: set[str] = set()
        async with self.db.execute("SELECT file_path FROM file_index") as cur:
            async for row in cur:
                existing.add(row[0])

        new_count = 0
        batch: list[tuple] = []
        now = time.time()

        for f in directory.rglob("*"):
            if not f.is_file() or f.suffix.lower() not in extensions:
                continue
            fp_str = str(f)
            if fp_str in existing:
                continue

            fhash = _file_hash(f)
            try:
                fsize = f.stat().st_size
            except OSError:
                fsize = 0

            batch.append((fp_str, fhash, fsize, now))
            new_count += 1

            if len(batch) >= batch_size:
                await self.db.executemany(
                    "INSERT OR IGNORE INTO file_index (file_path, file_hash, file_size, indexed_at) VALUES (?, ?, ?, ?)",
                    batch,
                )
                await self.db.commit()
                batch.clear()

        if batch:
            await self.db.executemany(
                "INSERT OR IGNORE INTO file_index (file_path, file_hash, file_size, indexed_at) VALUES (?, ?, ?, ?)",
                batch,
            )
            await self.db.commit()

        total_indexed = len(existing) + new_count
        logger.info(
            "File index: %d total (%d new, %d existing)",
            total_indexed, new_count, len(existing),
        )
        return new_count

    async def get_index_count(self) -> int:
        """인덱스에 등록된 파일 수."""
        async with self.db.execute("SELECT COUNT(*) FROM file_index") as cur:
            row = await cur.fetchone()
        return row[0] if row else 0

    async def get_unprocessed_from_index(self) -> list[Path]:
        """LEFT JOIN으로 미처리 파일 조회. 결정적 seq_id 순서.

        completed 상태가 아닌 모든 파일을 반환 (신규, processing, failed 포함).
        """
        query = """
            SELECT fi.file_path
            FROM file_index fi
            LEFT JOIN processed_files pf ON fi.file_path = pf.file_path
            WHERE pf.file_path IS NULL OR pf.status != 'completed'
            ORDER BY fi.seq_id
        """
        async with self.db.execute(query) as cur:
            rows = await cur.fetchall()
        return [Path(row[0]) for row in rows]

    async def reset_stale_processing(self) -> int:
        """강제 종료로 남은 processing 상태 파일을 pending으로 리셋.

        Returns:
            리셋된 파일 수.
        """
        async with self.db.execute(
            "SELECT COUNT(*) FROM processed_files WHERE status='processing'",
        ) as cur:
            row = await cur.fetchone()
            stale_count = row[0] if row else 0

        if stale_count > 0:
            await self.db.execute(
                "UPDATE processed_files SET status='pending', updated_at=? WHERE status='processing'",
                (time.time(),),
            )
            await self.db.commit()
            logger.info("Reset %d stale processing files to pending", stale_count)

        return stale_count

    # --- 체크포인트 ---

    async def save_checkpoint(self, key: str, value: str):
        """체크포인트 저장."""
        await self.db.execute(
            "INSERT OR REPLACE INTO checkpoint (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, time.time()),
        )
        await self.db.commit()

    async def get_checkpoint(self, key: str) -> str | None:
        """체크포인트 조회."""
        async with self.db.execute(
            "SELECT value FROM checkpoint WHERE key=?", (key,),
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row else None

    async def mark_processing(self, file_path: Path, run_id: str):
        """파일 처리 시작."""
        fhash = _file_hash(file_path)
        await self.db.execute(
            """INSERT INTO processed_files (file_path, file_hash, status, run_id, updated_at)
               VALUES (?, ?, 'processing', ?, ?)
               ON CONFLICT(file_path) DO UPDATE SET
                 file_hash=excluded.file_hash, status='processing',
                 run_id=excluded.run_id, updated_at=excluded.updated_at""",
            (str(file_path), fhash, run_id, time.time()),
        )
        await self.db.commit()

    async def mark_completed(self, file_path: Path, chunks_count: int):
        """파일 처리 완료."""
        await self.db.execute(
            "UPDATE processed_files SET status='completed', chunks_count=?, error_msg=NULL, updated_at=? WHERE file_path=?",
            (chunks_count, time.time(), str(file_path)),
        )
        await self.db.commit()

    async def mark_failed(self, file_path: Path, error_msg: str):
        """파일 처리 실패."""
        await self.db.execute(
            """UPDATE processed_files SET status='failed', error_msg=?,
               retry_count=retry_count+1, updated_at=? WHERE file_path=?""",
            (error_msg, time.time(), str(file_path)),
        )
        await self.db.commit()

    async def get_retryable_files(self, max_retries: int = settings.MAX_RETRIES) -> list[str]:
        """재시도 가능한 실패 파일 경로 목록."""
        async with self.db.execute(
            "SELECT file_path FROM processed_files WHERE status='failed' AND retry_count < ?",
            (max_retries,),
        ) as cur:
            rows = await cur.fetchall()
        return [row[0] for row in rows]

    async def get_stats(self, run_id: str | None = None) -> dict:
        """실시간 통계."""
        where = "WHERE run_id=?" if run_id else ""
        params: tuple = (run_id,) if run_id else ()

        stats = {}
        for status in ("processing", "completed", "failed"):
            async with self.db.execute(
                f"SELECT COUNT(*) FROM processed_files {where}" +
                (" AND " if where else " WHERE ") + "status=?",
                (*params, status),
            ) as cur:
                row = await cur.fetchone()
                stats[status] = row[0] if row else 0

        async with self.db.execute(
            f"SELECT COALESCE(SUM(chunks_count), 0) FROM processed_files {where}" +
            (" AND " if where else " WHERE ") + "status='completed'",
            params,
        ) as cur:
            row = await cur.fetchone()
            stats["total_chunks"] = row[0] if row else 0

        return stats

    async def get_dead_letters(self, max_retries: int = settings.MAX_RETRIES) -> list[dict]:
        """재시도 한도 초과 영구 실패 파일 목록."""
        async with self.db.execute(
            "SELECT file_path, error_msg, retry_count FROM processed_files WHERE status='failed' AND retry_count >= ?",
            (max_retries,),
        ) as cur:
            rows = await cur.fetchall()
        return [
            {"file_path": row[0], "error_msg": row[1], "retry_count": row[2]}
            for row in rows
        ]

    async def get_runs(self) -> list[dict]:
        """전체 실행 이력."""
        async with self.db.execute(
            "SELECT run_id, started_at, finished_at, total_files, completed_files, failed_files FROM ingestion_runs ORDER BY started_at DESC",
        ) as cur:
            rows = await cur.fetchall()
        return [
            {
                "run_id": row[0],
                "started_at": row[1],
                "finished_at": row[2],
                "total_files": row[3],
                "completed_files": row[4],
                "failed_files": row[5],
            }
            for row in rows
        ]

    async def get_run(self, run_id: str) -> dict | None:
        """단일 실행 상세."""
        async with self.db.execute(
            "SELECT run_id, started_at, finished_at, total_files, completed_files, failed_files FROM ingestion_runs WHERE run_id=?",
            (run_id,),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return {
            "run_id": row[0],
            "started_at": row[1],
            "finished_at": row[2],
            "total_files": row[3],
            "completed_files": row[4],
            "failed_files": row[5],
        }
