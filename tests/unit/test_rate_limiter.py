"""rate_limiter 단위 테스트."""

import asyncio
import time

import pytest

from app.ingestion.rate_limiter import RateLimiter


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_acquire_within_budget(self):
        limiter = RateLimiter(requests_per_minute=600, tokens_per_minute=60000)
        await limiter.start()
        try:
            # 초기 예산으로 즉시 acquire 가능
            start = time.monotonic()
            await limiter.acquire(100)
            elapsed = time.monotonic() - start
            assert elapsed < 0.5
        finally:
            await limiter.stop()

    @pytest.mark.asyncio
    async def test_multiple_acquires(self):
        limiter = RateLimiter(requests_per_minute=600, tokens_per_minute=60000)
        await limiter.start()
        try:
            for _ in range(5):
                await limiter.acquire(10)
        finally:
            await limiter.stop()

    @pytest.mark.asyncio
    async def test_start_stop(self):
        limiter = RateLimiter(requests_per_minute=60, tokens_per_minute=6000)
        await limiter.start()
        assert limiter._running is True
        await limiter.stop()
        assert limiter._running is False

    @pytest.mark.asyncio
    async def test_budget_refills(self):
        # 매우 작은 예산으로 리필 확인
        limiter = RateLimiter(requests_per_minute=60, tokens_per_minute=6000)
        await limiter.start()
        try:
            # 초기 예산 소진
            await limiter.acquire(100)
            # 1초 후 리필 확인
            await asyncio.sleep(1.2)
            start = time.monotonic()
            await limiter.acquire(50)
            elapsed = time.monotonic() - start
            assert elapsed < 0.5
        finally:
            await limiter.stop()
