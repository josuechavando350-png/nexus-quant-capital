"""M10: actual local admission/quarantine state transitions, not host isolation."""

import hashlib
import hmac
import time

from . import canary, freshness, identity, rate, receipts
from .audit import Ledger
from .build import archive
from .codec import Rejected, canonical, decode, identifier, integer, request, response
from .config import ConfigStore, controls
from .state import State
from .files import sha256


class Engine:
    def __init__(self, assets_root, configs_root, state_root, policy_digest, audit_key,
                 clock=None, checkpoint=None):
        self.root = assets_root
        self.configs = ConfigStore(configs_root)
        self.digest = policy_digest
        self.policy = self.configs.get(policy_digest)
        self.assets = {a["id"]: a for a in self.policy["assets"]}
        self.ledger = Ledger(audit_key)
        self.state = State(state_root, policy_digest)
        self.clock = clock or (lambda: int(time.time()))
        key_id = hmac.new(audit_key, b"nqc-defense-ledger-key-v1", hashlib.sha256).hexdigest()
        with self.state.transaction() as db:
            db.execute("INSERT OR IGNORE INTO meta VALUES('audit_key_id',?)", (key_id,))
            if not hmac.compare_digest(db.execute("SELECT value FROM meta WHERE key='audit_key_id'").fetchone()[0], key_id):
                raise Rejected("audit_key_mismatch")
            self.ledger.verify(db, checkpoint)

    def now(self):
        return integer(self.clock(), 0, 2**63 - 3601)

    def _check_policy(self):
        # The digest is a trust anchor supplied by the operator, not by the requester.
        if self.configs.get(self.digest) != self.policy:
            raise Rejected("policy_changed")

    def issue(self, subject, asset):
        """Local operator API. This method is deliberately absent from the HTTP surface."""
        self._check_policy()
        identifier(subject)
        if asset not in self.assets:
            raise Rejected("unknown_asset")
        with self.state.transaction() as db:
            self.ledger.verify(db)
            now = self.now()  # Read after waiting for the database and verifying the history.
            freshness.require_current(db, now)
            if db.execute("SELECT 1 FROM quarantine WHERE asset=?", (asset,)).fetchone():
                raise Rejected("asset_quarantined")
            token = identity.issue(db, subject, asset, now, self.policy["token_ttl_seconds"])
            self.ledger.append(db, {"kind": "token_issued", "subject": subject, "asset": asset, "time": now})
            freshness.advance(db, [now])
            return token

    def process(self, raw, token):
        result, _ = self._process(raw, token, retain_bytes=False)
        return result

    def admit_bytes(self, raw, token):
        """Authorize and return the inspected bytes after the complete transaction commits."""
        result, payload = self._process(raw, token, retain_bytes=True)
        if result["decision"] != "admit":
            raise Rejected("artifact_not_admitted")
        if not isinstance(payload, bytes):
            raise Rejected("artifact_snapshot_missing")
        return result, payload

    def _process(self, raw, token, retain_bytes):
        message = request(raw)
        self._check_policy()
        asset_id = message["asset"]
        if asset_id not in self.assets:
            raise Rejected("unknown_asset")
        with self.state.transaction() as db:
            self.ledger.verify(db)
            started = self.now()
            freshness.require_current(db, started)
            subject = identity.consume(db, token, asset_id, started)
            allowed = rate.admit(db, subject, started, self.policy["rate_limit"], self.policy["rate_window_seconds"])
            duplicate = bool(db.execute("SELECT 1 FROM requests WHERE subject=? AND request_id=?",
                                        (subject, message["request_id"])).fetchone())
            quarantined = bool(db.execute("SELECT 1 FROM quarantine WHERE asset=?", (asset_id,)).fetchone())
            quarantine_count = db.execute("SELECT count(*) FROM quarantine").fetchone()[0]
            observations = []
            artifact_bytes = None
            if allowed and not duplicate:
                db.execute("INSERT INTO requests VALUES(?,?,?)", (subject, message["request_id"], asset_id))
                if not quarantined:
                    observations, artifact_bytes = canary.observe_snapshot(self.root, self.assets[asset_id], self.now)
            decided = self.now()
            facts = {"started_at": started, "decided_at": decided, "rate_allowed": allowed,
                     "duplicate_request": duplicate, "was_quarantined": quarantined,
                     "quarantine_count": quarantine_count, "observations": observations}
            receipt = receipts.make(self.policy, subject, message, facts)
            outcome = receipt["outcome"]
            if outcome["transition"] == "quarantine":
                db.execute("INSERT INTO quarantine VALUES(?,?)", (asset_id, ",".join(outcome["reasons"])))
                identity.revoke_asset(db, asset_id)
            receipt_hash = receipts.digest(receipt)
            head = self.ledger.append(db, {"kind": "decision", "time": decided, "subject": subject,
                                          **message, "decision": outcome["decision"], "reasons": outcome["reasons"],
                                          "receipt_sha256": receipt_hash, "receipt": receipt})
            if retain_bytes and outcome["decision"] == "admit":
                if not isinstance(artifact_bytes, bytes) or sha256(artifact_bytes) != observations[0]["sha256"]:
                    raise Rejected("artifact_snapshot_mismatch")
                head = self.ledger.append(db, {"kind": "snapshot_authorized", "time": decided,
                                              "subject": subject, **message,
                                              "receipt_sha256": receipt_hash, "policy_digest": self.digest,
                                              "sha256": sha256(artifact_bytes), "size_bytes": len(artifact_bytes)})
            freshness.advance(db, [started, decided, *[x["observed_at"] for x in observations]])
            result = {**message, "decision": outcome["decision"], "reasons": outcome["reasons"],
                      "audit_head": head, "receipt_sha256": receipt_hash}
            response(result)  # Contract violations roll back the whole transaction.
        # Reaching this point proves SQLite commit succeeded. No bytes leave on rollback.
        return result, artifact_bytes if retain_bytes and result["decision"] == "admit" else None

    def release(self, asset):
        """Local operator release only after actual artifact and canary restoration."""
        self._check_policy()
        if asset not in self.assets:
            raise Rejected("unknown_asset")
        with self.state.transaction() as db:
            self.ledger.verify(db)
            started = self.now()
            freshness.require_current(db, started)
            observations = canary.observe(self.root, self.assets[asset], self.now)
            decided = self.now()
            stale = freshness.evaluate(started, decided, [x["observed_at"] for x in observations],
                                       controls(self.policy)["evidence_max_age_seconds"])
            if stale:
                raise Rejected(stale[0])
            if receipts.observations_for(self.assets[asset], observations):
                raise Rejected("integrity_not_restored")
            changed = db.execute("DELETE FROM quarantine WHERE asset=?", (asset,)).rowcount
            if changed:
                self.ledger.append(db, {"kind": "operator_release", "asset": asset, "time": decided,
                                       "policy_digest": self.digest, "observations": observations})
            freshness.advance(db, [started, decided, *[x["observed_at"] for x in observations]])
            return bool(changed)

    def receipt(self, receipt_sha256):
        """Retrieve and independently replay a receipt through the local operator API."""
        receipts.hex_digest(receipt_sha256)
        self._check_policy()
        with self.state.transaction() as db:
            self.ledger.verify(db)
            for payload, in db.execute("SELECT payload FROM audit ORDER BY seq"):
                event = decode(payload.encode())
                if event.get("receipt_sha256") == receipt_sha256:
                    receipt = event["receipt"]
                    receipts.verify(receipt, self.policy, receipt_sha256)
                    return receipt
        raise Rejected("receipt_not_found")

    def checkpoint(self):
        with self.state.transaction() as db:
            return self.ledger.verify(db)

    def export(self):
        """Repeatable audit archive: a read transaction cannot race a writer."""
        with self.state.transaction() as db:
            checkpoint = self.ledger.verify(db)
            records = [{"sequence": n, "payload": p, "previous": prev, "mac": mac}
                       for n, p, prev, mac in db.execute("SELECT seq,payload,previous,mac FROM audit ORDER BY seq")]
            return archive({"audit.json": canonical({"checkpoint": checkpoint, "records": records}),
                            "policy.sha3": self.digest.encode("ascii"), "policy.json": canonical(self.policy)})
