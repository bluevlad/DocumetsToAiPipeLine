"""텍스트 청킹 모듈.

변환된 문서 텍스트를 의미 단위로 분할.
"""

import hashlib
from dataclasses import dataclass, field

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings


@dataclass
class Chunk:
    """문서 청크."""
    chunk_id: str = ""
    text: str = ""
    metadata: dict = field(default_factory=dict)
    chunk_index: int = 0


class DocumentChunker:
    """문서 텍스트를 벡터DB 적재용 청크로 분할."""

    def __init__(
        self,
        chunk_size: int = settings.CHUNK_SIZE,
        chunk_overlap: int = settings.CHUNK_OVERLAP,
    ):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
            length_function=len,
        )

    def chunk(self, text: str, metadata: dict | None = None) -> list[Chunk]:
        """텍스트를 청크로 분할."""
        if not text or not text.strip():
            return []

        meta = metadata or {}
        splits = self.splitter.split_text(text)
        chunks = []

        for idx, split_text in enumerate(splits):
            source = meta.get("source_path", "unknown")
            chunk_id = hashlib.md5(
                f"{source}:{idx}:{split_text[:50]}".encode()
            ).hexdigest()

            chunks.append(Chunk(
                chunk_id=chunk_id,
                text=split_text,
                metadata={**meta, "chunk_index": idx, "total_chunks": len(splits)},
                chunk_index=idx,
            ))

        return chunks
