"""Subprocess tests of the authentic bridge; no mocked historical validator."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
EXPERIMENTS = REPO / "migration/experiments"
PARENT = json.loads((EXPERIMENTS / "nqc-037-historical-state/inputs/parent-header.json").read_text())
CHAIN = {"jsonrpc": "2.0", "id": 1, "result": "0x1237"}


def run(raw=None, root=REPO, check=False):
    args = [sys.executable, "-I", str(HERE / "worker.py"), "--repo-root", str(root)]
    if check:
        args.append("--check")
    result = subprocess.run(args, input=raw, capture_output=True, timeout=20)
    if result.stderr:
        raise AssertionError("Unexpected worker diagnostics")
    return result.returncode, json.loads(result.stdout)


def payload(responses):
    return json.dumps({"responses": responses}, separators=(",", ":")).encode()


class WorkerTests(unittest.TestCase):
    def test_complete_original_sources_and_exact_dependencies(self):
        code, r = run(check=True)
        self.assertEqual(code, 0)
        self.assertEqual(r["manifest_files_verified"], 42)
        self.assertTrue(r["complete_original_modules_loaded"])
        self.assertEqual(r["dependency_versions"]["trie"], "4.0.0")
        self.assertFalse(r["live_enabled"])

    def test_valid_prefix_and_byte_binding(self):
        parent = {**PARENT, "id": 2}  # Artificial envelope; no provider claim.
        raw = payload([CHAIN, parent])
        code, r = run(raw)
        self.assertEqual(code, 0)
        self.assertEqual(r["responses_validated"], 2)
        self.assertEqual(r["input_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertFalse(r["gates"]["commercial_admission"])
        self.assertEqual(r["gates"]["authenticated_pretransaction_priority_slots"], 0)

    def test_original_id_six_not_relabelled_in_real_input(self):
        code, r = run(payload([CHAIN, PARENT]))
        self.assertEqual(code, 2)
        self.assertEqual(r["responses_validated"], 1)
        self.assertEqual(r["failed_purpose"], "parent")

    def test_parent_mutation_rejected_by_complete_original(self):
        parent = copy.deepcopy(PARENT)
        parent["id"] = 2
        parent["result"]["stateRoot"] = "0x" + "00" * 32
        code, r = run(payload([CHAIN, parent]))
        self.assertEqual((code, r["responses_validated"]), (2, 1))

    def test_prior_fake_chain_rejected(self):
        code, r = run(payload([{**CHAIN, "result": "SIM_ACCEPTED_1"}]))
        self.assertEqual((code, r["responses_validated"]), (2, 0))

    def test_no_input_can_supply_state_or_replace_verifier(self):
        for extra in ("state", "validate_step", "commercial_admission"):
            with self.subTest(extra=extra):
                raw = json.dumps({"responses": [CHAIN], extra: {}}).encode()
                self.assertEqual(run(raw)[0], 2)

    def test_ambiguous_json_and_nonfinite_rejected(self):
        for raw in (b'{"responses":[],"responses":[]}', b'{"responses":[NaN]}', b'[]'):
            with self.subTest(raw=raw):
                self.assertEqual(run(raw)[0], 2)

    def test_boolean_id_error_envelope_and_wrong_chain(self):
        for response in ({**CHAIN, "id": True}, {**CHAIN, "result": "0x1"},
                         {**CHAIN, "error": {"message": "DO_NOT_ECHO_UNTRUSTED_TEXT"}}):
            with self.subTest(response=response):
                code, r = run(payload([response]))
                self.assertEqual(code, 2)
                self.assertNotIn("DO_NOT_ECHO_UNTRUSTED_TEXT", json.dumps(r))

    def test_ninth_and_empty_prefix_rejected(self):
        for responses in ([], [CHAIN] * 9):
            self.assertEqual(run(payload(responses))[0], 2)

    def test_missing_checkout_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            code, r = run(payload([CHAIN]), Path(temporary))
            self.assertEqual(code, 2)
            self.assertEqual(r["status"], "BLOCKED_SOURCE_OR_DEPENDENCY")

    def test_validation_boundary_denies_sockets_and_child_processes(self):
        script = '''
import importlib.util, pathlib, socket, subprocess, sys
spec = importlib.util.spec_from_file_location("worker", sys.argv[1])
w = importlib.util.module_from_spec(spec); spec.loader.exec_module(w)
sys.addaudithook(w.reject_network)
w.load_original(pathlib.Path(sys.argv[2]))
sys.addaudithook(w.reject_process)
for operation in (lambda: socket.socket(), lambda: subprocess.run(["true"])):
    try: operation()
    except w.Blocked: pass
    else: raise AssertionError("Offline boundary was bypassed")
print("OFFLINE_BOUNDARY_PASS")
'''
        p = subprocess.run([sys.executable, "-I", "-c", script,
                            str(HERE / "worker.py"), str(REPO)], capture_output=True, timeout=20)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(p.stdout, b"OFFLINE_BOUNDARY_PASS\n")

    def test_modified_original_refused_before_import(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "migration/experiments/nqc-037-historical-state"
            shutil.copytree(EXPERIMENTS / "nqc-037-historical-state", target)
            path = target / "src/verify.py"
            path.write_bytes(path.read_bytes() + b'\nraise RuntimeError("NEVER_EXECUTE")\n')
            code, r = run(payload([CHAIN]), root)
            self.assertEqual(code, 2)
            self.assertNotIn("complete_original_modules_loaded", r)


if __name__ == "__main__":
    unittest.main()
