"""진행률 조회 API 엔드포인트."""

from fastapi import APIRouter

from app.ingestion.progress_db import ProgressDB

router = APIRouter()


@router.get("/")
async def get_progress():
    """현재 진행률 통계."""
    db = ProgressDB()
    await db.initialize()
    try:
        stats = await db.get_stats()
        return stats
    finally:
        await db.close()


@router.get("/runs")
async def get_runs():
    """실행 이력 목록."""
    db = ProgressDB()
    await db.initialize()
    try:
        return await db.get_runs()
    finally:
        await db.close()


@router.get("/runs/{run_id}")
async def get_run(run_id: str):
    """단일 실행 상세."""
    db = ProgressDB()
    await db.initialize()
    try:
        result = await db.get_run(run_id)
        if result is None:
            return {"error": "Run not found"}
        return result
    finally:
        await db.close()


@router.get("/dead-letters")
async def get_dead_letters():
    """영구 실패 파일 목록."""
    db = ProgressDB()
    await db.initialize()
    try:
        return await db.get_dead_letters()
    finally:
        await db.close()


@router.post("/retry-failed")
async def retry_failed():
    """실패 파일 재시도 대상 초기화."""
    db = ProgressDB()
    await db.initialize()
    try:
        retryable = await db.get_retryable_files()
        return {"retryable_count": len(retryable), "files": retryable}
    finally:
        await db.close()
