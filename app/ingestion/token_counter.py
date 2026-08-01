"""tiktoken 기반 토큰 카운팅.

OpenAI 임베딩 API의 토큰 제한에 맞춰 배치를 분할.
"""

import tiktoken

ENCODING = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """단일 텍스트의 토큰 수를 반환."""
    return len(ENCODING.encode(text))


def create_batches(
    texts: list[str],
    max_tokens: int = 8000,
    max_items: int = 2048,
) -> list[list[int]]:
    """토큰 제한에 맞는 배치 인덱스 그룹 생성.

    Args:
        texts: 배치로 분할할 텍스트 리스트
        max_tokens: 배치당 최대 토큰 수
        max_items: 배치당 최대 항목 수

    Returns:
        인덱스 그룹 리스트. 예: [[0,1,2], [3,4], [5]]
    """
    batches: list[list[int]] = []
    current_batch: list[int] = []
    current_tokens = 0

    for idx, text in enumerate(texts):
        token_count = count_tokens(text)

        if current_batch and (
            current_tokens + token_count > max_tokens
            or len(current_batch) >= max_items
        ):
            batches.append(current_batch)
            current_batch = []
            current_tokens = 0

        current_batch.append(idx)
        current_tokens += token_count

    if current_batch:
        batches.append(current_batch)

    return batches
