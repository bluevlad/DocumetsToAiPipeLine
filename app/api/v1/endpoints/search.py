"""문서 검색 API 엔드포인트."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.embedding.embedder import DocumentEmbedder
from app.vectordb.search import VectorSearch
from app.vectordb.store import VectorStore

router = APIRouter()

store = VectorStore()
embedder = DocumentEmbedder()
searcher = VectorSearch(store)


class SearchRequest(BaseModel):
    query: str
    top_k: int = 10
    project_filter: str | None = None
    file_type_filter: str | None = None


@router.post("/")
async def search_documents(request: SearchRequest):
    """벡터 유사도 기반 문서 검색."""
    query_embedding = await embedder.embed(request.query)

    results = searcher.search(
        query_embedding=query_embedding,
        top_k=request.top_k,
        project_filter=request.project_filter,
        file_type_filter=request.file_type_filter,
    )

    return {
        "query": request.query,
        "results": [
            {
                "chunk_id": r.chunk_id,
                "text": r.text[:500],
                "score": round(r.score, 4),
                "project": r.metadata.get("project", ""),
                "file_name": r.metadata.get("file_name", ""),
                "file_type": r.metadata.get("file_type", ""),
            }
            for r in results
        ],
        "total": len(results),
    }
