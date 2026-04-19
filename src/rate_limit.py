"""Async token bucket for proactive rate limiting.

Used to pace requests below an OpenAI org/model tier's RPM and TPM ceilings so
we don't rely on 429-and-retry as the control loop.
"""
from __future__ import annotations

import asyncio
import time


class AsyncTokenBucket:
    """Classic token bucket. Refills at `rate_per_minute / 60` tokens per second.

    Capacity defaults to one minute's worth of budget (allows burst up to the
    per-minute limit, then paces).
    """

    def __init__(self, rate_per_minute: float, capacity: float | None = None) -> None:
        if rate_per_minute <= 0:
            raise ValueError("rate_per_minute must be > 0")
        self._rate_per_sec = rate_per_minute / 60.0
        self._capacity = float(capacity if capacity is not None else rate_per_minute)
        self._tokens = self._capacity
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, amount: float = 1.0) -> None:
        """Block until `amount` tokens are available, then consume them."""
        if amount <= 0:
            return
        if amount > self._capacity:
            # Caller wants more than the whole minute's budget. Let it through
            # after draining the bucket; the caller effectively waits ~amount/rate
            # seconds. Better than failing.
            amount = self._capacity

        while True:
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self._updated
                self._tokens = min(
                    self._capacity, self._tokens + elapsed * self._rate_per_sec
                )
                self._updated = now
                if self._tokens >= amount:
                    self._tokens -= amount
                    return
                needed = amount - self._tokens
                wait = needed / self._rate_per_sec
            await asyncio.sleep(wait)


class RateLimiter:
    """Bundles an optional RPM bucket and an optional TPM bucket."""

    def __init__(
        self,
        *,
        requests_per_minute: int | None = None,
        tokens_per_minute: int | None = None,
    ) -> None:
        self._rpm = (
            AsyncTokenBucket(requests_per_minute) if requests_per_minute else None
        )
        self._tpm = (
            AsyncTokenBucket(tokens_per_minute) if tokens_per_minute else None
        )

    @property
    def enabled(self) -> bool:
        return self._rpm is not None or self._tpm is not None

    async def acquire(self, estimated_tokens: int) -> None:
        if self._rpm is not None:
            await self._rpm.acquire(1)
        if self._tpm is not None:
            await self._tpm.acquire(estimated_tokens)
