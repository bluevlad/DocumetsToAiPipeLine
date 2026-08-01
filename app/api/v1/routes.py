from fastapi import APIRouter

from app.api.v1.endpoints import ingest, search, analyze, progress

router = APIRouter()

router.include_router(ingest.router, prefix="/ingest", tags=["ingestion"])
router.include_router(search.router, prefix="/search", tags=["search"])
router.include_router(analyze.router, prefix="/analyze", tags=["analyze"])
router.include_router(progress.router, prefix="/progress", tags=["progress"])
