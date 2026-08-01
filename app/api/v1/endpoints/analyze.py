"""문서 분석 / RAG 질의 API 엔드포인트."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.embedding.embedder import DocumentEmbedder
from app.rag.prompts import SYSTEM_PROMPT, build_rag_prompt
from app.vectordb.search import VectorSearch
from app.vectordb.store import VectorStore

router = APIRouter()

store = VectorStore()
embedder = DocumentEmbedder()
searcher = VectorSearch(store)


class AnalyzeRequest(BaseModel):
    query: str
    top_k: int = 10
    project_filter: str | None = None


@router.post("/")
async def analyze_documents(request: AnalyzeRequest):
    """RAG 기반 문서 분석 및 응답 생성."""
    import anthropic
    from app.core.config import settings

    # 1. 검색
    query_embedding = await embedder.embed(request.query)
    results = searcher.search(
        query_embedding=query_embedding,
        top_k=request.top_k,
        project_filter=request.project_filter,
    )

    if not results:
        return {"query": request.query, "answer": "관련 문서를 찾을 수 없습니다.", "sources": []}

    # 2. RAG 프롬프트 생성
    user_prompt = build_rag_prompt(request.query, results)

    # 3. Claude 응답 생성
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=settings.LLM_MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    return {
        "query": request.query,
        "answer": response.content[0].text,
        "sources": [
            {
                "project": r.metadata.get("project", ""),
                "file_name": r.metadata.get("file_name", ""),
                "score": round(r.score, 4),
            }
            for r in results
        ],
    }
