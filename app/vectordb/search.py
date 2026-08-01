"""벡터 검색 모듈."""

from dataclasses import dataclass

from app.vectordb.store import VectorStore


@dataclass
class SearchResult:
    """검색 결과."""
    chunk_id: str
    text: str
    score: float
    metadata: dict


class VectorSearch:
    """벡터 유사도 검색."""

    def __init__(self, store: VectorStore):
        self.store = store

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        project_filter: str | None = None,
        file_type_filter: str | None = None,
    ) -> list[SearchResult]:
        """유사도 기반 검색."""
        where = {}
        if project_filter:
            where["project"] = project_filter
        if file_type_filter:
            where["file_type"] = file_type_filter

        results = self.store.search(
            query_embedding=query_embedding,
            top_k=top_k,
            where=where if where else None,
        )

        search_results = []
        if results and results["ids"] and results["ids"][0]:
            for i, chunk_id in enumerate(results["ids"][0]):
                search_results.append(SearchResult(
                    chunk_id=chunk_id,
                    text=results["documents"][0][i] if results["documents"] else "",
                    score=1 - results["distances"][0][i] if results["distances"] else 0,
                    metadata=results["metadatas"][0][i] if results["metadatas"] else {},
                ))

        return search_results
