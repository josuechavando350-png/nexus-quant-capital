"""Capa 0 · RateLimiter — token-bucket por host.

Tumbar un servidor convierte un bounty en delito. Este limitador obedece
el `rps` que declare el programa (global o por host) y bloquea hasta tener
permiso, para que ninguna capa futura pueda pisar el acelerador.

El reloj y la función de dormir son inyectables (`clock`, `sleeper`) para
que los tests sean deterministas y rápidos; por defecto usan tiempo real.
"""

from __future__ import annotations

import threading
import time
from typing import Callable


class _Bucket:
    __slots__ = ("rate", "capacity", "tokens", "updated", "clock", "lock")

    def __init__(self, rate: float, capacity: float, clock: Callable[[], float]) -> None:
        self.rate = float(rate)
        self.capacity = float(capacity)
        self.tokens = float(capacity)
        self.clock = clock
        self.updated = clock()
        self.lock = threading.Lock()

    def refill(self) -> None:
        now = self.clock()
        elapsed = now - self.updated
        if elapsed > 0:
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.updated = now


class RateLimiter:
    """Token-bucket por host. `acquire(host)` bloquea hasta tener un token."""

    def __init__(
        self,
        default_rps: float,
        per_host: dict[str, float] | None = None,
        *,
        capacity: float | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if default_rps <= 0:
            raise ValueError("default_rps must be > 0")
        self.default_rps = float(default_rps)
        self.per_host = {str(k): float(v) for k, v in (per_host or {}).items()}
        self.capacity = None if capacity is None else float(capacity)
        self._clock = clock
        self._sleeper = sleeper
        self._buckets: dict[str, _Bucket] = {}
        self._guard = threading.Lock()

    def _rate_for(self, host: str) -> float:
        return self.per_host.get(host, self.default_rps)

    def _capacity_for(self, rate: float) -> float:
        return self.capacity if self.capacity is not None else max(1.0, rate)

    def _bucket(self, host: str) -> _Bucket:
        with self._guard:
            bucket = self._buckets.get(host)
            if bucket is None:
                rate = self._rate_for(host)
                bucket = _Bucket(rate, self._capacity_for(rate), self._clock)
                self._buckets[host] = bucket
            return bucket

    def try_acquire(self, host: str, tokens: float = 1.0) -> bool:
        """No bloquea: devuelve True si había tokens, False si no."""
        bucket = self._bucket(host)
        with bucket.lock:
            bucket.refill()
            if bucket.tokens >= tokens:
                bucket.tokens -= tokens
                return True
            return False

    def acquire(self, host: str, tokens: float = 1.0) -> None:
        """Bloquea hasta que haya `tokens` disponibles para `host`."""
        bucket = self._bucket(host)
        if tokens > bucket.capacity:
            raise ValueError(
                f"requested {tokens} tokens but bucket capacity for {host!r} is {bucket.capacity}"
            )
        while True:
            with bucket.lock:
                bucket.refill()
                if bucket.tokens >= tokens:
                    bucket.tokens -= tokens
                    return
                deficit = tokens - bucket.tokens
                wait = deficit / bucket.rate
            self._sleeper(wait)
