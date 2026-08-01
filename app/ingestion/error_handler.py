"""에러 분류 + 재시도 핸들러.

transient 에러는 지수 백오프로 재시도, permanent 에러는 즉시 실패 처리.
"""

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from enum import Enum

from app.core.config import settings

logger = logging.getLogger(__name__)


class ErrorType(Enum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"


# transient 에러로 분류할 예외 이름 패턴
_TRANSIENT_NAMES = {
    "RateLimitError",
    "APITimeoutError",
    "APIConnectionError",
    "ConnectionError",
    "TimeoutError",
    "InternalServerError",
    "ServiceUnavailableError",
}

# permanent 에러로 분류할 예외 타입
_PERMANENT_TYPES = (
    FileNotFoundError,
    PermissionError,
    IsADirectoryError,
    UnicodeDecodeError,
    ValueError,
)


class ErrorClassifier:
    """에러를 transient / permanent으로 분류."""

    @staticmethod
    def classify(error: Exception) -> ErrorType:
        if isinstance(error, _PERMANENT_TYPES):
            return ErrorType.PERMANENT

        error_name = type(error).__name__
        if error_name in _TRANSIENT_NAMES:
            return ErrorType.TRANSIENT

        # zlib.error 등 데이터 손상
        error_module = type(error).__module__ or ""
        if "zlib" in error_module or "zlib" in error_name.lower() or "decompres" in str(error).lower():
            return ErrorType.PERMANENT

        # 알 수 없는 에러는 transient으로 분류 (재시도 허용)
        return ErrorType.TRANSIENT


class RetryHandler:
    """지수 백오프 기반 비동기 재시도."""

    def __init__(
        self,
        max_retries: int = settings.MAX_RETRIES,
        base_delay: float = settings.RETRY_BASE_DELAY,
        max_delay: float = settings.RETRY_MAX_DELAY,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

    async def execute_with_retry(
        self,
        coro_factory: Callable[[], Awaitable],
        description: str = "",
    ):
        """코루틴 팩토리를 재시도와 함께 실행.

        Args:
            coro_factory: 매 시도마다 새 코루틴을 생성하는 팩토리 함수
            description: 로그용 설명

        Raises:
            마지막 시도에서 발생한 예외
        """
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                return await coro_factory()
            except Exception as e:
                last_error = e
                error_type = ErrorClassifier.classify(e)

                if error_type == ErrorType.PERMANENT:
                    logger.warning(
                        "Permanent error for %s: %s", description, e
                    )
                    raise

                if attempt >= self.max_retries:
                    logger.error(
                        "Max retries (%d) reached for %s: %s",
                        self.max_retries, description, e,
                    )
                    raise

                delay = min(
                    self.base_delay * (2 ** attempt) + random.uniform(0, 1),
                    self.max_delay,
                )
                logger.info(
                    "Retry %d/%d for %s after %.1fs: %s",
                    attempt + 1, self.max_retries, description, delay, e,
                )
                await asyncio.sleep(delay)

        raise last_error  # type: ignore[misc]
