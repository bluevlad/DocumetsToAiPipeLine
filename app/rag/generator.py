"""RAG Generator - 검색된 컨텍스트 기반 응답 생성."""

from app.core.config import settings
from app.rag.prompts import build_rag_prompt
from app.vectordb.search import SearchResult


class Generator:
    """검색된 문서 컨텍스트를 기반으로 LLM 응답 생성."""

    def __init__(self, model: str = settings.LLM_MODEL):
        self.model = model

    async def generate(
        self,
        query: str,
        context: list[SearchResult],
    ) -> str:
        """질의 + 검색 컨텍스트로 응답 생성."""
        prompt = build_rag_prompt(query, context)
        # TODO: Anthropic Claude API 호출
        raise NotImplementedError
