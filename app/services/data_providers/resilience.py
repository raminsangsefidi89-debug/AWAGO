"""Resilience utilities: TTL cache, circuit breaker, backoff with jitter."""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.logging_config import get_logger

logger = get_logger(__name__)


class CircuitOpenError(RuntimeError):
    """Raised when a call is attempted while the circuit breaker is open."""


@dataclass
class CircuitBreaker:
    """Simple circuit breaker: closed -> open -> half_open -> closed.

    Opens after ``failure_threshold`` consecutive failures, stays open for
    ``reset_seconds``, then admits a single probe (half-open). A successful
    probe closes the circuit.
    """

    failure_threshold: int = 3
    reset_seconds: float = 60.0
    failures: int = 0
    opened_at: float | None = None
    state: str = "closed"
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def allow(self) -> bool:
        with self._lock:
            if self.state == "closed":
                return True
            if self.state == "open":
                if (
                    self.opened_at is not None
                    and time.monotonic() - self.opened_at >= self.reset_seconds
                ):
                    self.state = "half_open"
                    return True
                return False
            return True  # half_open: allow one probe

    def record_success(self) -> None:
        with self._lock:
            self.failures = 0
            self.state = "closed"
            self.opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self.failures += 1
            if self.failures >= self.failure_threshold or self.state == "half_open":
                self.state = "open"
                self.opened_at = time.monotonic()
                logger.warning("Circuit breaker OPENED after %d failures", self.failures)


class TTLCache:
    """Thread-safe TTL cache."""

    def __init__(self, ttl_seconds: float = 900.0, max_entries: int = 256) -> None:
        self.ttl = ttl_seconds
        self.max_entries = max_entries
        self._store: dict[Any, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: Any) -> Any | None:
        with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            expires_at, value = item
            if time.monotonic() > expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: Any, value: Any) -> None:
        with self._lock:
            if len(self._store) >= self.max_entries:
                # drop the oldest entry
                oldest = min(self._store, key=lambda k: self._store[k][0], default=None)
                if oldest is not None:
                    del self._store[oldest]
            self._store[key] = (time.monotonic() + self.ttl, value)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


def backoff_delay(attempt: int, base: float = 1.0, cap: float = 30.0, jitter: bool = True) -> float:
    """Exponential backoff with optional full jitter."""
    delay = min(cap, base * (2**attempt))
    return random.uniform(0, delay) if jitter else delay


def with_backoff(
    fn: Callable[[], Any],
    *,
    retries: int = 3,
    base: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
) -> Any:
    """Call ``fn`` with exponential backoff + jitter on failure."""
    last_exc: BaseException | None = None
    for attempt in range(max(1, retries)):
        try:
            return fn()
        except retry_on as exc:
            last_exc = exc
            if attempt < retries - 1:
                delay = backoff_delay(attempt, base=base)
                logger.warning("Attempt %d failed (%s); retrying in %.1fs", attempt + 1, exc, delay)
                sleep(delay)
    assert last_exc is not None
    raise last_exc
