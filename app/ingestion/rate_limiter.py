"""비동기 토큰 버킷 레이트 리미터.

OpenAI API의 요청/분 + 토큰/분 이중 제한을 준수.
"""

import asyncio
import logging
import time

from app.core.config import settings

logger = logging.getLogger(__name__)


class RateLimiter:
    """요청/분 + 토큰/분 이중 레이트 리미터."""

    def __init__(
        self,
        requests_per_minute: int = settings.EMBEDDING_REQUESTS_PER_MINUTE,
        tokens_per_minute: int = settings.EMBEDDING_TOKENS_PER_MINUTE,
    ):
        self.rpm = requests_per_minute
        self.tpm = tokens_per_minute

        # 버킷 (1초 단위 리필)
        self._request_budget = requests_per_minute / 60.0
        self._token_budget = tokens_per_minute / 60.0
        self._request_refill = requests_per_minute / 60.0
        self._token_refill = tokens_per_minute / 60.0

        self._lock = asyncio.Lock()
        self._last_refill = time.monotonic()
        self._running = False
        self._refill_task: asyncio.Task | None = None

    async def start(self):
        """백그라운드 리필 루프 시작."""
        if self._running:
            return
        self._running = True
        self._last_refill = time.monotonic()
        self._refill_task = asyncio.create_task(self._refill_loop())

    async def stop(self):
        """리필 루프 중지."""
        self._running = False
        if self._refill_task:
            self._refill_task.cancel()
            try:
                await self._refill_task
            except asyncio.CancelledError:
                pass
            self._refill_task = None

    async def _refill_loop(self):
        """1초마다 버킷 리필."""
        while self._running:
            await asyncio.sleep(1.0)
            async with self._lock:
                self._request_budget = min(
                    self._request_budget + self._request_refill,
                    self.rpm / 60.0 * 10,  # 최대 10초치 버스트 허용
                )
                self._token_budget = min(
                    self._token_budget + self._token_refill,
                    self.tpm / 60.0 * 10,
                )

    async def acquire(self, token_count: int = 0):
        """예산 소진 시 대기. 1 요청 + token_count 토큰을 소비."""
        while True:
            async with self._lock:
                if self._request_budget >= 1.0 and self._token_budget >= token_count:
                    self._request_budget -= 1.0
                    self._token_budget -= token_count
                    return

            # 예산 부족 시 100ms 대기 후 재시도
            await asyncio.sleep(0.1)
