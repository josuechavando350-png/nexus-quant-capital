"""Sequential research ingress with epoch invalidation and conditional R1 math.

Thread confinement is part of the contract. A worker publishes no candidate while
verification is in progress. This is not a production authorization interface.
"""
from dataclasses import dataclass
import subprocess
import threading

from state_evidence import Policy, Rejected, require, verify


@dataclass(frozen=True)
class Ticket:
    epoch: int
    block_hash: bytes
    observed_eligibility: None = None
    commercial_admission: bool = False


@dataclass(frozen=True)
class Conditional:
    debt: int
    capacity: int
    eligible_if_assumptions_hold: bool
    assumed_price: int
    state_time_s: int
    label: str = "conditional_prediction_not_observed_eligibility"
    commercial_admission: bool = False


class MathWorker:
    """Existing, unchanged Rust R1 evaluator; local stdin/stdout only."""
    def __init__(self, executable):
        self.process = subprocess.Popen([str(executable)], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, text=True, bufsize=1)

    def health(self, args):
        require(len(args) == 6 and all(type(x) is int and 0 <= x < 2**256 for x in args),
                "math input range")
        self.process.stdin.write("H " + " ".join(f"{x:064x}" for x in args) + "\n")
        self.process.stdin.flush()
        row = self.process.stdout.readline().split()
        require(len(row) == 4 and row[0] == "OK", "R1 math rejected/unavailable")
        try:
            debt, cap, eligible = [int(x, 16) for x in row[1:]]
        except ValueError as e:
            raise Rejected("R1 malformed output") from e
        require(eligible in (0, 1), "R1 result range")
        return debt, cap, bool(eligible)

    def close(self):
        self.process.stdin.close()
        self.process.stdout.close()
        self.process.wait(timeout=10)


class Gateway:
    def __init__(self, policy: Policy):
        self._owner = threading.get_ident()
        self._policy = policy
        self._epoch = 0
        self._facts = None
        self._last_now = 0

    def _check_thread(self):
        require(threading.get_ident() == self._owner, "gateway thread confinement")

    def _invalidate(self):
        self._epoch += 1
        self._facts = None

    def reset(self, policy):
        self._check_thread()
        self._invalidate()
        self._policy = policy
        # Keep the local monotonic observation watermark across a reorg.

    def ingest(self, raw, now_s, *, shared=True):
        self._check_thread()
        self._invalidate()  # Invalid input must never leave a previous ticket usable.
        require(type(now_s) is int and now_s >= self._last_now, "local time moved backwards")
        self._last_now = now_s
        facts = verify(raw, self._policy, now_s, shared=shared)
        self._facts = facts
        return Ticket(self._epoch, facts.anchor.block_hash)

    def _current(self, ticket, now_s):
        self._check_thread()
        try:
            require(type(ticket) is Ticket and self._facts is not None, "no verified snapshot")
            require(type(now_s) is int and now_s >= self._last_now, "local time moved backwards")
            require(ticket.epoch == self._epoch and ticket.block_hash == self._facts.anchor.block_hash,
                    "superseded ticket")
            require(self._facts.anchor.timestamp <= now_s <=
                    self._facts.anchor.timestamp + self._policy.max_age_s, "expired ticket")
        except Rejected:
            self._invalidate()
            raise
        self._last_now = now_s
        return self._facts

    def facts(self, ticket, now_s):
        return self._current(ticket, now_s)

    def scenario(self, ticket, now_s, assumed_price, worker):
        facts = self._current(ticket, now_s)
        try:
            require(type(assumed_price) is int and 0 < assumed_price < 2**256,
                    "scenario price")
            v = facts.values()
            # No IRM execution: stale stored debt is not current accrued debt.
            require(v["time_fee"] % 2**128 == facts.anchor.timestamp,
                    "accrual unknown; conditional health unavailable")
            args = [v["borrow"] % 2**128, v["borrow"] >> 128,
                    v["position"] % 2**128, v["position"] >> 128,
                    assumed_price, v["lltv"]]
            debt, capacity, eligible = worker.health(args)
            return Conditional(debt, capacity, eligible, assumed_price, facts.anchor.timestamp)
        except Exception:
            self._invalidate()
            raise

    def authorize(self, ticket, now_s):
        self._current(ticket, now_s)
        return {"commercial_admission": False, "observed_candidate": None,
                "missing": ("canonical_chain_evidence", "runtime_layout_attestation",
                            "oracle_execution_and_freshness", "full_execution_simulation",
                            "financial_and_nonrecourse_authorization")}
