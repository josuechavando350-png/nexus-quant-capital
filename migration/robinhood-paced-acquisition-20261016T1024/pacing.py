"""One sequential start-spacing gate, independent of connection lifetime.

No token bucket and no burst credit. Times are local monotonic dispatch times,
not a claim about arrival spacing or the provider's quota implementation.
"""
import time

INTERVAL_NS = 350_000_000


class Pacer:
    def __init__(self, clock=None, sleep=None):
        self.clock = clock or time.monotonic_ns
        self.sleep = sleep or time.sleep
        self.last_start_ns = None

    def admit(self, deadline_ns, event):
        requested = self.clock()
        due = requested if self.last_start_ns is None else max(requested, self.last_start_ns + INTERVAL_NS)
        event.update(requested_ns=requested, due_ns=due, deadline_ns=deadline_ns)
        if requested >= deadline_ns:
            raise ValueError('TIME_BUDGET')
        if due >= deadline_ns:
            raise ValueError('PACING_TIME_BUDGET')
        if due > requested:
            self.sleep((due-requested)/1e9)
        admitted = self.clock()
        event['admitted_ns'] = admitted
        # Fail closed on an early wake; never dispatch early or spin/retry.
        if admitted < due:
            raise ValueError('PACING_EARLY_WAKE')
        if admitted >= deadline_ns:
            raise ValueError('TIME_BUDGET')
        return admitted

    def record_start(self, stamp):
        if self.last_start_ns is not None and stamp-self.last_start_ns < INTERVAL_NS:
            raise ValueError('PACING_START_GAP')
        self.last_start_ns = stamp
