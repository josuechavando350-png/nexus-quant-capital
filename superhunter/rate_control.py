"""Nonblocking local admission through pinned DIABLO ScopeGuard/RateLimiter.

This module does not send requests, schedule work, execute callbacks or grant
network permission. It validates a narrow local-use interface around unchanged
native sources. Rates are PER NORMALIZED KEY, not a global rate across keys.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import threading
import time
from typing import Callable

from .native_runtime import load_components


class AdmissionError(ValueError):
    """Fixed diagnostics; no supplied identifiers or policy details are echoed."""


def _number(value: object, code: str, *, maximum: float = 1_000_000) -> float:
    if type(value) not in (float, int):
        raise AdmissionError(code)
    try:
        number = float(value)
    except OverflowError as exc:
        raise AdmissionError(code) from exc
    if not math.isfinite(number) or not 0 < number <= maximum:
        raise AdmissionError(code)
    return number


def _key(value: object) -> str:
    if type(value) is not str or not 0 < len(value) <= 512:
        raise AdmissionError('INVALID_LOCAL_KEY')
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise AdmissionError('INVALID_LOCAL_KEY')
    normalized = value.strip().rstrip('.').lower()
    if not normalized or any(c.isspace() for c in normalized):
        raise AdmissionError('INVALID_LOCAL_KEY')
    return normalized


def _configuration(scope: object) -> tuple:
    """Detect in-process policy/rate mutation; this is not policy authentication."""
    rate = _number(scope.rps, 'INVALID_RATE')
    rates = scope.rps_per_host
    if type(rates) is not dict or len(rates) > 4096:
        raise AdmissionError('INVALID_PER_KEY_RATES')
    checked = []
    for name, value in rates.items():
        if _key(name) != name:
            raise AdmissionError('NONCANONICAL_RATE_KEY')
        checked.append((name, _number(value, 'INVALID_PER_KEY_RATE')))
    return (rate, tuple(sorted(checked)), tuple(r.raw for r in scope._in),
            tuple(r.raw for r in scope._out))


@dataclass(frozen=True)
class AdmissionStats:
    admitted: int
    deferred: int
    keys: int


class ScopedRateLimiter:
    """Scope-check each attempt before consuming positive, finite native tokens.

    Only try_admit is exposed: no sleep loops, no blocking acquire, no callback.
    A configuration change or invalid clock aborts instead of bypassing a limit.
    Native exceptions are sanitized. This is thread-safe for this one instance,
    not a distributed limiter or an operating-system security boundary.
    """

    def __init__(self, scope: object, *, capacity: int = 1,
                 max_keys: int = 256, clock: Callable[[], float] = time.monotonic) -> None:
        native = load_components()
        if not isinstance(scope, native.scope.ScopeGuard):
            raise AdmissionError('NATIVE_SCOPE_REQUIRED')
        if type(capacity) is not int or not 1 <= capacity <= 1_000_000:
            raise AdmissionError('INVALID_CAPACITY')
        if type(max_keys) is not int or not 1 <= max_keys <= 4096 or not callable(clock):
            raise AdmissionError('INVALID_GATE_CONFIGURATION')
        self._scope = scope
        self._config = _configuration(scope)
        self._target_class = native.models.Target
        self._capacity = capacity
        self._max_keys = max_keys
        self._clock = clock
        self._last_time = None
        self._lock = threading.RLock()
        self._keys: set[str] = set()
        self._admitted = 0
        self._deferred = 0
        self._clock_value()  # Validate the clock before creating native state.
        self._limiter = scope.rate_limiter(capacity=capacity, clock=self._clock_value,
                                          sleeper=self._no_sleep)

    @staticmethod
    def _no_sleep(_: float) -> None:
        raise AdmissionError('BLOCKING_EXECUTION_DISABLED')

    def _clock_value(self) -> float:
        try:
            value = self._clock()
            if type(value) not in (float, int):
                raise ValueError()
            now = float(value)
            if not math.isfinite(now) or now < 0 or now > 1e12:
                raise ValueError()
        except Exception:
            raise AdmissionError('INVALID_CLOCK') from None
        if self._last_time is not None and now < self._last_time:
            raise AdmissionError('CLOCK_MOVED_BACKWARDS')
        self._last_time = now
        return now

    def try_admit(self, target: object, tokens: int | float = 1) -> bool:
        amount = _number(tokens, 'INVALID_TOKEN_AMOUNT')
        if amount > self._capacity:
            raise AdmissionError('REQUEST_EXCEEDS_CAPACITY')
        if type(target) is str:
            target = self._target_class(value=target)
        elif not isinstance(target, self._target_class):
            raise AdmissionError('INVALID_TARGET_TYPE')
        key = _key(target.value)
        with self._lock:
            if _configuration(self._scope) != self._config:
                raise AdmissionError('SCOPE_CONFIGURATION_CHANGED')
            # Validate time before scope logging or any native bucket mutations.
            self._clock_value()
            try:
                self._scope.assert_allowed(target)
            except PermissionError:
                raise AdmissionError('SCOPE_DENIED') from None
            if key not in self._keys and len(self._keys) >= self._max_keys:
                raise AdmissionError('LOCAL_KEY_BUDGET_EXHAUSTED')
            try:
                granted = self._limiter.try_acquire(key, amount)
            except AdmissionError:
                raise
            except Exception:
                raise AdmissionError('NATIVE_LIMITER_ERROR') from None
            if type(granted) is not bool:
                raise AdmissionError('INVALID_NATIVE_DECISION')
            self._keys.add(key)
            if granted:
                self._admitted += 1
            else:
                self._deferred += 1
            return granted

    def stats(self) -> AdmissionStats:
        with self._lock:
            return AdmissionStats(self._admitted, self._deferred, len(self._keys))
