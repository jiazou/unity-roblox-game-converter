"""
retry.py — Exponential backoff retry utility for transient failures.

Provides a decorator and a callable wrapper for retrying operations that
may fail due to transient issues (network timeouts, API rate limits, etc.).

No other module is imported here.
"""

from __future__ import annotations

import functools
import logging
import time
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


# Exceptions that are considered transient and worth retrying.
_TRANSIENT_EXCEPTIONS: tuple[type[Exception], ...] = (
    ConnectionError,
    TimeoutError,
    OSError,
)

# Try to include urllib errors if available (includes HTTP 429 rate limits)
try:
    import urllib.error
    _TRANSIENT_EXCEPTIONS = _TRANSIENT_EXCEPTIONS + (
        urllib.error.URLError,
        urllib.error.HTTPError,  # covers HTTP 429, 500, 502, 503, etc.
    )
except ImportError:
    pass


def retry_with_backoff(
    max_retries: int = 4,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    retryable_exceptions: tuple[type[Exception], ...] | None = None,
) -> Callable[[F], F]:
    """
    Decorator that retries a function on transient failures with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts (total calls = max_retries + 1).
        base_delay: Initial delay in seconds before the first retry.
        max_delay: Maximum delay cap in seconds.
        backoff_factor: Multiplier applied to delay after each retry.
        retryable_exceptions: Tuple of exception types to retry on.
            Defaults to network/timeout errors.

    Returns:
        Decorated function with retry logic.

    Example:
        @retry_with_backoff(max_retries=3, base_delay=1.0)
        def call_api(payload):
            return requests.post(url, json=payload)
    """
    exceptions = retryable_exceptions or _TRANSIENT_EXCEPTIONS

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            delay = base_delay
            last_exception: Exception | None = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exception = exc
                    if attempt == max_retries:
                        logger.error(
                            "retry: %s failed after %d attempts: %s",
                            func.__name__, max_retries + 1, exc,
                        )
                        raise
                    logger.warning(
                        "retry: %s attempt %d/%d failed (%s), "
                        "retrying in %.1fs …",
                        func.__name__, attempt + 1, max_retries + 1,
                        type(exc).__name__, delay,
                    )
                    time.sleep(delay)
                    delay = min(delay * backoff_factor, max_delay)

            # Unreachable, but satisfies type checker
            raise last_exception  # type: ignore[misc]

        return wrapper  # type: ignore[return-value]

    return decorator


def call_with_retry(
    func: Callable[..., Any],
    *args: Any,
    max_retries: int = 4,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    retryable_exceptions: tuple[type[Exception], ...] | None = None,
    **kwargs: Any,
) -> Any:
    """
    Call a function with exponential backoff retry logic.

    Same semantics as retry_with_backoff but used as a direct wrapper call
    instead of a decorator. Useful when you can't modify the original function.

    Args:
        func: The function to call.
        *args: Positional arguments passed to func.
        max_retries: Maximum number of retry attempts.
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay cap.
        backoff_factor: Multiplier per retry.
        retryable_exceptions: Exception types to retry on.
        **kwargs: Keyword arguments passed to func.

    Returns:
        The return value of func.

    Example:
        result = call_with_retry(
            upload_to_api, payload,
            max_retries=3,
            base_delay=2.0,
        )
    """
    exceptions = retryable_exceptions or _TRANSIENT_EXCEPTIONS
    delay = base_delay
    last_exception: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except exceptions as exc:
            last_exception = exc
            if attempt == max_retries:
                logger.error(
                    "call_with_retry: %s failed after %d attempts: %s",
                    getattr(func, "__name__", str(func)),
                    max_retries + 1, exc,
                )
                raise
            logger.warning(
                "call_with_retry: %s attempt %d/%d failed (%s), "
                "retrying in %.1fs …",
                getattr(func, "__name__", str(func)),
                attempt + 1, max_retries + 1,
                type(exc).__name__, delay,
            )
            time.sleep(delay)
            delay = min(delay * backoff_factor, max_delay)

    raise last_exception  # type: ignore[misc]
