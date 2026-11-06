"""Exercise the complete local lifecycle against a copy of actual package source bytes."""

import hashlib
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nqc_defense.build import verify_archive
from nqc_defense.codec import Rejected, canonical
from nqc_defense.engine import Engine
from nqc_defense.enroll import enroll
from nqc_defense.files import read_local
from nqc_defense.verify_export import verify as verify_export


def run():
    source = Path(__file__).resolve().parents[1] / "nqc_defense/engine.py"
    source_bytes = source.read_bytes()
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        assets = root / "assets"
        assets.mkdir()
        (assets / "engine.py").write_bytes(source_bytes)
        receipt = enroll(assets, "engine.py", "nqc-defense-engine", "guard", root / "control")
        control = root / "control"
        key = read_local(control, "ledger.key", 32)
        engine = Engine(assets, control / "configs", control / "state", receipt["policy_digest"], key)
        def inspect(request_id):
            token = engine.issue("local-acceptance", "nqc-defense-engine")
            return engine.process(canonical({"request_id": request_id, "asset": "nqc-defense-engine"}), token)
        initial = inspect("original")
        (assets / "engine.py").write_bytes(source_bytes + b"\n# controlled local integrity test\n")
        changed = inspect("modified")
        blocked_release = False
        try:
            engine.release("nqc-defense-engine")
        except Rejected:
            blocked_release = True
        (assets / "engine.py").write_bytes(source_bytes)
        released = engine.release("nqc-defense-engine")
        restored = inspect("restored")
        checkpoint = engine.checkpoint()
        reopened = Engine(assets, control / "configs", control / "state", receipt["policy_digest"], key, checkpoint=checkpoint)
        first, second = engine.export(), reopened.export()
        verified = verify_archive(first)
        audit_verification = verify_export(first, key, receipt["policy_digest"], checkpoint)
        expected = (initial["decision"], changed["decision"], blocked_release, released, restored["decision"], first == second)
        if expected != ("admit", "quarantined", True, True, "admit", True):
            raise RuntimeError("local acceptance lifecycle failed")
        return {"status": "LOCAL_ACCEPTANCE_PASS", "source_file": "nqc_defense/engine.py",
                "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
                "initial": initial["decision"], "changed": changed["decision"],
                "premature_release_blocked": blocked_release, "restored": restored["decision"],
                "restart_checkpoint_verified": True, "identical_exports": first == second,
                "export_members": sorted(verified), "audit_entries": checkpoint["sequence"],
                "authenticated_export_verified": audit_verification["verified"],
                "replayed_decisions": audit_verification["replayed_decisions"],
                "scope": "temporary local copies; no production enforcement or hardware validation"}


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
