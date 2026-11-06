"""Demonstrate local checkpoint rollback rejection using real files and SQLite."""

import json
from pathlib import Path
import secrets
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nqc_defense.audit_pages import AuditPageVerifier
from nqc_defense.codec import Rejected, canonical
from nqc_defense.engine import Engine
from nqc_defense.enroll import enroll
from nqc_defense.files import read_local, sha256
from nqc_defense.witness import Witness


def run():
    source = Path(__file__).resolve().parents[1] / "nqc_defense/engine.py"
    source_bytes = source.read_bytes()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        assets = root / "assets"
        assets.mkdir()
        (assets / "engine.py").write_bytes(source_bytes)
        enrolled = enroll(assets, "engine.py", "witness-source", "guard", root / "control")
        control = root / "control"
        key, digest = read_local(control, "ledger.key", 32), enrolled["policy_digest"]
        witness = Witness.create(root / "separate-witness", secrets.token_bytes(32), key, digest)
        engine = Engine(assets, control / "configs", control / "state", digest, key, witness=witness)
        raw = canonical({"request_id": "source-capture", "asset": "witness-source"})
        _, data = engine.admit_bytes(raw, engine.issue("local-check", "witness-source"))
        if data != source_bytes:
            raise Rejected("witness_source_mismatch")
        pending = engine.issue("local-check", "witness-source")
        target, expected = engine.checkpoint(), witness.head()
        def pages():
            verifier = AuditPageVerifier(key, digest, target)
            while not verifier.complete:
                page = engine.export_page(verifier.current, target, limit=1)
                verifier.accept(page)
                yield page
        saved = witness.advance(pages(), target, expected)
        # Fault injection is confined to the new temporary state, never repository data.
        with engine.state.transaction() as db:
            db.execute("DELETE FROM audit WHERE seq>=3")
        unguarded = Engine(assets, control / "configs", control / "state", digest, key)
        valid_prefix = unguarded.checkpoint()
        try:
            engine.admit_bytes(canonical({"request_id": "after-rollback", "asset": "witness-source"}), pending)
        except Rejected as exc:
            if str(exc) != "audit_anchor_unavailable":
                raise
            blocked = True
        else:
            raise RuntimeError("guarded consumer accepted rolled-back history")
        with engine.state.connection() as db:
            unconsumed = db.execute("SELECT count(*) FROM tokens WHERE consumed=0").fetchone()[0]
        if valid_prefix["sequence"] != 2 or unconsumed != 1 or witness.head(saved) != saved:
            raise Rejected("witness_acceptance_failed")
        # Record the trust limit explicitly: rollback of the witness itself needs its retained receipt.
        with witness.connection(write=True) as db:
            db.execute("DELETE FROM anchors WHERE revision=2")
        try:
            witness.head(saved)
        except Rejected as exc:
            if str(exc) != "witness_receipt_mismatch":
                raise
        else:
            raise RuntimeError("external receipt did not detect witness rollback")
        return {"status": "LOCAL_WITNESS_ACCEPTANCE_PASS", "source_sha256": sha256(source_bytes),
                "anchored_sequence": target["sequence"], "remaining_valid_hmac_prefix": valid_prefix["sequence"],
                "guarded_consumer_blocked": blocked, "pending_token_still_unconsumed": True,
                "witness_unchanged_by_engine_rollback": True,
                "separately_retained_receipt_detected_witness_rollback": True,
                "scope": "local temporary state and retained receipt; no independent remote witness or root resistance"}


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
