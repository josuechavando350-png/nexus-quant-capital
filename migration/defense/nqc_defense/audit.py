"""X101: authenticated audit chain. Truncation requires an external checkpoint."""

import hashlib
import hmac

from .codec import Rejected, canonical, decode

GENESIS = "0" * 64


def key_id(key):
    return hmac.new(key, b"nqc-defense-ledger-key-v1", hashlib.sha256).hexdigest()


def mac(key, sequence, previous, payload):
    return hmac.new(key, canonical([sequence, previous, payload]), hashlib.sha256).hexdigest()


class Ledger:
    def __init__(self, key):
        if not isinstance(key, bytes) or len(key) < 32:
            raise Rejected("audit_key_size")
        self.key = key

    def append(self, db, event):
        row = db.execute("SELECT seq, mac FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        sequence, previous = (row[0] + 1, row[1]) if row else (1, GENESIS)
        payload = canonical(event).decode()
        digest = mac(self.key, sequence, previous, payload)
        db.execute("INSERT INTO audit VALUES (?, ?, ?, ?)", (sequence, payload, previous, digest))
        return digest

    def verify(self, db, checkpoint=None):
        previous, sequence = GENESIS, 0
        for seq, payload, parent, digest in db.execute("SELECT seq,payload,previous,mac FROM audit ORDER BY seq"):
            if seq != sequence + 1 or parent != previous:
                raise Rejected("audit_sequence")
            if not hmac.compare_digest(digest, mac(self.key, seq, parent, payload)):
                raise Rejected("audit_integrity")
            decode(payload.encode())
            previous, sequence = digest, seq
        result = {"sequence": sequence, "head": previous}
        if checkpoint is not None and result != checkpoint:
            raise Rejected("audit_checkpoint_mismatch")
        return result
