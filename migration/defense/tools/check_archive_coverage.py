"""Verify real local archive intervals, missing coverage, and pinned historical targets."""

import json
from pathlib import Path
import secrets
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nqc_defense.archive_coverage import ArchiveCoverage
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
        enrolled = enroll(assets, "engine.py", "coverage-source", "guard", root / "control")
        control = root / "control"
        key, digest = read_local(control, "ledger.key", 32), enrolled["policy_digest"]
        witness = Witness.create(root / "witness", secrets.token_bytes(32), key, digest)
        archive = ArchiveStore.create(root / "archive")
        engine = Engine(assets, control / "configs", control / "state", digest, key, witness=witness)
        origin, manifests = witness.head(), []
        def capture(index):
            _, data = engine.admit_bytes(canonical({"request_id": f"source-{index}", "asset": "coverage-source"}),
                                        engine.issue("local-coverage-check", "coverage-source"))
            if data != source:
                raise Rejected("coverage_source_mismatch")
            return archive.capture(engine, witness, engine.checkpoint(), witness.head(), limit=1)["manifest_sha256"]
        for index in range(3):
            manifests.append(capture(index))
        target = witness.head()
        checker = ArchiveCoverage(archive, witness)
        sealed = checker.seal(manifests, origin, target)
        if sealed["interval_count"] != 3 or sealed["record_count"] != 9 or sealed["page_count"] != 9:
            raise Rejected("coverage_acceptance_failed")
        for partial, reason in (([manifests[0], manifests[2]], "coverage_gap"), (manifests[:-1], "coverage_incomplete")):
            try:
                checker.verify(partial, origin, target)
            except Rejected as exc:
                if str(exc) != reason:
                    raise
            else:
                raise RuntimeError("incomplete coverage accepted")
        capture(3)
        checked = checker.verify_catalog(sealed["catalog_sha256"], origin, target)
        try:
            checker.verify_catalog(sealed["catalog_sha256"], origin, witness.head())
        except Rejected as exc:
            if str(exc) != "coverage_catalog_anchor_mismatch":
                raise
        else:
            raise RuntimeError("historical catalog accepted a newer target")
        manifest = json.loads(read_local(archive.root, "manifests/" + manifests[1] + ".json"))
        path = archive.root / "pages" / (manifest["pages"][0]["sha256"] + ".zip")
        path.write_bytes(b"controlled local page corruption")
        try:
            checker.verify_catalog(sealed["catalog_sha256"], origin, target)
        except Rejected as exc:
            if str(exc) != "archive_page_integrity":
                raise
        else:
            raise RuntimeError("corrupted archive coverage accepted")
        return {"status": "LOCAL_ARCHIVE_COVERAGE_ACCEPTANCE_PASS", "source_sha256": sha256(source),
                "intervals_verified": checked["interval_count"], "records_verified": checked["record_count"],
                "pages_verified": checked["page_count"], "pinned_target_sequence": target["checkpoint"]["sequence"],
                "current_engine_sequence": engine.checkpoint()["sequence"], "middle_gap_rejected": True,
                "missing_tail_rejected": True, "later_interval_excluded_from_pinned_coverage": True,
                "new_target_requires_new_catalog": True, "stored_corruption_detected": True,
                "scope": "local archive coverage at check time; no deletion, replication or production activation"}


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
