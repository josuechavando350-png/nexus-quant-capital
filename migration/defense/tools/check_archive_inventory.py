"""Exercise local inventory using actual source admissions and persisted audit archives."""

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
from nqc_defense.files import create_local, read_local, sha256
from nqc_defense.witness import Witness


def run():
    source = (Path(__file__).resolve().parents[1] / "nqc_defense/engine.py").read_bytes()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        assets = root / "assets"
        assets.mkdir()
        (assets / "engine.py").write_bytes(source)
        enrolled = enroll(assets, "engine.py", "inventory-source", "guard", root / "control")
        control = root / "control"
        key, digest = read_local(control, "ledger.key", 32), enrolled["policy_digest"]
        witness = Witness.create(root / "witness", secrets.token_bytes(32), key, digest)
        archive = ArchiveStore.create(root / "archive")
        engine = Engine(assets, control / "configs", control / "state", digest, key, witness=witness)
        coverage, inventory = ArchiveCoverage(archive, witness), ArchiveInventory(archive, witness)
        origin, manifests, selected = witness.head(), [], []
        for index in range(2):
            _, data = engine.admit_bytes(canonical({"request_id": f"inventory-source-{index}", "asset": "inventory-source"}),
                                        engine.issue("local-inventory-check", "inventory-source"))
            if data != source:
                raise Rejected("inventory_source_mismatch")
            captured = archive.capture(engine, witness, engine.checkpoint(), witness.head(), limit=1)
            manifests.append(captured["manifest_sha256"])
            sealed = coverage.seal(manifests, origin, witness.head())
            selected.append({"catalog_sha256": sealed["catalog_sha256"], "start_receipt": origin,
                             "target_receipt": witness.head()})
        # An explicit leftover test object uses actual source bytes, never fabricated evidence.
        pending = "pending-" + "a" * 48
        create_local(archive.root, pending, source)
        before = {str(path.relative_to(archive.root)): path.read_bytes()
                  for path in archive.root.rglob("*") if path.is_file()}
        checkpoint, anchored = engine.checkpoint(), witness.head()
        both = inventory.inspect(selected)
        historical = inventory.inspect(selected[:1])
        if (not both["verified"] or both["observed_objects"] != 11
                or both["summary"]["page"]["objects"] != 6
                or historical["summary"]["page"]["outside_selected_objects"] != 3
                or both["summary"]["temporary"]["objects"] != 1):
            raise Rejected("inventory_acceptance_failed")
        after = {str(path.relative_to(archive.root)): path.read_bytes()
                 for path in archive.root.rglob("*") if path.is_file()}
        if before != after or engine.checkpoint() != checkpoint or witness.head() != anchored:
            raise Rejected("inventory_changed_state")
        manifest = json.loads(read_local(archive.root, "manifests/" + manifests[0] + ".json"))
        missing_path = "pages/" + manifest["pages"][0]["sha256"] + ".zip"
        # Fault injection affects only this temporary archive, after the read-only check.
        (archive.root / missing_path).unlink()
        missing = inventory.inspect(selected)
        if (missing["verified"] or missing["reference_classification_available"]
                or {"path": missing_path, "reason": "missing_reference"} not in missing["issues"]):
            raise Rejected("inventory_missing_reference_accepted")
        return {"status": "LOCAL_ARCHIVE_INVENTORY_ACCEPTANCE_PASS", "source_sha256": sha256(source),
                "selected_catalogs": len(selected), "unique_archive_objects": both["observed_objects"],
                "unique_pages": both["summary"]["page"]["objects"], "reference_edges": len(both["references"]),
                "overlapping_catalogs_share_pages": True, "logical_bytes_match_files": both["observed_logical_bytes"] == sum(map(len, before.values())),
                "historical_selection_excludes_later_pages": True, "pending_object_preserved": (archive.root / pending).read_bytes() == source,
                "files_and_checkpoints_unchanged_by_inspection": True, "missing_reference_path_reported": True,
                "missing_reference_disables_unused_classification": True, "deletion_authorized": both["deletion_authorized"],
                "scope": "local metadata inventory and selected coverage; fault injection only in temporary archive; no cleanup or production activation"}


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
