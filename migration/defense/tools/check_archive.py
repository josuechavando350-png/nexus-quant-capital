"""Exercise persisted audit pages and recoverable witness confirmation with real files."""

import json
from pathlib import Path
import secrets
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nqc_defense.archive_store import ArchiveStore
from nqc_defense.codec import Rejected, canonical
from nqc_defense.engine import Engine
from nqc_defense.enroll import enroll
from nqc_defense.files import read_local, sha256
from nqc_defense.witness import Witness


def run():
    source_bytes = (Path(__file__).resolve().parents[1] / "nqc_defense/engine.py").read_bytes()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        assets = root / "assets"
        assets.mkdir()
        (assets / "engine.py").write_bytes(source_bytes)
        enrolled = enroll(assets, "engine.py", "archive-source", "guard", root / "control")
        control = root / "control"
        key, digest = read_local(control, "ledger.key", 32), enrolled["policy_digest"]
        witness = Witness.create(root / "witness", secrets.token_bytes(32), key, digest)
        archive = ArchiveStore.create(root / "archive")
        engine = Engine(assets, control / "configs", control / "state", digest, key, witness=witness)
        _, snapshot = engine.admit_bytes(canonical({"request_id": "source", "asset": "archive-source"}),
                                        engine.issue("local-archive-check", "archive-source"))
        if snapshot != source_bytes:
            raise Rejected("archive_source_mismatch")
        target, expected = engine.checkpoint(), witness.head()
        result = archive.capture(engine, witness, target, expected, limit=1)
        reopened = ArchiveStore(archive.root)
        verified = reopened.verify(result["manifest_sha256"], key, digest)
        recovered = reopened.finalize(witness, result["manifest_sha256"], expected)
        if (verified["pages"] != 3 or verified["record_count"] != 3
                or not recovered["recovered_existing_commit"]
                or recovered["witness_receipt"] != result["witness_receipt"]
                or engine.checkpoint() != target):
            raise Rejected("archive_acceptance_failed")
        manifest = json.loads(read_local(archive.root, "manifests/" + result["manifest_sha256"] + ".json"))
        damaged = archive.root / "pages" / (manifest["pages"][0]["sha256"] + ".zip")
        damaged.write_bytes(b"controlled local archive corruption")
        try:
            reopened.finalize(witness, result["manifest_sha256"], expected)
        except Rejected as exc:
            if str(exc) != "archive_page_integrity":
                raise
        else:
            raise RuntimeError("recovery accepted a corrupted stored page")
        if witness.head() != result["witness_receipt"]:
            raise Rejected("archive_witness_changed_after_corruption")
        return {"status": "LOCAL_ARCHIVE_ACCEPTANCE_PASS", "source_sha256": sha256(source_bytes),
                "stored_pages_verified_after_reopen": verified["pages"], "records_verified": verified["record_count"],
                "stored_page_bytes": verified["stored_page_bytes"], "witness_revision": result["witness_receipt"]["revision"],
                "lost_ack_recovered_without_duplicate": True, "corrupted_stored_page_blocks_recovery": True,
                "engine_history_unchanged": True,
                "scope": "local fsynced files and point-in-time reread; no physical power-loss test or independent replica"}


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
