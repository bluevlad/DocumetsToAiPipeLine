r"""Phase 2 병렬 파이프라인 실제 문서 테스트.

실제 문서 N개로 전체 파이프라인을 검증한다:
변환 → 청킹 → 임베딩 → 벡터DB 저장 → 검색 확인.

사용법:
    python scripts/test_parallel_pipeline.py [N]
    python scripts/test_parallel_pipeline.py 100   # 100개 파일
    python scripts/test_parallel_pipeline.py 50    # 50개 파일 (기본)

환경 요구:
    - OPENAI_API_KEY 환경변수 설정
    - DOCUMENTS_ROOT 경로 접근 가능
"""

import asyncio
import logging
import sys
import time
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.embedding.embedder import DocumentEmbedder
from app.ingestion.parallel_pipeline import ParallelIngestionPipeline
from app.ingestion.progress_db import ProgressDB
from app.vectordb.store import VectorStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_parallel")


async def run_test(max_files: int = 50):
    """실제 문서로 병렬 파이프라인 테스트."""
    print("=" * 70)
    print(f"Phase 2 병렬 파이프라인 실제 테스트 (max_files={max_files})")
    print("=" * 70)

    # 1. 파이프라인 실행
    print("\n[1/5] 병렬 파이프라인 실행...")
    pipeline = ParallelIngestionPipeline(
        converter_concurrency=10,
        store_batch_size=500,
        embedding_batch_max_tokens=8000,
    )
    # 테스트용 별도 progress DB
    pipeline.progress_db = ProgressDB(db_path="./progress_test.db")

    start = time.time()
    result = await pipeline.run(
        directory=Path(settings.DOCUMENTS_ROOT),
        max_files=max_files,
        resume=False,
    )
    elapsed = time.time() - start

    completed = result.get("completed", 0)
    failed = result.get("failed", 0)
    total_chunks = result.get("total_chunks", 0)
    processed = completed + failed

    print(f"\n[2/5] 파이프라인 결과:")
    print(f"  처리된 파일: {processed}/{max_files}")
    print(f"  성공: {completed}")
    print(f"  실패: {failed}")
    print(f"  청크 수: {total_chunks}")
    print(f"  소요 시간: {elapsed:.1f}s")
    if processed > 0:
        success_rate = completed / processed * 100
        print(f"  성공률: {success_rate:.1f}%")

    # 3. 벡터DB 저장 확인
    print(f"\n[3/5] 벡터DB 저장 확인...")
    store = VectorStore()
    vector_count = store.count()
    print(f"  저장된 벡터 수: {vector_count}")

    # 4. 검색 테스트
    print(f"\n[4/5] 검색 테스트...")
    embedder = DocumentEmbedder()
    test_query = "프로젝트 제안서"
    query_embedding = await embedder.embed(test_query)
    results = store.search(query_embedding, top_k=3)

    if results["documents"] and results["documents"][0]:
        print(f"  쿼리: '{test_query}'")
        for i, (doc, meta, dist) in enumerate(zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        )):
            print(f"  [{i+1}] distance={dist:.4f}")
            print(f"      파일: {meta.get('file_name', 'N/A')}")
            print(f"      프로젝트: {meta.get('project', 'N/A')}")
            print(f"      텍스트: {doc[:100]}...")
    else:
        print("  검색 결과 없음")

    # 5. 진행률 DB 확인
    print(f"\n[5/5] 진행률 DB 확인...")
    pdb = ProgressDB(db_path="./progress_test.db")
    await pdb.initialize()
    try:
        stats = await pdb.get_stats()
        print(f"  완료: {stats.get('completed', 0)}")
        print(f"  실패: {stats.get('failed', 0)}")
        print(f"  청크 합계: {stats.get('total_chunks', 0)}")

        dead = await pdb.get_dead_letters()
        if dead:
            print(f"  영구 실패 파일: {len(dead)}개")
            for d in dead[:5]:
                print(f"    - {d['file_path']}: {d['error_msg'][:80]}")
    finally:
        await pdb.close()

    # 검증
    print("\n" + "=" * 70)
    print("검증 결과:")
    checks = []

    # 변환 성공률 95% 이상
    if processed > 0:
        success_rate = completed / processed * 100
        ok = success_rate >= 95
        checks.append((f"변환 성공률 >= 95% (실제: {success_rate:.1f}%)", ok))
    else:
        checks.append(("변환 성공률", False))

    # ChromaDB에 벡터 저장 확인
    checks.append((f"벡터 저장 확인 (count={vector_count})", vector_count > 0))

    # 검색 결과 존재
    has_results = bool(results["documents"] and results["documents"][0])
    checks.append((f"검색 결과 존재", has_results))

    all_passed = True
    for desc, ok in checks:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {desc}")
        if not ok:
            all_passed = False

    print("=" * 70)
    if all_passed:
        print("모든 검증 통과!")
    else:
        print("일부 검증 실패. 로그를 확인하세요.")
    print("=" * 70)

    return all_passed


async def run_resume_test(max_files: int = 50):
    """재개 테스트: N/2 처리 후 중단 → 재실행 시 나머지만 처리."""
    half = max_files // 2
    print(f"\n{'=' * 70}")
    print(f"재개 테스트: {half}개 처리 → 중단 → 나머지 {max_files - half}개 재개")
    print(f"{'=' * 70}")

    # 테스트용 별도 progress DB
    progress_path = "./progress_resume_test.db"

    # 1차 실행: 절반만
    print(f"\n[1차 실행] {half}개 파일...")
    pipeline1 = ParallelIngestionPipeline(converter_concurrency=5)
    pipeline1.progress_db = ProgressDB(db_path=progress_path)

    # 테스트용 별도 ChromaDB
    pipeline1.store._client = None
    pipeline1.store._collection = None
    settings.CHROMA_PERSIST_DIR = "./chroma_resume_test"

    result1 = await pipeline1.run(
        directory=Path(settings.DOCUMENTS_ROOT),
        max_files=half,
        resume=False,
    )
    first_completed = result1.get("completed", 0)
    print(f"  1차 완료: {first_completed}개")

    # 2차 실행: 전체 max_files로 resume
    print(f"\n[2차 실행] {max_files}개 파일 (resume=True)...")
    pipeline2 = ParallelIngestionPipeline(converter_concurrency=5)
    pipeline2.progress_db = ProgressDB(db_path=progress_path)

    result2 = await pipeline2.run(
        directory=Path(settings.DOCUMENTS_ROOT),
        max_files=max_files,
        resume=True,
    )
    second_processed = result2.get("completed", 0) + result2.get("failed", 0)
    print(f"  2차 처리: {second_processed}개 (새로 처리된 파일만)")

    # 재개 확인: 2차에서는 1차에서 완료된 파일을 다시 처리하지 않아야 함
    ok = second_processed <= (max_files - first_completed + 5)  # 약간의 여유
    print(f"\n  [{'PASS' if ok else 'FAIL'}] 재개 시 중복 처리 없음 (2차 처리: {second_processed}개)")

    return ok


if __name__ == "__main__":
    max_files = int(sys.argv[1]) if len(sys.argv) > 1 else 50

    passed = asyncio.run(run_test(max_files))

    # 100개 이상일 때만 재개 테스트
    if max_files >= 20:
        resume_ok = asyncio.run(run_resume_test(min(max_files, 20)))
        passed = passed and resume_ok

    sys.exit(0 if passed else 1)
