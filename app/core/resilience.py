"""
Resilience & Retry Utilities — Resilient HTTP retries with exponential backoff.

Provides:
- Error classification (transient network timeout vs HTTP 429 rate limit vs HTTP 5xx vs non-retryable 4xx).
- Jittered exponential backoff for async network operations.
- Async retry helper and decorator.
"""

import asyncio
import logging
import random
from typing import Any, Callable, Coroutine, TypeVar

import httpx

logger = logging.getLogger(__name__)

T = TypeVar("T")

# HTTP status codes that represent transient, retryable failures
RETRYABLE_STATUS_CODES: set[int] = {
    429,  # Too Many Requests (Rate limit)
    500,  # Internal Server Error
    502,  # Bad Gateway
    503,  # Service Unavailable
    504,  # Gateway Timeout
}


def classify_http_error(exc: Exception) -> str:
    """Classify an HTTP or network exception into a human-readable diagnostic message."""
    if isinstance(exc, httpx.TimeoutException):
        return f"Network timeout ({exc.__class__.__name__})"
    if isinstance(exc, httpx.NetworkError):
        return f"Network transport error ({exc.__class__.__name__}: {exc})"
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 429:
            return f"Rate limit exceeded (HTTP 429) from {exc.request.url}"
        if 500 <= status <= 599:
            return f"Server error (HTTP {status}) from {exc.request.url}"
        if 400 <= status <= 499:
            return f"Client error (HTTP {status}) from {exc.request.url} (non-retryable)"
    return f"{exc.__class__.__name__}: {exc}"


def is_retryable_http_error(exc: Exception) -> bool:
    """Determine whether an exception represents a transient failure worth retrying."""
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_STATUS_CODES
    return False


async def retry_async(
    coro_fn: Callable[..., Coroutine[Any, Any, T]],
    *args: Any,
    max_retries: int = 3,
    base_delay: float = 0.3,
    max_delay: float = 3.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    is_retryable: Callable[[Exception], bool] = is_retryable_http_error,
    operation_name: str = "network_request",
    **kwargs: Any,
) -> T:
    """Execute an async operation with jittered exponential backoff.

    Args:
        coro_fn: Async callable to execute.
        *args: Positional arguments for coro_fn.
        max_retries: Maximum number of retry attempts after the first failure.
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay cap in seconds.
        backoff_factor: Multiplier for exponential backoff.
        jitter: Whether to add random uniform jitter (0% to 25% of delay).
        is_retryable: Predicate function evaluating if an exception is retryable.
        operation_name: Descriptive name for logging.
        **kwargs: Keyword arguments for coro_fn.

    Returns:
        The return value of coro_fn.

    Raises:
        Exception: The last caught exception if retries are exhausted or non-retryable.
    """
    total_attempts = max_retries + 1
    last_exc: Exception | None = None

    for attempt in range(1, total_attempts + 1):
        try:
            return await coro_fn(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            is_last_attempt = (attempt == total_attempts)

            if is_last_attempt or not is_retryable(exc):
                logger.debug(
                    "Operation '%s' failed on attempt %d/%d (%s). Not retrying.",
                    operation_name,
                    attempt,
                    total_attempts,
                    classify_http_error(exc),
                )
                raise

            # Calculate jittered exponential backoff delay
            raw_delay = min(max_delay, base_delay * (backoff_factor ** (attempt - 1)))
            jitter_amount = random.uniform(0.0, 0.25 * raw_delay) if jitter else 0.0
            delay = raw_delay + jitter_amount

            logger.warning(
                "Operation '%s' attempt %d/%d failed: %s. Retrying in %.2fs...",
                operation_name,
                attempt,
                total_attempts,
                classify_http_error(exc),
                delay,
            )
            await asyncio.sleep(delay)

    # Should not reach here, but satisfy type checker
    if last_exc:
        raise last_exc
    raise RuntimeError(f"Operation '{operation_name}' failed with unknown state.")
