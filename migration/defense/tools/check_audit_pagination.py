"""Exercise a large controlled local audit fixture through real SQLite and HMAC."""

import io
import json
from pathlib import Path
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nqc_defense.audit_pages import AuditPageVerifier
from nqc_defense.codec import Rejected, canonical
from nqc_defense.engine import Engine
from nqc_defense.enroll import enroll
from nqc_defense.files import read_local, sha256
from nqc_defense.verify_export import verify as verify_export


def run():
    source = Path(__file__).resolve().parents[1] / "nqc_defense/engine.py"
    source_bytes = source.read_bytes()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        assets = root / "assets"
        assets.mkdir()
        (assets / "engine.py").write_bytes(source_bytes)
        enrollment = enroll(assets, "engine.py", "pagination-source", "guard", root / "control")
        control = root / "control"
        key = read_local(control, "ledger.key", 32)
        digest = enrollment["policy_digest"]
        engine = Engine(assets, control / "configs", control / "state", digest, key)
        token = engine.issue("local-pagination-check", "pagination-source")
        _, snapshot = engine.admit_bytes(canonical({"request_id": "source-capture", "asset": "pagination-source"}), token)
        if snapshot != source_bytes:
            raise Rejected("pagination_capture_mismatch")
        # Explicit synthetic load markers, never presented as real incidents or decisions.
        # The production append path and real SQLite transaction store every record.
        with engine.state.transaction() as db:
            for i in range(10000):
                engine.ledger.append(db, {"kind": "local_validation_marker", "fixture_index": i,
                                          "source_sha256": sha256(source_bytes)})
        target = engine.checkpoint()
        try:
            verify_export(engine.export(), key, digest, target)
        except Rejected as exc:
            if str(exc) != "audit_export_count":
                raise
            full_export_limit = str(exc)
        else:
            raise RuntimeError("single-export limit was not exercised")
        verifier = AuditPageVerifier(key, digest, target)
        peak_archive = peak_page = 0
        while not verifier.complete:
            data = engine.export_page(verifier.current, target, limit=512, max_bytes=256 * 1024)
            if verifier.pages == 1:
                # Append after fixing target; the traversal must still stop at the earlier head.
                engine.issue("later-local-event", "pagination-source")
            verifier.accept(data)
            peak_archive = max(peak_archive, len(data))
            with zipfile.ZipFile(io.BytesIO(data)) as bundle:
                peak_page = max(peak_page, bundle.getinfo("page.json").file_size)
        result = verifier.finish()
        if (result["record_count"] != 10003 or result["replayed_decisions"] != 1
                or result["authorized_snapshots"] != 1 or result["checkpoint"] != target
                or engine.checkpoint()["sequence"] != 10004):
            raise Rejected("pagination_acceptance_failed")
        return {"status": "LOCAL_PAGINATION_ACCEPTANCE_PASS", "source_sha256": sha256(source_bytes),
                "real_admission_records": 3, "synthetic_load_markers": 10000,
                "single_export_rejection": full_export_limit, "records_verified": result["record_count"],
                "pages_verified": result["pages"], "replayed_decisions": result["replayed_decisions"],
                "authorized_snapshots": result["authorized_snapshots"],
                "maximum_page_json_bytes": peak_page, "maximum_archive_bytes": peak_archive,
                "pinned_target_sequence": target["sequence"], "current_sequence": 10004,
                "later_event_excluded_from_fixed_target": True,
                "scope": "controlled local stress fixture; no production traffic or throughput benchmark"}


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True, indent=2))
