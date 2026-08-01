r"""문서 수집 파이프라인 오케스트레이션.

DOCUMENTS_ROOT 하위 전체 문서를
변환 → 청킹 → 임베딩 → 벡터DB 적재하는 파이프라인.
"""

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from tqdm import tqdm

from app.core.config import settings
from app.embedding.embedder import DocumentEmbedder
from app.ingestion.chunker import DocumentChunker
from app.ingestion.converters import (
    HwpConverter,
    OfficeConverter,
    PdfConverter,
    TextConverter,
)
from app.ingestion.metadata_normalizer import MetadataNormalizer
from app.ingestion.parallel_pipeline import ParallelIngestionPipeline
from app.vectordb.store import VectorStore

logger = logging.getLogger(__name__)


@dataclass
class IngestionStats:
    """수집 통계."""
    total_files: int = 0
    processed: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0
    total_chunks: int = 0
    elapsed_seconds: float = 0.0
    errors: list = field(default_factory=list)
    run_id: str = ""
    retry_count: int = 0
    dead_letter_count: int = 0

    def summary(self) -> dict:
        result = {
            "total_files": self.total_files,
            "processed": self.processed,
            "success": self.success,
            "failed": self.failed,
            "skipped": self.skipped,
            "total_chunks": self.total_chunks,
            "success_rate": f"{self.success / max(self.processed, 1) * 100:.1f}%",
            "elapsed": f"{self.elapsed_seconds:.1f}s",
        }
        if self.run_id:
            result["run_id"] = self.run_id
        if self.retry_count:
            result["retry_count"] = self.retry_count
        if self.dead_letter_count:
            result["dead_letter_count"] = self.dead_letter_count
        return result


class IngestionPipeline:
    """문서 수집 → 변환 → 청킹 → 임베딩 → 벡터DB 적재."""

    # RAG 대상 파일 확장자
    TARGET_EXTENSIONS = {
        ".hwp", ".doc", ".docx", ".ppt", ".pptx",
        ".xls", ".xlsx", ".pdf", ".txt", ".sql",
    }

    def __init__(self):
        self.converters = [
            HwpConverter(),
            OfficeConverter(),
            PdfConverter(),
            TextConverter(),
        ]
        self.chunker = DocumentChunker()
        self.embedder = DocumentEmbedder()
        self.store = VectorStore()
        self.normalizer = MetadataNormalizer()

    def _get_converter(self, file_path: Path):
        for converter in self.converters:
            if converter.can_handle(file_path):
                return converter
        return None

    async def process_file(self, file_path: Path) -> dict:
        """단일 파일 처리: 변환 → 청킹 → 메타데이터."""
        converter = self._get_converter(file_path)
        if not converter:
            return {"status": "skipped", "reason": "unsupported format"}

        try:
            text = await converter.convert(file_path)
        except Exception as e:
            return {"status": "failed", "reason": str(e)}

        if not text or len(text.strip()) < 10:
            return {"status": "failed", "reason": "empty or too short"}

        metadata = self.normalizer.normalize(file_path)
        chunks = self.chunker.chunk(text, metadata)

        if not chunks:
            return {"status": "failed", "reason": "no chunks generated"}

        return {
            "status": "success",
            "file_path": str(file_path),
            "text_length": len(text),
            "chunks": chunks,
            "metadata": metadata,
        }

    async def process_and_store(self, file_path: Path) -> dict:
        """단일 파일: 변환 → 청킹 → 임베딩 → 저장."""
        result = await self.process_file(file_path)
        if result["status"] != "success":
            return result

        chunks = result["chunks"]
        texts = [c.text for c in chunks]

        # 임베딩 생성
        embeddings = await self.embedder.embed_batch(texts)

        # 벡터DB 저장
        self.store.upsert_batch(
            ids=[c.chunk_id for c in chunks],
            embeddings=embeddings,
            metadatas=[c.metadata for c in chunks],
            documents=texts,
        )

        result["chunks"] = len(chunks)
        return result

    def scan_files(
        self,
        directory: Path | None = None,
        max_files: int | None = None,
    ) -> list[Path]:
        """디렉토리에서 대상 파일 목록 스캔."""
        root = directory or Path(settings.DOCUMENTS_ROOT)
        files = []

        for f in root.rglob("*"):
            if f.is_file() and f.suffix.lower() in self.TARGET_EXTENSIONS:
                files.append(f)
                if max_files and len(files) >= max_files:
                    break

        return files

    async def run_sequential(
        self,
        directory: Path | None = None,
        max_files: int | None = None,
        embed: bool = True,
    ) -> IngestionStats:
        """순차 파이프라인 실행 (Phase 1 호환)."""
        stats = IngestionStats()
        start = time.time()

        files = self.scan_files(directory, max_files)
        stats.total_files = len(files)

        logger.info("Starting sequential ingestion: %d files", stats.total_files)

        for file_path in tqdm(files, desc="Ingesting"):
            stats.processed += 1
            try:
                if embed:
                    result = await self.process_and_store(file_path)
                else:
                    result = await self.process_file(file_path)

                if result["status"] == "success":
                    stats.success += 1
                    chunk_count = result["chunks"] if isinstance(result["chunks"], int) else len(result["chunks"])
                    stats.total_chunks += chunk_count
                elif result["status"] == "skipped":
                    stats.skipped += 1
                else:
                    stats.failed += 1
                    stats.errors.append({
                        "file": str(file_path),
                        "reason": result.get("reason", "unknown"),
                    })
            except Exception as e:
                stats.failed += 1
                stats.errors.append({"file": str(file_path), "reason": str(e)})
                logger.error("Pipeline error for %s: %s", file_path, e)

        stats.elapsed_seconds = time.time() - start
        logger.info("Ingestion complete: %s", stats.summary())
        return stats

    # 하위 호환: run() → run_sequential()
    async def run(
        self,
        directory: Path | None = None,
        max_files: int | None = None,
        embed: bool = True,
    ) -> IngestionStats:
        """전체 파이프라인 실행 (하위 호환)."""
        return await self.run_sequential(directory, max_files, embed)

    async def run_parallel(
        self,
        directory: Path | None = None,
        max_files: int | None = None,
        resume: bool = True,
    ) -> IngestionStats:
        """병렬 파이프라인 실행."""
        parallel = ParallelIngestionPipeline()
        start = time.time()

        result = await parallel.run(directory=directory, max_files=max_files, resume=resume)

        stats = IngestionStats(
            total_files=result.get("completed", 0) + result.get("failed", 0) + result.get("processing", 0),
            processed=result.get("completed", 0) + result.get("failed", 0),
            success=result.get("completed", 0),
            failed=result.get("failed", 0),
            total_chunks=result.get("total_chunks", 0),
            elapsed_seconds=time.time() - start,
            run_id=parallel.run_id,
        )
        return stats
