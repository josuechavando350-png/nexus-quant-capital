"""Single-owner research ingress. Uses R5 proof traversal with R3 checks and direct Rust arithmetic.

Deadlines reject late results; they cannot preempt OS scheduling or verifier work.
Even a valid witness produces no commercial authorization.
"""
from dataclasses import dataclass
from pathlib import Path
import sys
import threading
import time

R3 = Path(__file__).resolve().parents[2] / "r3-state-evidence"
sys.path.insert(0, str(R3 / "src"))
from gateway import Conditional
from state_evidence import Policy, Rejected, require
from state_evidence_fast import verify


@dataclass(frozen=True)
class Ticket:
    session: object
    epoch: int
    block_hash: bytes
    market_id: bytes
    borrower: bytes


class StableGateway:
    def __init__(self, policy: Policy, math, *, clock=time.monotonic_ns,
                 max_ingest_ns=50_000_000, max_scenario_ns=5_000_000):
        require(type(policy) is Policy, "policy type")
        require(type(max_ingest_ns) is int and max_ingest_ns > 0 and
                type(max_scenario_ns) is int and max_scenario_ns > 0, "processing budget")
        self._thread = threading.current_thread()
        self._session = object()
        self._epoch = 0
        self._policy = policy
        self._facts = None
        self._ticket = None
        self._busy = False
        self._last_now = 0
        self._last_tick = 0
        self._expires = 0
        self._clock = clock
        self._math = math
        self._max_ingest = max_ingest_ns
        self._max_scenario = max_scenario_ns

    def _owner(self):
        require(threading.current_thread() is self._thread, "gateway thread confinement")
        if self._busy:
            self._invalidate()
            raise Rejected("reentrant gateway access")

    def _invalidate(self):
        self._epoch += 1
        self._facts = self._ticket = None
        self._expires = 0

    def _tick(self):
        tick = self._clock()
        require(type(tick) is int and tick >= self._last_tick, "monotonic clock invalid/backwards")
        self._last_tick = tick
        return tick

    def reset(self, policy):
        self._owner()
        self._invalidate()
        require(type(policy) is Policy, "policy type")
        self._policy = policy

    def ingest(self, raw, now_s):
        self._owner()
        self._invalidate()
        self._busy = True
        try:
            require(type(now_s) is int and now_s >= self._last_now, "observation time moved backwards")
            self._last_now = now_s
            start = self._tick()
            facts = verify(raw, self._policy, now_s, shared=True)
            end = self._tick()
            require(end - start <= self._max_ingest, "ingress processing deadline exceeded")
            expires = start + (facts.anchor.timestamp + self._policy.max_age_s - now_s) * 10**9
            require(end <= expires, "snapshot expired during verification")
            ticket = Ticket(self._session, self._epoch, facts.anchor.block_hash, facts.market_id, facts.borrower)
            self._facts, self._ticket, self._expires = facts, ticket, expires
            return ticket
        except BaseException:
            self._invalidate()
            raise
        finally:
            self._busy = False

    def _current(self, ticket, now_s):
        self._owner()
        try:
            require(ticket is self._ticket and type(ticket) is Ticket and self._facts is not None,
                    "foreign, copied or superseded ticket")
            require(ticket.session is self._session and ticket.epoch == self._epoch and
                    ticket.block_hash == self._facts.anchor.block_hash and
                    ticket.market_id == self._facts.market_id and ticket.borrower == self._facts.borrower,
                    "ticket identity")
            require(type(now_s) is int and now_s >= self._last_now and
                    self._facts.anchor.timestamp <= now_s <=
                    self._facts.anchor.timestamp + self._policy.max_age_s, "stale observation clock")
            require(self._tick() <= self._expires, "monotonic snapshot expiry")
            self._last_now = now_s
            return self._facts
        except BaseException:
            self._invalidate()
            raise

    def facts(self, ticket, now_s):
        return self._current(ticket, now_s)

    def scenario(self, ticket, now_s, assumed_price):
        facts = self._current(ticket, now_s)
        self._busy = True
        try:
            start = self._tick()
            require(type(assumed_price) is int and 0 < assumed_price < 2**256, "scenario price")
            v = facts.values()
            require(v["time_fee"] % 2**128 == facts.anchor.timestamp,
                    "accrual unknown; conditional health unavailable")
            result = self._math.health([v["borrow"] % 2**128, v["borrow"] >> 128,
                                       v["position"] % 2**128, v["position"] >> 128,
                                       assumed_price, v["lltv"]])
            require(type(result) is tuple and len(result) == 3, "math result schema")
            debt, cap, eligible = result
            require(type(debt) is type(cap) is int and 0 <= debt < 2**256 and 0 <= cap < 2**256 and
                    type(eligible) is bool and eligible == (debt > cap), "math result consistency")
            end = self._tick()
            require(end - start <= self._max_scenario, "scenario processing deadline exceeded")
            require(ticket is self._ticket and facts is self._facts, "snapshot revoked during calculation")
            require(end <= self._expires, "snapshot expired during calculation")
            return Conditional(debt, cap, eligible, assumed_price, facts.anchor.timestamp)
        except BaseException:
            self._invalidate()
            raise
        finally:
            self._busy = False

    def authorize(self, ticket, now_s):
        self._current(ticket, now_s)
        return {"commercial_admission": False, "observed_candidate": None,
                "missing": ("canonical_chain_evidence", "runtime_layout_attestation",
                            "oracle_execution_and_freshness", "full_execution_simulation",
                            "financial_and_nonrecourse_authorization")}
