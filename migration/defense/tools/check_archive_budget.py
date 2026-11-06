"""Exercise a full pinned archive budget through real admission, archival and recovery."""

import json
from pathlib import Path
import secrets
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nqc_defense.archive_coverage import ArchiveCoverage
from nqc_defense.archive_inventory import ArchiveInventory
from nqc_defense.archive_store import ArchiveStore
from nqc_defense.codec import Rejected, canonical
from nqc_defense.engine import Engine
from nqc_defense.enroll import enroll
from nqc_defense.files import read_local, sha256
from nqc_defense.witness import Witness


def run():
    source = (Path(__file__).resolve().parents[1] / "nqc_defense/engine.py").read_bytes()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        assets = root / "assets"
        assets.mkdir()
        (assets / "engine.py").write_bytes(source)
        enrolled = enroll(assets, "engine.py", "budget-source", "guard", root / "control")
        control = root / "control"
        key, digest = read_local(control, "ledger.key", 32), enrolled["policy_digest"]
        witness = Witness.create(root / "witness", secrets.token_bytes(32), key, digest)
        archive = ArchiveStore.create(root / "archive")
        configured = archive.configure_budget(128 * 1024, 6)
        archive = ArchiveStore(archive.root, configured["budget_digest"])
        engine = Engine(assets, control / "configs", control / "state", digest, key, witness=witness)
        origin = witness.head()
        def admit(index):
            _, data = engine.admit_bytes(canonical({"request_id": f"budget-source-{index}", "asset": "budget-source"}),
                                        engine.issue("local-budget-check", "budget-source"))
            if data != source:
                raise Rejected("budget_source_mismatch")
        admit(0)
        target = engine.checkpoint()
        captured = archive.capture(engine, witness, target, origin, limit=1)
        anchor = witness.head()
        coverage = ArchiveCoverage(archive, witness)
        sealed = coverage.seal([captured["manifest_sha256"]], origin, anchor)
        full = archive.budget_status()
        if not full["within_budget"] or full["remaining_objects"] != 0 or full["used_objects"] != 6:
            raise Rejected("budget_acceptance_failed")
        files = {str(path.relative_to(archive.root)): path.read_bytes()
                 for path in archive.root.rglob("*") if path.is_file()}
        recovered = archive.capture(engine, witness, target, origin, limit=1)
        repeated = coverage.seal([captured["manifest_sha256"]], origin, anchor)
        if not recovered["recovered_existing_commit"] or repeated != sealed or archive.budget_status() != full:
            raise Rejected("budget_retry_failed")
        admit(1)
        try:
            archive.capture(engine, witness, engine.checkpoint(), anchor, limit=1)
        except Rejected as exc:
            if str(exc) != "archive_budget_exceeded":
                raise
        else:
            raise RuntimeError("full archive accepted a new object")
        after = {str(path.relative_to(archive.root)): path.read_bytes()
                 for path in archive.root.rglob("*") if path.is_file()}
        if witness.head() != anchor or engine.checkpoint()["sequence"] != 6 or files != after:
            raise Rejected("budget_failure_changed_evidence")
        inventory = ArchiveInventory(archive, witness).inspect([{"catalog_sha256": sealed["catalog_sha256"],
                     "start_receipt": origin, "target_receipt": anchor}])
        if not inventory["verified"] or inventory["observed_logical_bytes"] != full["used_logical_bytes"]:
            raise Rejected("budget_inventory_mismatch")
        return {"status": "LOCAL_ARCHIVE_BUDGET_ACCEPTANCE_PASS", "source_sha256": sha256(source),
                "budget_reopened_with_external_digest": True, "object_limit": 6, "objects_used": full["used_objects"],
                "byte_limit": full["limits"]["max_logical_bytes"], "policy_counted_as_object": True,
                "republishing_at_limit_verified": True, "new_object_rejected_at_limit": True,
                "quota_exhaustion_preserved_checkpoint": True, "archived_checkpoint_sequence": anchor["checkpoint"]["sequence"],
                "current_engine_sequence": engine.checkpoint()["sequence"], "archive_bytes_unchanged_after_rejection": True,
                "inventory_matches_budget_usage": True, "scope": "cooperating local writer budget; no deletion, OS quota or production activation"}


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
