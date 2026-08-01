"""error_handler 단위 테스트."""

import pytest

from app.ingestion.error_handler import (
    ErrorClassifier,
    ErrorType,
    RetryHandler,
)


class TestErrorClassifier:
    def test_file_not_found_is_permanent(self):
        assert ErrorClassifier.classify(FileNotFoundError()) == ErrorType.PERMANENT

    def test_permission_error_is_permanent(self):
        assert ErrorClassifier.classify(PermissionError()) == ErrorType.PERMANENT

    def test_value_error_is_permanent(self):
        assert ErrorClassifier.classify(ValueError()) == ErrorType.PERMANENT

    def test_unicode_error_is_permanent(self):
        err = UnicodeDecodeError("utf-8", b"", 0, 1, "test")
        assert ErrorClassifier.classify(err) == ErrorType.PERMANENT

    def test_connection_error_is_transient(self):
        assert ErrorClassifier.classify(ConnectionError()) == ErrorType.TRANSIENT

    def test_timeout_error_is_transient(self):
        assert ErrorClassifier.classify(TimeoutError()) == ErrorType.TRANSIENT

    def test_zlib_error_is_permanent(self):
        import zlib
        assert ErrorClassifier.classify(zlib.error("test")) == ErrorType.PERMANENT

    def test_unknown_error_is_transient(self):
        assert ErrorClassifier.classify(RuntimeError("unknown")) == ErrorType.TRANSIENT


class TestRetryHandler:
    @pytest.mark.asyncio
    async def test_success_no_retry(self):
        handler = RetryHandler(max_retries=3, base_delay=0.01)
        call_count = 0

        async def success():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await handler.execute_with_retry(success, "test")
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_transient_error_retries(self):
        handler = RetryHandler(max_retries=2, base_delay=0.01, max_delay=0.05)
        call_count = 0

        async def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("transient")
            return "ok"

        result = await handler.execute_with_retry(fail_then_succeed, "test")
        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_permanent_error_no_retry(self):
        handler = RetryHandler(max_retries=3, base_delay=0.01)
        call_count = 0

        async def permanent_fail():
            nonlocal call_count
            call_count += 1
            raise FileNotFoundError("gone")

        with pytest.raises(FileNotFoundError):
            await handler.execute_with_retry(permanent_fail, "test")
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self):
        handler = RetryHandler(max_retries=2, base_delay=0.01, max_delay=0.05)
        call_count = 0

        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("always fails")

        with pytest.raises(ConnectionError):
            await handler.execute_with_retry(always_fail, "test")
        assert call_count == 3  # initial + 2 retries
