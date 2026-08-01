r"""병렬 문서 수집 파이프라인.

Producer-Consumer 아키텍처:
    scan_files() → [file_queue] → N converter workers → [chunk_queue]
                                                             ↓
                                                      embedding batcher → [store_queue]
                                                                              ↓
                                                                        store worker (1)
"""

import asyncio
import logging
import signal
import time
import uuid
from pathlib import Path

from app.core.config import settings
from app.embedding.embedder import DocumentEmbedder
from app.ingestion.chunker import DocumentChunker
from app.ingestion.converters import (
    HwpConverter,
    OfficeConverter,
    PdfConverter,
    TextConverter,
)
from app.ingestion.error_handler import ErrorClassifier, ErrorType, RetryHandler
from app.ingestion.metadata_normalizer import MetadataNormalizer
from app.ingestion.progress_db import ProgressDB
from app.ingestion.rate_limiter import RateLimiter
from app.ingestion.token_counter import count_tokens
from app.vectordb.store import VectorStore

logger = logging.getLogger(__name__)

# 대상 파일 확장자
TARGET_EXTENSIONS = {
    ".hwp", ".doc", ".docx", ".ppt", ".pptx",
    ".xls", ".xlsx", ".pdf", ".txt", ".sql",
}


class ParallelIngestionPipeline:
    """병렬 문서 수집 파이프라인."""

    def __init__(
        self,
        converter_concurrency: int = settings.CONVERTER_CONCURRENCY,
        store_batch_size: int = settings.STORE_BATCH_SIZE,
        embedding_batch_max_tokens: int = settings.EMBEDDING_BATCH_MAX_TOKENS,
    ):
        self.converter_concurrency = converter_concurrency
        self.store_batch_size = store_batch_size
        self.embedding_batch_max_tokens = embedding_batch_max_tokens

        # 컴포넌트
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
        self.progress_db = ProgressDB()
        self.rate_limiter = RateLimiter()
        self.retry_handler = RetryHandler()

        # 큐
        self.file_queue: asyncio.Queue[Path | None] = asyncio.Queue(maxsize=1000)
        self.chunk_queue: asyncio.Queue[tuple | None] = asyncio.Queue(maxsize=500)
        self.store_queue: asyncio.Queue[tuple | None] = asyncio.Queue(maxsize=200)

        # 상태
        self.shutdown_event = asyncio.Event()
        self.run_id = ""
        self._start_time = 0.0
        self._converter_done_count = 0

    def _get_converter(self, file_path: Path):
        for converter in self.converters:
            if converter.can_handle(file_path):
                return converter
        return None

    def scan_files(
        self,
        directory: Path | None = None,
        max_files: int | None = None,
    ) -> list[Path]:
        """디렉토리에서 대상 파일 목록 스캔."""
        root = directory or Path(settings.DOCUMENTS_ROOT)
        files = []
        for f in root.rglob("*"):
            if f.is_file() and f.suffix.lower() in TARGET_EXTENSIONS:
                files.append(f)
                if max_files and len(files) >= max_files:
                    break
        return files

    def _setup_signal_handlers(self):
        """Graceful shutdown을 위한 시그널 핸들러 설정."""
        def _signal_handler(sig, frame):
            logger.info("Shutdown signal received. Finishing current work...")
            self.shutdown_event.set()

        try:
            signal.signal(signal.SIGINT, _signal_handler)
            signal.signal(signal.SIGTERM, _signal_handler)
        except (ValueError, OSError):
            # 메인 스레드가 아닌 경우 시그널 설정 불가
            pass

    async def run(
        self,
        directory: Path | None = None,
        max_files: int | None = None,
        resume: bool = True,
    ) -> dict:
        """병렬 파이프라인 실행 (인덱스 기반)."""
        self.run_id = f"run_{uuid.uuid4().hex[:8]}"
        self._start_time = time.time()
        self._converter_done_count = 0
        self.shutdown_event.clear()
        self._setup_signal_handlers()

        await self.progress_db.initialize()
        await self.rate_limiter.start()

        try:
            # 1. 강제 종료로 남은 processing 파일 복구
            stale_count = await self.progress_db.reset_stale_processing()
            if stale_count:
                logger.info("Recovered %d stale processing files", stale_count)

            # 2. 파일 인덱스 구축 (최초 1회 전체 스캔, 이후 증분)
            root = directory or Path(settings.DOCUMENTS_ROOT)
            new_indexed = await self.progress_db.build_file_index(
                root, TARGET_EXTENSIONS,
            )
            index_count = await self.progress_db.get_index_count()
            logger.info(
                "File index: %d total files (%d newly indexed)",
                index_count, new_indexed,
            )

            # 3. LEFT JOIN으로 미처리 파일 조회 (O(1))
            files = await self.progress_db.get_unprocessed_from_index()

            # 4. max_files 제한 적용
            if max_files and len(files) > max_files:
                files = files[:max_files]

            logger.info(
                "Files to process: %d (index=%d, max_files=%s)",
                len(files), index_count, max_files or "all",
            )

            if not files:
                logger.info("No files to process")
                return await self.progress_db.get_stats(self.run_id)

            await self.progress_db.create_run(self.run_id, len(files))

            # 5. 워커 태스크 생성
            tasks = []

            # Producer: 파일 큐잉
            tasks.append(asyncio.create_task(
                self._file_producer(files), name="file_producer"
            ))

            # Converter workers
            for i in range(self.converter_concurrency):
                tasks.append(asyncio.create_task(
                    self._converter_worker(i), name=f"converter_{i}"
                ))

            # Embedding batcher
            tasks.append(asyncio.create_task(
                self._embedding_batcher(), name="embedding_batcher"
            ))

            # Store worker
            tasks.append(asyncio.create_task(
                self._store_worker(), name="store_worker"
            ))

            # Progress reporter
            tasks.append(asyncio.create_task(
                self._progress_reporter(), name="progress_reporter"
            ))

            # 6. 모든 워커 완료 대기
            await asyncio.gather(*tasks)

            # 7. 실행 완료
            await self.progress_db.finish_run(self.run_id)
            stats = await self.progress_db.get_stats(self.run_id)
            elapsed = time.time() - self._start_time
            logger.info(
                "Pipeline complete in %.1fs: %s", elapsed, stats
            )
            return stats

        finally:
            await self.rate_limiter.stop()
            await self.progress_db.close()

    async def _file_producer(self, files: list[Path]):
        """미처리 파일을 큐에 넣기. shutdown_event 시 조기 종료."""
        produced = 0
        for fp in files:
            if self.shutdown_event.is_set():
                logger.info(
                    "Shutdown: stopping file producer after %d/%d files",
                    produced, len(files),
                )
                break
            await self.file_queue.put(fp)
            produced += 1

        # 종료 신호: converter 수만큼 None
        for _ in range(self.converter_concurrency):
            await self.file_queue.put(None)

    async def _converter_worker(self, worker_id: int):
        """파일 변환 + 청킹 워커."""
        while True:
            file_path = await self.file_queue.get()
            if file_path is None:
                self.file_queue.task_done()
                break

            try:
                await self.progress_db.mark_processing(file_path, self.run_id)

                converter = self._get_converter(file_path)
                if not converter:
                    await self.progress_db.mark_failed(file_path, "unsupported format")
                    continue

                # 변환 (재시도 포함)
                text = await self.retry_handler.execute_with_retry(
                    lambda fp=file_path, cv=converter: cv.convert(fp),
                    description=str(file_path),
                )

                if not text or len(text.strip()) < 10:
                    await self.progress_db.mark_failed(file_path, "empty or too short")
                    continue

                # 메타데이터 정규화 + 청킹
                metadata = self.normalizer.normalize(file_path)
                chunks = self.chunker.chunk(text, metadata)

                if not chunks:
                    await self.progress_db.mark_failed(file_path, "no chunks generated")
                    continue

                # 청크 큐에 넣기
                await self.chunk_queue.put((file_path, chunks))

            except Exception as e:
                error_type = ErrorClassifier.classify(e)
                await self.progress_db.mark_failed(file_path, f"[{error_type.value}] {e}")
                logger.warning("Worker %d failed on %s: %s", worker_id, file_path, e)
            finally:
                self.file_queue.task_done()

        # 이 워커 완료. 모든 converter가 끝나면 chunk_queue에 종료 신호
        self._converter_done_count += 1
        if self._converter_done_count >= self.converter_concurrency:
            await self.chunk_queue.put(None)

    async def _embedding_batcher(self):
        """청크를 모아서 배치 임베딩 후 store_queue로 전달."""
        pending_chunks = []
        pending_file_paths = []
        pending_tokens = 0

        while True:
            # 타임아웃으로 주기적 플러시
            try:
                item = await asyncio.wait_for(self.chunk_queue.get(), timeout=2.0)
            except asyncio.TimeoutError:
                if pending_chunks:
                    await self._flush_embedding_batch(pending_chunks, pending_file_paths)
                    pending_chunks = []
                    pending_file_paths = []
                    pending_tokens = 0
                continue

            if item is None:
                # 남은 청크 플러시
                if pending_chunks:
                    await self._flush_embedding_batch(pending_chunks, pending_file_paths)
                self.chunk_queue.task_done()
                # store_queue 종료 신호
                await self.store_queue.put(None)
                break

            file_path, chunks = item
            batch_tokens = sum(count_tokens(c.text) for c in chunks)

            # 배치가 너무 크면 먼저 플러시
            if pending_chunks and pending_tokens + batch_tokens > self.embedding_batch_max_tokens:
                await self._flush_embedding_batch(pending_chunks, pending_file_paths)
                pending_chunks = []
                pending_file_paths = []
                pending_tokens = 0

            pending_chunks.extend(chunks)
            pending_file_paths.append(file_path)
            pending_tokens += batch_tokens
            self.chunk_queue.task_done()

    async def _flush_embedding_batch(self, chunks, file_paths):
        """누적된 청크에 임베딩을 생성하고 store_queue로 전달."""
        texts = [c.text for c in chunks]

        try:
            embeddings = await self.retry_handler.execute_with_retry(
                lambda: self.embedder.embed_batch_rated(texts, self.rate_limiter),
                description=f"embedding batch ({len(texts)} chunks)",
            )

            ids = [c.chunk_id for c in chunks]
            metadatas = [c.metadata for c in chunks]

            await self.store_queue.put((ids, embeddings, metadatas, texts, file_paths, chunks))

        except Exception as e:
            logger.error("Embedding batch failed: %s", e)
            # 개별 파일을 실패로 기록
            for fp in file_paths:
                await self.progress_db.mark_failed(fp, f"embedding error: {e}")

    async def _store_worker(self):
        """벡터DB 배치 저장 워커."""
        while True:
            item = await self.store_queue.get()
            if item is None:
                self.store_queue.task_done()
                break

            ids, embeddings, metadatas, documents, file_paths, chunks = item

            try:
                await self.store.upsert_batch_async(
                    ids=ids,
                    embeddings=embeddings,
                    metadatas=metadatas,
                    documents=documents,
                    batch_size=self.store_batch_size,
                )

                # 파일별 청크 수 계산하여 완료 기록
                file_chunk_counts: dict[str, int] = {}
                for chunk in chunks:
                    src = chunk.metadata.get("source_path", "")
                    file_chunk_counts[src] = file_chunk_counts.get(src, 0) + 1

                for fp in file_paths:
                    count = file_chunk_counts.get(str(fp), 0)
                    await self.progress_db.mark_completed(fp, count)

            except Exception as e:
                logger.error("Store batch failed: %s", e)
                for fp in file_paths:
                    await self.progress_db.mark_failed(fp, f"store error: {e}")
            finally:
                self.store_queue.task_done()

    async def _progress_reporter(self):
        """주기적으로 진행률 로그 출력."""
        interval = settings.PROGRESS_LOG_INTERVAL
        while not self.shutdown_event.is_set():
            await asyncio.sleep(interval)
            try:
                stats = await self.progress_db.get_stats(self.run_id)
                elapsed = time.time() - self._start_time
                completed = stats.get("completed", 0)
                processing = stats.get("processing", 0)
                failed = stats.get("failed", 0)
                total_chunks = stats.get("total_chunks", 0)

                # store_queue가 비었고, chunk_queue가 비었고, 모든 converter가 끝나면 종료
                if (self._converter_done_count >= self.converter_concurrency
                        and self.chunk_queue.empty()
                        and self.store_queue.empty()
                        and processing == 0):
                    break

                logger.info(
                    "[%.0fs] completed=%d failed=%d processing=%d chunks=%d",
                    elapsed, completed, failed, processing, total_chunks,
                )
            except Exception:
                pass
