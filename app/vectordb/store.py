"""벡터DB 저장소.

개발: ChromaDB → 운영: PostgreSQL + pgvector.
"""

import asyncio
import logging

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.config import settings

logger = logging.getLogger(__name__)


def _sanitize_str(text: str) -> str:
    """서로게이트 및 null 바이트 제거."""
    return text.encode("utf-8", errors="replace").decode("utf-8").replace("\x00", "")


class VectorStore:
    """ChromaDB 기반 벡터 저장소."""

    COLLECTION_NAME = settings.CHROMA_COLLECTION_NAME

    def __init__(self):
        self._client: chromadb.ClientAPI | None = None
        self._collection = None
        self._write_lock = asyncio.Lock()

    @property
    def client(self) -> chromadb.ClientAPI:
        if self._client is None:
            self._client = chromadb.PersistentClient(
                path=settings.CHROMA_PERSIST_DIR,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        return self._client

    @property
    def collection(self):
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def upsert(self, chunk_id: str, embedding: list[float], metadata: dict, text: str):
        """단일 벡터 + 메타데이터 저장."""
        safe_meta = {k: _sanitize_str(str(v)) if isinstance(v, str) else
                     (str(v) if not isinstance(v, (int, float, bool)) else v)
                     for k, v in metadata.items()}

        self.collection.upsert(
            ids=[chunk_id],
            embeddings=[embedding],
            metadatas=[safe_meta],
            documents=[_sanitize_str(text)],
        )

    def upsert_batch(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict],
        documents: list[str],
    ):
        """벡터 배치 저장."""
        safe_metas = []
        for meta in metadatas:
            safe_meta = {k: _sanitize_str(str(v)) if isinstance(v, str) else
                         (str(v) if not isinstance(v, (int, float, bool)) else v)
                         for k, v in meta.items()}
            safe_metas.append(safe_meta)

        safe_docs = [_sanitize_str(d) for d in documents]

        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            metadatas=safe_metas,
            documents=safe_docs,
        )

    async def upsert_batch_async(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict],
        documents: list[str],
        batch_size: int = settings.STORE_BATCH_SIZE,
    ):
        """비동기 배치 저장. Lock으로 ChromaDB 동시 쓰기 보호."""
        safe_metas = []
        for meta in metadatas:
            safe_meta = {k: _sanitize_str(str(v)) if isinstance(v, str) else
                         (str(v) if not isinstance(v, (int, float, bool)) else v)
                         for k, v in meta.items()}
            safe_metas.append(safe_meta)

        safe_docs = [_sanitize_str(d) for d in documents]

        for i in range(0, len(ids), batch_size):
            batch_ids = ids[i : i + batch_size]
            batch_embeddings = embeddings[i : i + batch_size]
            batch_metas = safe_metas[i : i + batch_size]
            batch_docs = safe_docs[i : i + batch_size]

            async with self._write_lock:
                await asyncio.to_thread(
                    self.collection.upsert,
                    ids=batch_ids,
                    embeddings=batch_embeddings,
                    metadatas=batch_metas,
                    documents=batch_docs,
                )

    def count(self) -> int:
        """저장된 벡터 수."""
        return self.collection.count()

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        where: dict | None = None,
    ) -> dict:
        """벡터 유사도 검색."""
        kwargs = {
            "query_embeddings": [query_embedding],
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        return self.collection.query(**kwargs)
