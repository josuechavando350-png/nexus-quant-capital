"""Inspect actual pinned NQC artifacts locally without activating a production consumer."""

import argparse
import json
from pathlib import Path
import secrets
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nqc_defense.codec import Rejected, canonical
from nqc_defense.engine import Engine
from nqc_defense.enroll import enroll
from nqc_defense.files import read_local, sha256
from nqc_defense.integration import verify_nqc
from nqc_defense.verify_export import verify as verify_export


def run(root):
    root = root.absolute()
    baseline = verify_nqc(root)
    # All pre-existing source bytes are read-only; the only repository write is this new owned canary.
    artifact = "nqc-census/Cargo.toml"
    before = read_local(root, artifact)
    marker_path = "migration/defense-check-" + secrets.token_hex(16) + ".canary"
    created_marker = None
    try:
        with tempfile.TemporaryDirectory() as directory:
            control = Path(directory) / "control"
            enrollment = enroll(root, artifact, "nqc-census-manifest", marker_path, control)
            created_marker = read_local(root, marker_path)
            key = read_local(control, "ledger.key", 32)
            engine = Engine(root, control / "configs", control / "state", enrollment["policy_digest"], key)
            token = engine.issue("local-integration-check", "nqc-census-manifest")
            result = engine.process(canonical({"request_id": "nqc-artifact-check", "asset": "nqc-census-manifest"}), token)
            receipt = engine.receipt(result["receipt_sha256"])
            verified = verify_export(engine.export(), key, enrollment["policy_digest"], engine.checkpoint())
            if result["decision"] != "admit" or before != read_local(root, artifact):
                raise Rejected("nqc_artifact_check_failed")
            return {"status": "NQC_LOCAL_ARTIFACT_CHECK_PASS", "base_commit": baseline["base_commit"],
                    "artifact": artifact, "artifact_sha256": sha256(before),
                    "decision": result["decision"], "receipt_replayed": receipt["outcome"]["decision"] == "admit",
                    "audit_export_verified": verified["verified"], "source_bytes_unchanged": True,
                    "scope": "actual local NQC artifact; no mandatory production admission hook installed"}
    finally:
        if created_marker is not None:
            # Delete only the exact new marker we own, never a changed or pre-existing file.
            if read_local(root, marker_path) != created_marker:
                raise Rejected("owned_canary_changed_during_cleanup")
            (root / marker_path).unlink()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    print(json.dumps(run(parser.parse_args().repo), sort_keys=True, indent=2))
