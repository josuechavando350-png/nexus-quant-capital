"""End-to-end OFFLINE evidence test using real SuperHunter importers and verifiers.

The Slither-compatible JSON reports below are SYNTHETIC FORMAT FIXTURES.
No Slither or Solidity compiler executes; no bounty, scanning or native proof.
Unlike test_slither_pair_replay, these tests do NOT mock the importers,
Slither triple-control verifier, pair comparator, or native audit-chain loader.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import time
import unittest

from superhunter import slither_owned_runner as owned
from superhunter import slither_control_pair as pair
from superhunter import slither_pair_replay as replay
from superhunter import static_review
from superhunter.safe_io import canonical, strict_json

COMMIT = "a" * 40
MODES = ("positive", "clean", "comparison")
SOURCES = {
    "positive": owned.OWNED_SOURCE,
    "clean": pair.CLEAN_SOURCE,
    "comparison": pair.COMPARISON_SOURCE,
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def synthetic_slither_report(mode: str) -> bytes:
    """Minimal documented Slither JSON shape, NEVER a real scanner result."""
    if mode not in MODES:
        raise ValueError("UNSUPPORTED_SYNTHETIC_CASE")
    findings = []
    if mode == "positive":
        source = SOURCES[mode]
        needle = b'require(tx.origin == owner, "owner");'
        start = source.index(needle)
        findings = [{
            "check": "tx-origin", "impact": "Medium", "confidence": "Medium",
            "description": "SYNTHETIC SLITHER FORMAT TEST — never a scanner execution",
            "elements": [{
                "type": "node", "name": "synthetic positive conditional",
                "source_mapping": {
                    "filename_relative": "Owned.sol",
                    "start": start,
                    "length": len(needle),
                    "lines": [source[:start].count(b"\n") + 1],
                },
            }],
        }]
    return canonical({"success": True, "error": None, "results": {"detectors": findings}})


def synthetic_context(mode: str, report: bytes) -> dict:
    if mode not in MODES:
        raise ValueError("UNSUPPORTED_SYNTHETIC_CASE")
    return {
        "schema_version": 1,
        "scope_id": "owned-fixed-local-fixture" if mode == "positive"
                    else "owned-fixed-local-fixture-" + mode,
        "repository": {"repo": "superhunter-owned/fixture", "commit": COMMIT},
        "tool": {"name": "slither", "version": owned.SCANNER_VERSION},
        "detectors": [owned.DETECTOR], "report_sha256": sha(report),
        "sources": {"Owned.sol": sha(SOURCES[mode])},
        # Intentionally model a forged 'external-report' declaration. This
        # controlled test demonstrates that hash-consistent scanner metadata
        # is NOT authenticated proof that an external scanner ran.
        "input_kind": "external-report",
    }


class SlitherOfflineEndToEndTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="sh-slither-e2e-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def _import(self, dest: Path, mode: str, *, invalid_offset: bool = False) -> dict:
        work = self.root / ("input-" + dest.parent.name + "-" + mode)
        work.mkdir(mode=0o700)
        source = SOURCES[mode]
        report = synthetic_slither_report(mode)
        if invalid_offset:
            row = strict_json(report)
            row["results"]["detectors"][0]["elements"][0]["source_mapping"]["start"] = len(source) + 1
            report = canonical(row)
        context = synthetic_context(mode, report)
        (work / "Owned.sol").write_bytes(source)
        (work / "report.json").write_bytes(report)
        (work / "context.json").write_bytes(canonical(context))
        return static_review.import_report(work / "report.json", work / "context.json",
                                           work, dest)

    def _bundle(self, name: str) -> Path:
        root = self.root / name
        root.mkdir(mode=0o700)
        for mode in MODES:
            result = self._import(root / mode, mode)
            self.assertTrue(result["normalization_complete"])
            self.assertFalse(result["scanner_execution_verified"])
            pair.accept(result, mode == "positive", expected_source=SOURCES[mode])
        # The fixture deliberately supplies the same untrusted producer assertion
        # that the real runner would make. pair.verify_pair accepts the assertion,
        # but replay MUST NOT treat that as native execution authentication.
        summary = {
            "schema_version": 1, "status": "OWNED_SLITHER_PAIR_UNVERIFIED",
            "positive_sha256": sha(SOURCES["positive"]),
            "clean_sha256": sha(SOURCES["clean"]),
            "comparison_sha256": sha(SOURCES["comparison"]),
            "scanner": "slither", "scanner_version": owned.SCANNER_VERSION,
            "detector": owned.DETECTOR,
            "positive_count": 1, "clean_count": 0, "comparison_count": 0,
            "declared_commit": COMMIT, "scanner_executed_in_local_worker": True,
            "network_isolation_proven": False, "independent_execution_replay": False,
            "vulnerability_confirmed": False,
        }
        (root / "summary.json").write_bytes(canonical(summary))
        marker = {"schema_version": 1, "sha256": {
            "summary.json": sha((root / "summary.json").read_bytes()),
            **{mode + "/COMPLETE.json": sha((root / mode / "COMPLETE.json").read_bytes())
               for mode in MODES},
        }}
        (root / "COMPLETE.json").write_bytes(canonical(marker))
        self.assertEqual(pair.verify_pair(root), summary)
        return root

    def test_real_offline_import_verification_and_six_report_comparison(self):
        original = self._bundle("original")
        # Audit entries use microsecond UTC times; ensure the two anchor bytes
        # differ, without modifying the semantically equivalent source reports.
        time.sleep(0.005)
        repeated = self._bundle("repeated")
        first = sha((original / "COMPLETE.json").read_bytes())
        second = sha((repeated / "COMPLETE.json").read_bytes())
        self.assertNotEqual(first, second, "same markers do not prove a second observation")
        result = replay.create(original, repeated, first, second,
                               self.root / "comparison-result")
        self.assertEqual(result["status"],
                         "TWO_SLITHER_THREE_CONTROL_RUNS_AGREE_UNAUTHENTICATED")
        self.assertEqual(result["control_reports_reevaluated"], 6)
        self.assertFalse(result["scanner_executed_here"])
        self.assertFalse(result["producer_authenticated"])
        self.assertFalse(result["independent_execution_proven"])
        self.assertFalse(result["vulnerability_confirmed"])
        self.assertEqual(
            replay.verify(self.root / "comparison-result", original, repeated,
                          first, second), result)

    def test_real_importer_rejects_wrong_source_offsets_before_bundle(self):
        out = self.root / "bad-report"
        with self.assertRaisesRegex(ValueError, "LOCATION_BYTE_RANGE"):
            self._import(out, "positive", invalid_offset=True)
        self.assertFalse(out.exists())

    def test_real_verifier_rejects_altered_original_source_even_if_content_resealed(self):
        original = self._bundle("original")
        positive_dir = original / "positive"
        context = strict_json((positive_dir / "context.json").read_bytes())
        original_filename = "source-" + context["sources"]["Owned.sol"] + ".txt"
        source = positive_dir / original_filename
        source.write_bytes(b"modified synthetic fixture")
        manifest_path = positive_dir / "COMPLETE.json"
        manifest = strict_json(manifest_path.read_bytes())
        manifest["sha256"][original_filename] = sha(source.read_bytes())
        manifest_path.write_bytes(canonical(manifest))
        with self.assertRaisesRegex(ValueError, "SOURCE_CONTENT_MISMATCH|PAIR_HASHES"):
            pair.verify_pair(original)

    def test_synthetic_report_is_never_claimed_as_native_scanner_proof(self):
        original = self._bundle("original")
        evidence = static_review.verify_report(original / "positive")
        self.assertEqual(evidence["input_kind"], "external-report")
        # A synthetically forged declaration must never promote either flag.
        self.assertFalse(evidence["repository_commit_verified"])
        self.assertFalse(evidence["scanner_execution_verified"])
        self.assertFalse(evidence["producer_authenticated"])
        self.assertFalse(evidence["vulnerability_confirmed"])


if __name__ == "__main__":
    unittest.main()
