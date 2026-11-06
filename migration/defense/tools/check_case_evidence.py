"""Preserve a native-format fixture's triggering bytes across rotation and verify offline."""
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nqc_defense.auth_log import AuthLogMonitor
from nqc_defense.case_evidence import capture_case, describe_case, verify_bundle
from nqc_defense.codec import Rejected
from nqc_defense.files import sha256
from nqc_defense.operations import OperationsStore


def run():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        def line(second):
            return (f"2026-11-06T12:00:0{second}Z node-a sshd[351]: Failed password for analyst "
                    "from 192.0.2.40 port 43000 ssh2\n").encode()
        log = root / "auth.log"
        unrelated = b"2026-11-06T11:59:59Z node-a sshd[351]: unrelated private fixture detail\n"
        log.write_bytes(unrelated + line(0) + line(1))
        store = OperationsStore.create(root / "operations")
        monitor = AuthLogMonitor.register(store, "ssh", "evaluation", "host", root, log.name, 3, 60,
                                          format_name="openssh-syslog-rfc3339", expected_host="node-a")
        monitor.poll(); log.rename(root / "auth.old"); log.write_bytes(line(2))
        monitor.rotate("auth.old"); monitor.poll()
        case = store.cases("evaluation", "host")[0]
        info = describe_case(store, "evaluation", "host", case["case_id"])
        if info["config_digest"] != monitor.digest:
            raise AssertionError("registration pin changed")
        paths = [{"generation": 0, "name": "auth.old"}, {"generation": 1, "name": "auth.log"}]
        before = {name: (root / name).read_bytes() for name in ("auth.old", "auth.log")}
        output = root / "evidence.json"
        receipt = capture_case(store, "evaluation", "host", case["case_id"], info["case_digest"], monitor.digest, paths, output)
        if any((root / name).read_bytes() != content for name, content in before.items()):
            raise AssertionError("capture changed source")
        bundle = output.read_bytes()
        # Attempting to acquire changed bytes must not produce a second complete bundle.
        log.write_bytes(line(2).replace(b"analyst", b"changed"))
        try:
            capture_case(store, "evaluation", "host", case["case_id"], info["case_digest"], monitor.digest, paths, root / "bad.json")
        except Rejected as exc:
            changed_rejection = str(exc)
        else:
            raise AssertionError("changed record was acquired")
        if (root / "bad.json").exists():
            raise AssertionError("failed acquisition published a bundle")
        log.unlink(); (root / "auth.old").unlink(); store.path.unlink()
        verified = verify_bundle(bundle, receipt["bundle_digest"], "evaluation", "host", case["case_id"], info["case_digest"], monitor.digest)
        try:
            verify_bundle(bundle + b" ", receipt["bundle_digest"], "evaluation", "host", case["case_id"], info["case_digest"], monitor.digest)
        except Rejected as exc:
            tamper_rejection = str(exc)
        else:
            raise AssertionError("modified bundle accepted")
        return {"verified": True, "fixture_origin": "authored OpenSSH-format messages in real temporary files; not a live server capture",
                "source_unchanged_by_capture": True, "source_generations": 2,
                "offline_verification_after_source_and_database_removal": verified,
                "changed_source_rejected": changed_rejection, "altered_bundle_rejected": tamper_rejection,
                "bundle_bytes": len(bundle), "bundle_digest": sha256(bundle),
                "stored_and_reread": receipt["stored_and_reread"], "production_activated": False}


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
