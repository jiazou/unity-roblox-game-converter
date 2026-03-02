"""Tests for modules/retry.py."""

import time

import pytest

from modules.retry import call_with_retry, retry_with_backoff


class TestRetryWithBackoff:
    """Tests for the retry_with_backoff decorator."""

    def test_succeeds_on_first_try(self) -> None:
        call_count = 0

        @retry_with_backoff(max_retries=3, base_delay=0.01)
        def succeed() -> str:
            nonlocal call_count
            call_count += 1
            return "ok"

        result = succeed()
        assert result == "ok"
        assert call_count == 1

    def test_retries_on_connection_error(self) -> None:
        call_count = 0

        @retry_with_backoff(max_retries=2, base_delay=0.01)
        def fail_then_succeed() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("transient")
            return "ok"

        result = fail_then_succeed()
        assert result == "ok"
        assert call_count == 3

    def test_raises_after_max_retries(self) -> None:
        call_count = 0

        @retry_with_backoff(max_retries=2, base_delay=0.01)
        def always_fail() -> str:
            nonlocal call_count
            call_count += 1
            raise ConnectionError("permanent")

        with pytest.raises(ConnectionError):
            always_fail()
        assert call_count == 3  # 1 initial + 2 retries

    def test_does_not_retry_non_transient_errors(self) -> None:
        call_count = 0

        @retry_with_backoff(max_retries=3, base_delay=0.01)
        def value_error() -> str:
            nonlocal call_count
            call_count += 1
            raise ValueError("not transient")

        with pytest.raises(ValueError):
            value_error()
        assert call_count == 1

    def test_custom_retryable_exceptions(self) -> None:
        call_count = 0

        @retry_with_backoff(
            max_retries=2, base_delay=0.01,
            retryable_exceptions=(ValueError,),
        )
        def fail_with_value_error() -> str:
            nonlocal call_count
            call_count += 1
            raise ValueError("custom retryable")

        with pytest.raises(ValueError):
            fail_with_value_error()
        assert call_count == 3

    def test_exponential_delay(self) -> None:
        """Verify delays are exponentially increasing."""
        call_count = 0
        timestamps: list[float] = []

        @retry_with_backoff(max_retries=2, base_delay=0.05, backoff_factor=2.0)
        def record_timestamps() -> str:
            nonlocal call_count
            timestamps.append(time.monotonic())
            call_count += 1
            if call_count < 3:
                raise ConnectionError("transient")
            return "ok"

        record_timestamps()
        assert len(timestamps) == 3
        delay1 = timestamps[1] - timestamps[0]
        delay2 = timestamps[2] - timestamps[1]
        # Second delay should be roughly 2x the first
        assert delay2 > delay1 * 1.5


class TestCallWithRetry:
    """Tests for the call_with_retry function wrapper."""

    def test_succeeds_on_first_try(self) -> None:
        result = call_with_retry(
            lambda: "ok",
            max_retries=3, base_delay=0.01,
        )
        assert result == "ok"

    def test_retries_on_failure(self) -> None:
        call_count = 0

        def fail_then_succeed() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("transient")
            return "ok"

        result = call_with_retry(
            fail_then_succeed,
            max_retries=3, base_delay=0.01,
        )
        assert result == "ok"
        assert call_count == 2

    def test_passes_args_and_kwargs(self) -> None:
        def add(a: int, b: int) -> int:
            return a + b

        result = call_with_retry(
            add, 3, b=7,
            max_retries=1, base_delay=0.01,
        )
        assert result == 10

    def test_raises_after_exhausted_retries(self) -> None:
        def always_fail() -> str:
            raise TimeoutError("timeout")

        with pytest.raises(TimeoutError):
            call_with_retry(
                always_fail,
                max_retries=1, base_delay=0.01,
            )
