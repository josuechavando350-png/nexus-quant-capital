"""Read NQC's actual source manifest through byte-bound local admission."""

import argparse
import json
from pathlib import Path
import secrets
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nqc_defense.codec import Rejected, canonical
from nqc_defense.consumer import ArtifactReader
from nqc_defense.engine import Engine
from nqc_defense.enroll import enroll
from nqc_defense.files import read_local, sha256
from nqc_defense.integration import verify_nqc
from nqc_defense.verify_export import verify as verify_export
from nqc_defense.audit_pages import AuditPageVerifier
from nqc_defense.witness import Witness
from nqc_defense.archive_store import ArchiveStore


def run(root):
    root = root.absolute()
    baseline = verify_nqc(root)
    artifact = "migration/source-manifest.json"
    original = read_local(root, artifact)
    marker_path = "migration/defense/consumer-check-" + secrets.token_hex(16) + ".canary"
    marker = None
    try:
        with tempfile.TemporaryDirectory() as directory:
            control = Path(directory) / "control"
            enrollment = enroll(root, artifact, "nqc-source-manifest", marker_path, control)
            marker = read_local(root, marker_path)
            key = read_local(control, "ledger.key", 32)
            witness = Witness.create(Path(directory) / "witness", secrets.token_bytes(32), key, enrollment["policy_digest"])
            archive = ArchiveStore.create(Path(directory) / "archive")
            engine = Engine(root, control / "configs", control / "state", enrollment["policy_digest"], key, witness=witness)
            token = engine.issue("local-consumer-check", "nqc-source-manifest")
            result = ArtifactReader(engine).read_json(canonical({
                "request_id": "consume-nqc-source-manifest", "asset": "nqc-source-manifest"}), token)
            receipt = engine.receipt(result["admission"]["receipt_sha256"])
            checkpoint = engine.checkpoint()
            verified = verify_export(engine.export(), key, enrollment["policy_digest"], checkpoint)
            paged = AuditPageVerifier(key, enrollment["policy_digest"], checkpoint)
            while not paged.complete:
                paged.accept(engine.export_page(paged.current, checkpoint, limit=1))
            page_result = paged.finish()
            if (result["data"].get("schema") != "nqc-isolated-import-v1"
                    or result["content_sha256"] != sha256(original)
                    or result["size_bytes"] != len(original)
                    or verified["authorized_snapshots"] != 1
                    or page_result["authorized_snapshots"] != 1
                    or page_result["record_count"] != checkpoint["sequence"]
                    or checkpoint["head"] != result["admission"]["audit_head"]
                    or receipt["outcome"]["decision"] != "admit"):
                raise Rejected("nqc_consumer_check_failed")
            first_archive = archive.capture(engine, witness, checkpoint, witness.head(), limit=1)
            guarded = ArtifactReader(engine).read_json(canonical({"request_id": "consume-after-anchor",
                "asset": "nqc-source-manifest"}), engine.issue("local-consumer-check", "nqc-source-manifest"))
            if guarded["content_sha256"] != sha256(original):
                raise Rejected("nqc_guarded_consumer_check_failed")
            second_archive = archive.capture(engine, witness, engine.checkpoint(), witness.head(), limit=1)
            witnessed = second_archive["witness_receipt"]
            archived_pages = sum(archive.verify(item["manifest_sha256"], key, enrollment["policy_digest"])["pages"]
                                 for item in (first_archive, second_archive))
            evidence = {"status": "NQC_LOCAL_CONSUMER_CHECK_PASS",
                        "base_commit": baseline["base_commit"], "tested_parent_commit": baseline["head_commit"],
                        "artifact": artifact, "content_sha256": result["content_sha256"],
                        "size_bytes": result["size_bytes"], "manifest_files": len(result["data"]["files"]),
                        "decision": result["admission"]["decision"], "receipt_replayed": True,
                        "audit_export_verified": verified["verified"],
                        "authorized_snapshots": verified["authorized_snapshots"],
                        "paginated_audit_verified": page_result["verified"],
                        "audit_pages": page_result["pages"],
                        "witness_revision": witnessed["revision"],
                        "witness_checkpoint_sequence": witnessed["checkpoint"]["sequence"],
                        "second_read_enforced_anchored_prefix": True,
                        "local_archive_manifests": 2,
                        "stored_audit_pages_reread": archived_pages,
                        "archive_linked_to_witness": True,
                        "scope": "actual local manifest consumed; production Census loop unchanged"}
    finally:
        if marker is not None:
            if read_local(root, marker_path) != marker:
                raise Rejected("owned_canary_changed_during_cleanup")
            (root / marker_path).unlink()
    if read_local(root, artifact) != original:
        raise Rejected("nqc_source_changed")
    evidence["source_bytes_unchanged"] = True
    evidence["isolation_after_consumption"] = verify_nqc(root)["isolation"]["status"]
    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    print(json.dumps(run(parser.parse_args().repo), sort_keys=True, indent=2))
