"""문서 수집 API 엔드포인트."""

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from app.ingestion.pipeline import IngestionPipeline

router = APIRouter()
pipeline = IngestionPipeline()


class IngestFileRequest(BaseModel):
    file_path: str


class IngestDirectoryRequest(BaseModel):
    directory: str | None = None
    max_files: int | None = None
    embed: bool = False
    parallel: bool = False
    resume: bool = True


@router.post("/file")
async def ingest_file(request: IngestFileRequest):
    """단일 파일 수집 (변환 + 청킹만, 임베딩 없음)."""
    result = await pipeline.process_file(Path(request.file_path))
    if result["status"] == "success":
        result["chunks"] = len(result["chunks"])
    return result


@router.post("/directory")
async def ingest_directory(request: IngestDirectoryRequest, background_tasks: BackgroundTasks):
    """디렉토리 일괄 수집. parallel=true 시 병렬 처리."""
    directory = Path(request.directory) if request.directory else None

    if request.parallel:
        stats = await pipeline.run_parallel(
            directory=directory,
            max_files=request.max_files,
            resume=request.resume,
        )
    else:
        stats = await pipeline.run(
            directory=directory,
            max_files=request.max_files,
            embed=request.embed,
        )
    return stats.summary()


@router.get("/status")
async def ingestion_status():
    """벡터DB 저장 상태 조회."""
    try:
        count = pipeline.store.count()
        return {"status": "ok", "vectors_stored": count}
    except Exception as e:
        return {"status": "error", "message": str(e)}
