"""RAG Retriever - 질의에 맞는 문서 청크 검색."""

from app.embedding.embedder import DocumentEmbedder
from app.vectordb.search import VectorSearch, SearchResult


class Retriever:
    """질의 텍스트로부터 관련 문서 청크를 검색."""

    def __init__(self, embedder: DocumentEmbedder, search: VectorSearch):
        self.embedder = embedder
        self.search = search

    async def retrieve(
        self,
        query: str,
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[SearchResult]:
        """질의에 대한 관련 문서 검색."""
        query_embedding = await self.embedder.embed(query)
        return await self.search.search(query_embedding, top_k, filters)
