"""RAG 프롬프트 템플릿."""

from app.vectordb.search import SearchResult

SYSTEM_PROMPT = """당신은 26년간(1999-2025) 축적된 IT 프로젝트 문서를 분석하는 전문가입니다.
사용자의 질문에 대해 검색된 문서 컨텍스트를 기반으로 답변합니다.

답변 시 다음 원칙을 따릅니다:
1. 검색된 문서에 근거한 사실만 제시
2. 프로젝트명, 연도, 기술 스택을 명시
3. MSP 서비스 전환 가능성을 냉정하게 평가
4. 기술적 난이도와 시장성을 구분하여 분석
"""

RAG_USER_TEMPLATE = """## 검색된 문서 컨텍스트

{context}

---

## 질문

{query}
"""


def build_rag_prompt(query: str, results: list[SearchResult]) -> str:
    """검색 결과를 프롬프트 컨텍스트로 포맷팅."""
    context_parts = []
    for i, r in enumerate(results, 1):
        source = r.metadata.get("project", "unknown")
        file_name = r.metadata.get("file_name", "unknown")
        context_parts.append(
            f"### [{i}] {source} / {file_name}\n{r.text}"
        )

    context = "\n\n".join(context_parts)
    return RAG_USER_TEMPLATE.format(context=context, query=query)
