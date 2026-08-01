r"""전체 문서 적재 실행 스크립트.

전체 문서를 병렬로 변환 → 청킹 → 임베딩 → 벡터DB 적재.
중단 후 재실행하면 파일 인덱스를 활용하여 미처리 파일만 빠르게 조회.

사용법:
    py scripts/run_full_ingestion.py                    # 전체 실행 (resume)
    py scripts/run_full_ingestion.py --fresh             # 처음부터 새로 실행
    py scripts/run_full_ingestion.py --max-files 1000    # 최대 1000개만
    py scripts/run_full_ingestion.py --workers 5         # 변환 워커 5개
    py scripts/run_full_ingestion.py --status             # 현재 진행률만 확인

임베딩 프로바이더:
    - local (기본): sentence-transformers GPU 임베딩 (무료, ~15-30분)
    - openai: OpenAI API (~$8.50 USD, ~80-90분)

환경 요구:
    - EMBEDDING_PROVIDER=local: GPU 권장 (CUDA)
    - EMBEDDING_PROVIDER=openai: .env에 OPENAI_API_KEY 설정
    - DOCUMENTS_ROOT 경로 접근 가능
"""

import argparse
import asyncio
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.ingestion.parallel_pipeline import ParallelIngestionPipeline
from app.ingestion.progress_db import ProgressDB

# 로그: 콘솔 + 파일 동시 출력
LOG_FILE = f"ingestion_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger("full_ingestion")


async def show_status():
    """현재 진행률 확인."""
    db = ProgressDB()
    await db.initialize()
    try:
        stats = await db.get_stats()
        runs = await db.get_runs()
        dead = await db.get_dead_letters()
        index_count = await db.get_index_count()

        print("=" * 60)
        print("현재 진행률")
        print("=" * 60)
        print(f"  파일 인덱스: {index_count:,}개")
        print(f"  완료: {stats.get('completed', 0)}")
        print(f"  실패: {stats.get('failed', 0)}")
        print(f"  처리중: {stats.get('processing', 0)}")
        print(f"  총 청크: {stats.get('total_chunks', 0)}")
        if index_count > 0:
            completed = stats.get('completed', 0)
            progress_pct = completed / index_count * 100
            print(f"  진행률: {progress_pct:.1f}%")

        if runs:
            print(f"\n최근 실행 이력 ({len(runs)}건):")
            for run in runs[:5]:
                started = datetime.fromtimestamp(run["started_at"]).strftime("%Y-%m-%d %H:%M")
                finished = ""
                if run["finished_at"]:
                    finished = datetime.fromtimestamp(run["finished_at"]).strftime("%H:%M")
                    elapsed = run["finished_at"] - run["started_at"]
                    finished = f" → {finished} ({elapsed:.0f}s)"
                print(f"  {run['run_id']}: {started}{finished}")
                print(f"    total={run['total_files']} completed={run['completed_files']} failed={run['failed_files']}")

        if dead:
            print(f"\n영구 실패 파일: {len(dead)}개")
            for d in dead[:10]:
                print(f"  - {Path(d['file_path']).name}: {d['error_msg'][:60]}")
            if len(dead) > 10:
                print(f"  ... 외 {len(dead) - 10}개")

        print("=" * 60)
    finally:
        await db.close()


async def run_ingestion(
    max_files: int | None = None,
    resume: bool = True,
    workers: int = 10,
):
    """전체 문서 적재 실행."""
    print("=" * 60)
    print("전체 문서 적재 시작")
    print("=" * 60)
    print(f"  문서 경로: {settings.DOCUMENTS_ROOT}")
    print(f"  최대 파일: {max_files or '전체'}")
    print(f"  재개 모드: {'ON' if resume else 'OFF (새로 시작)'}")
    print(f"  변환 워커: {workers}개")
    print(f"  임베딩 프로바이더: {settings.EMBEDDING_PROVIDER}")
    if settings.EMBEDDING_PROVIDER == "local":
        print(f"  로컬 모델: {settings.EMBEDDING_LOCAL_MODEL}")
        print(f"  디바이스: {settings.EMBEDDING_LOCAL_DEVICE}")
    else:
        print(f"  임베딩 TPM: {settings.EMBEDDING_TOKENS_PER_MINUTE:,}")
    print(f"  로그 파일: {LOG_FILE}")
    print(f"  progress DB: {settings.PROGRESS_DB_PATH}")
    print("=" * 60)

    # 문서 경로 확인
    doc_root = Path(settings.DOCUMENTS_ROOT)
    if not doc_root.exists():
        logger.error("문서 경로가 존재하지 않습니다: %s", doc_root)
        return False

    # 임베딩 프로바이더별 사전 확인
    if settings.EMBEDDING_PROVIDER == "openai":
        try:
            from openai import OpenAI
            client = OpenAI()
            client.models.list()
            logger.info("OpenAI API 키 확인 완료")
        except Exception as e:
            logger.error("OpenAI API 키 오류: %s", e)
            return False
    else:
        logger.info(
            "로컬 임베딩 모드: %s (%s)",
            settings.EMBEDDING_LOCAL_MODEL,
            settings.EMBEDDING_LOCAL_DEVICE,
        )

    # 파이프라인 실행
    pipeline = ParallelIngestionPipeline(
        converter_concurrency=workers,
        store_batch_size=settings.STORE_BATCH_SIZE,
        embedding_batch_max_tokens=settings.EMBEDDING_BATCH_MAX_TOKENS,
    )

    start = time.time()
    try:
        result = await pipeline.run(
            directory=doc_root,
            max_files=max_files,
            resume=resume,
        )
    except KeyboardInterrupt:
        logger.info("사용자가 중단했습니다. 다시 실행하면 이어서 처리합니다.")
        return False

    elapsed = time.time() - start

    # 결과 출력
    completed = result.get("completed", 0)
    failed = result.get("failed", 0)
    total_chunks = result.get("total_chunks", 0)
    processed = completed + failed

    print("\n" + "=" * 60)
    print("실행 완료")
    print("=" * 60)
    print(f"  처리된 파일: {processed}")
    print(f"  성공: {completed}")
    print(f"  실패: {failed}")
    print(f"  청크 수: {total_chunks:,}")
    print(f"  소요 시간: {elapsed:.1f}s ({elapsed/60:.1f}분)")
    if processed > 0:
        rate = completed / processed * 100
        print(f"  성공률: {rate:.1f}%")
        print(f"  파일당 평균: {elapsed/processed:.2f}s")
    print(f"  로그 파일: {LOG_FILE}")
    print("=" * 60)

    if failed > 0:
        print(f"\n실패한 파일이 {failed}개 있습니다.")
        print("진행률 확인: py scripts/run_full_ingestion.py --status")
        print("재시도: py scripts/run_full_ingestion.py (resume 모드로 자동 재시도)")

    return True


def main():
    parser = argparse.ArgumentParser(description="전체 문서 적재 실행")
    parser.add_argument("--max-files", type=int, default=None, help="최대 처리 파일 수 (기본: 전체)")
    parser.add_argument("--fresh", action="store_true", help="처음부터 새로 실행 (resume 비활성화)")
    parser.add_argument("--workers", type=int, default=10, help="변환 워커 수 (기본: 10)")
    parser.add_argument("--status", action="store_true", help="현재 진행률만 확인")
    args = parser.parse_args()

    if args.status:
        asyncio.run(show_status())
        return

    success = asyncio.run(run_ingestion(
        max_files=args.max_files,
        resume=not args.fresh,
        workers=args.workers,
    ))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
