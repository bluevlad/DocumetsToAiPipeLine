"""RAG 검색 테스트 스크립트.

벡터 검색 + Claude RAG 응답 생성을 테스트.
"""
import asyncio
import io
import json
import sys
import time
from pathlib import Path

# Windows cp949 출력 에러 방지
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.embedding.embedder import DocumentEmbedder
from app.vectordb.search import VectorSearch
from app.vectordb.store import VectorStore


async def test_vector_search(query: str, top_k: int = 5):
    """벡터 유사도 검색 테스트."""
    print("=" * 70)
    print(f"[벡터 검색] {query}")
    print("=" * 70)

    embedder = DocumentEmbedder()
    store = VectorStore()
    searcher = VectorSearch(store)

    print(f"  ChromaDB 벡터 수: {store.count():,}")
    print(f"  임베딩 모델: {embedder.model}")
    print()

    start = time.time()
    query_embedding = await embedder.embed(query)
    embed_time = time.time() - start

    start = time.time()
    results = searcher.search(
        query_embedding=query_embedding,
        top_k=top_k,
    )
    search_time = time.time() - start

    print(f"  임베딩 시간: {embed_time:.3f}s")
    print(f"  검색 시간: {search_time:.3f}s")
    print(f"  결과 수: {len(results)}")
    print()

    for i, r in enumerate(results, 1):
        project = r.metadata.get("project", "unknown")
        file_name = r.metadata.get("file_name", "unknown")
        year = r.metadata.get("year", "?")
        category = r.metadata.get("category", "?")
        score = r.score

        print(f"  [{i}] score={score:.4f} | {project} / {file_name}")
        print(f"      year={year} category={category}")
        text_preview = r.text[:200].replace("\n", " ")
        print(f"      {text_preview}...")
        print()

    return results


async def test_rag_analyze(query: str, top_k: int = 10):
    """RAG 분석 (Claude 응답 생성) 테스트."""
    import anthropic
    from app.rag.prompts import SYSTEM_PROMPT, build_rag_prompt

    print("=" * 70)
    print(f"[RAG 분석] {query}")
    print("=" * 70)

    embedder = DocumentEmbedder()
    store = VectorStore()
    searcher = VectorSearch(store)

    # 1. 검색
    start = time.time()
    query_embedding = await embedder.embed(query)
    results = searcher.search(query_embedding=query_embedding, top_k=top_k)
    search_time = time.time() - start
    print(f"  검색: {len(results)}개 문서, {search_time:.3f}s")

    if not results:
        print("  관련 문서를 찾을 수 없습니다.")
        return

    # 소스 목록
    print("  소스:")
    for i, r in enumerate(results[:5], 1):
        project = r.metadata.get("project", "unknown")
        file_name = r.metadata.get("file_name", "unknown")
        print(f"    [{i}] {project} / {file_name} (score={r.score:.4f})")
    if len(results) > 5:
        print(f"    ... 외 {len(results) - 5}개")
    print()

    # 2. RAG 프롬프트
    user_prompt = build_rag_prompt(query, results)

    # 3. Claude 응답
    print("  Claude 응답 생성 중...")
    start = time.time()
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=settings.LLM_MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    gen_time = time.time() - start

    answer = response.content[0].text
    print(f"  생성 시간: {gen_time:.1f}s")
    print(f"  토큰: input={response.usage.input_tokens}, output={response.usage.output_tokens}")
    print()
    print("-" * 70)
    print(answer)
    print("-" * 70)


async def main():
    # 테스트 쿼리 목록
    test_queries = [
        "산업보건 관련 프로젝트에서 어떤 기술 스택을 사용했나?",
        "CBT 시험 시스템 설계 문서",
        "웹 애플리케이션 보안 취약점 점검",
    ]

    # 1. 벡터 검색 테스트 (3개 쿼리)
    for q in test_queries:
        await test_vector_search(q, top_k=5)
        print()

    # 2. RAG 분석 테스트 (1개 쿼리)
    print("\n" + "=" * 70)
    print("RAG 분석 테스트 (Claude API 사용)")
    print("=" * 70 + "\n")
    await test_rag_analyze(
        "26년간 프로젝트 경험 중 SaaS 서비스로 전환할 수 있는 아이디어를 분석해줘",
        top_k=10,
    )


if __name__ == "__main__":
    asyncio.run(main())
