"""Authenticated local wall-clock floor. This is not an independent time authority."""
import hmac
import time

from .audit import GENESIS, mac
from .codec import Rejected, canonical, decode, fields, integer
from .receipts import hex_digest

MAX_TIME = 2**63 - 1


class CredentialExpired(Rejected):
    def __init__(self, observed_ns):
        super().__init__("review_credential_expired")
        self.observed_ns = observed_ns


class ReviewClock:
    def __init__(self, policy):
        self.policy = policy

    def read(self, db, snapshot, *, initialize=False):
        row = db.execute("SELECT payload,mac FROM review_clock WHERE policy=?", (self.policy.digest,)).fetchone()
        enabled = any(v is not None for v in snapshot.expiries[-1].values())
        if row is None:
            if enabled and not initialize:
                raise Rejected("credential_clock_missing")
            return None
        payload, digest = row
        if not isinstance(payload, str) or len(payload.encode()) > 1024:
            raise Rejected("credential_clock_size")
        hex_digest(digest)
        if not hmac.compare_digest(digest, mac(self.policy.key, 1, GENESIS, payload)):
            raise Rejected("credential_clock_integrity")
        value = decode(payload.encode(), max_bytes=1024)
        fields(value, ("schema", "policy_digest", "credential_checkpoint", "observed_ns"))
        if canonical(value).decode() != payload or (value["schema"], value["policy_digest"]) != ("nqc-review-clock-v1", self.policy.digest):
            raise Rejected("credential_clock_binding")
        snapshot.contains(value["credential_checkpoint"])
        integer(value["observed_ns"], 0, MAX_TIME)
        if not enabled:
            raise Rejected("credential_clock_unexpected")
        return value

    def remember(self, db, snapshot, now, *, initialize=False):
        integer(now, 0, MAX_TIME)
        previous = self.read(db, snapshot, initialize=initialize)
        if not any(v is not None for v in snapshot.expiries[-1].values()):
            return
        minimum = max(previous["observed_ns"] if previous else 0,
                      snapshot.history[-1]["event"]["recorded_ns"] if snapshot.history else 0)
        if now < minimum:
            raise Rejected("credential_clock_regressed")
        value = {"schema": "nqc-review-clock-v1", "policy_digest": self.policy.digest,
                 "credential_checkpoint": snapshot.current, "observed_ns": now}
        payload = canonical(value).decode()
        digest = mac(self.policy.key, 1, GENESIS, payload)
        db.execute("INSERT INTO review_clock VALUES(?,?,?) ON CONFLICT(policy) DO UPDATE SET payload=excluded.payload,mac=excluded.mac",
                   (self.policy.digest, payload, digest))

    def observe(self, db, snapshot):
        now = integer(time.time_ns(), 0, MAX_TIME)
        self.remember(db, snapshot, now)
        return now
