"""임베딩 관련 데이터 모델."""

from dataclasses import dataclass


@dataclass
class EmbeddedChunk:
    """임베딩이 완료된 청크."""
    chunk_id: str
    text: str
    embedding: list[float]
    metadata: dict
