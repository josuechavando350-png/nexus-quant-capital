"""Bounded offline capture assembly around unchanged R6/R5 verification.

This is not an HTTP, RPC or consensus client. The trusted transport supplies
ordered immutable bytes; untrusted content cannot set policy, deadlines or time.
Only one update may be in flight. Beginning an update revokes the older result.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
from pathlib import Path
import sys
import threading
import time

R6 = Path(__file__).resolve().parents[2] / "r6-witness-ingress"
sys.path.insert(0, str(R6 / "python"))
from witness_gateway import StableGateway
from state_evidence import Policy, Rejected, require, MAX_PACKET


@dataclass(frozen=True)
class Receipt:
    capture_sha256: str
    bytes_received: int
    chunks_received: int
    capture_elapsed_ns: int


class StreamIngress:
    def __init__(self, policy, math, *, clock=time.monotonic_ns,
                 max_capture_ns=50_000_000, max_chunks=1024):
        require(type(policy) is Policy, "policy type")
        require(type(max_capture_ns) is int and 0 < max_capture_ns <= 50_000_000,
                "capture budget")
        require(type(max_chunks) is int and 0 < max_chunks <= 1024, "chunk limit")
        self._thread = threading.current_thread()
        self._policy, self._clock = policy, clock
        self._engine = StableGateway(policy, math, clock=clock)
        self._budget, self._max_chunks = max_capture_ns, max_chunks
        self._last_tick = self._last_now = self._epoch = 0
        self._capture = self._receipt = self._ticket = self._buffer = None
        self._chunks = self._started = self._expires = 0
        self._busy = False

    def _invalidate(self):
        self._epoch += 1
        self._capture = self._receipt = self._ticket = self._buffer = None
        self._chunks = self._started = self._expires = 0
        try:
            self._engine.reset(self._policy)
        except Rejected:
            # R6 itself revokes state on a reentrant reset while verifying.
            # The enclosing operation always raises; no result is returned.
            pass

    @contextmanager
    def _operation(self):
        require(threading.current_thread() is self._thread, "stream thread confinement")
        if self._busy:
            self._invalidate()
            raise Rejected("reentrant stream access")
        self._busy = True
        epoch = self._epoch
        try:
            yield
            require(self._epoch == epoch, "stream revoked during operation")
        except BaseException:
            self._invalidate()
            raise
        finally:
            self._busy = False

    def _tick(self):
        tick = self._clock()
        require(type(tick) is int and tick >= self._last_tick,
                "stream monotonic clock invalid/backwards")
        self._last_tick = tick
        return tick

    def _observe(self, now_s):
        a, age = self._policy.anchor, self._policy.max_age_s
        require(type(a.timestamp) is int and type(age) is int and age > 0 and
                type(now_s) is int and now_s >= self._last_now and
                a.timestamp <= now_s <= a.timestamp + age,
                "stream stale/future/backwards observation")
        self._last_now = now_s

    def _alive(self, now_s, collecting=False):
        self._observe(now_s)
        tick = self._tick()
        require(tick <= self._expires, "stream snapshot expired")
        if collecting:
            require(tick - self._started <= self._budget, "capture deadline exceeded")
        return tick

    def _append(self, chunk):
        require(type(chunk) is bytes and len(chunk) > 0, "nonempty immutable chunk required")
        require(len(chunk) <= MAX_PACKET - len(self._buffer), "capture size limit")
        require(self._chunks < self._max_chunks, "capture chunk limit")
        self._buffer.extend(chunk)
        self._chunks += 1

    def begin(self, policy, now_s, first_chunk):
        # Reset before entering the operation so its epoch is the new generation.
        require(threading.current_thread() is self._thread, "stream thread confinement")
        if self._busy:
            self._invalidate()
            raise Rejected("reentrant stream access")
        self._invalidate()
        with self._operation():
            require(type(policy) is Policy, "policy type")
            self._policy = policy
            self._engine.reset(policy)
            self._observe(now_s)
            self._started = self._tick()
            self._expires = self._started + (policy.anchor.timestamp + policy.max_age_s - now_s) * 10**9
            self._capture = object()
            self._buffer = bytearray()
            self._append(first_chunk)
            self._alive(now_s, collecting=True)
            return self._capture

    def feed(self, capture, offset, chunk, now_s):
        with self._operation():
            require(capture is not None and capture is self._capture and self._buffer is not None,
                    "foreign or superseded capture")
            self._alive(now_s, collecting=True)
            require(type(offset) is int and offset == len(self._buffer), "capture offset mismatch")
            self._append(chunk)
            self._alive(now_s, collecting=True)

    def finish(self, capture, now_s):
        with self._operation():
            require(capture is not None and capture is self._capture and self._buffer is not None,
                    "foreign or superseded capture")
            self._alive(now_s, collecting=True)
            raw = bytes(self._buffer)
            self._buffer = None
            digest = hashlib.sha256(raw).hexdigest()
            ticket = self._engine.ingest(raw, now_s)
            end = self._alive(now_s, collecting=True)
            receipt = Receipt(digest, len(raw), self._chunks, end - self._started)
            self._capture = None
            self._ticket, self._receipt = ticket, receipt
            return receipt

    def _current(self, receipt, now_s):
        require(receipt is not None and receipt is self._receipt and self._ticket is not None
                and self._capture is None, "foreign, copied or superseded receipt")
        self._alive(now_s)

    def facts(self, receipt, now_s):
        with self._operation():
            self._current(receipt, now_s)
            facts = self._engine.facts(self._ticket, now_s)
            self._alive(now_s)
            return facts

    def scenario(self, receipt, now_s, assumed_price):
        with self._operation():
            self._current(receipt, now_s)
            result = self._engine.scenario(self._ticket, now_s, assumed_price)
            self._alive(now_s)
            return result

    def authorize(self, receipt, now_s):
        with self._operation():
            self._current(receipt, now_s)
            result = self._engine.authorize(self._ticket, now_s)
            self._alive(now_s)
            return result

    def abort(self):
        require(threading.current_thread() is self._thread, "stream thread confinement")
        if self._busy:
            self._invalidate()
            raise Rejected("reentrant stream access")
        self._invalidate()
