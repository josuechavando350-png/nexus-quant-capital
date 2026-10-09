#!/usr/bin/env python3
"""Actual replay/API identity negative cases; no synthetic archive substitutes."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import verify_terminal_recovery as recovery


class RecoveryTests(unittest.TestCase):
    def test_actual_api_identities(self):
        for stage in ("d11", "d12"):
            recovery.api(stage, ARGS.metadata)

    def test_actual_rust_replay_parity(self):
        report = recovery.replay_parity(ARGS.d12, ARGS.replay)
        self.assertEqual(len(report["exact_byte_parity"]), 2)
        self.assertTrue(report["portfolio_claims_resources_conflicts_equal"])
        self.assertFalse(report["new_producer_certified"])

    def test_false_api_commit_run_repository_or_tree_rejected(self):
        for file, field in (("artifact", "digest"), ("run", "head_sha"), ("run", "id"), ("commit", "sha")):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                for k in ("artifact", "run", "commit"):
                    shutil.copyfile(ARGS.metadata / ("d11-" + k + ".json"), root / ("d11-" + k + ".json"))
                p = root / ("d11-" + file + ".json")
                value = json.loads(p.read_bytes())
                value[field] = "wrong"
                p.write_text(json.dumps(value))
                with self.subTest(file=file, field=field), self.assertRaises(ValueError):
                    recovery.api("d11", root)

    def test_replay_missing_candidate_or_altered_promotion_rejected(self):
        for name in ("actionability-records.jsonl", "capital-promotions.jsonl"):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                shutil.copytree(ARGS.replay, root / "replay")
                p = root / "replay" / name
                p.write_bytes(b"\n".join(p.read_bytes().splitlines()[1:]) + b"\n")
                with self.subTest(file=name), self.assertRaises(ValueError):
                    recovery.replay_parity(ARGS.d12, root / "replay")

    def test_resource_changes_cannot_hide_in_provenance_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "replay"
            shutil.copytree(ARGS.replay, root)
            p = root / "portfolio-capacity.json"
            value = json.loads(p.read_bytes())
            value["shared_resource_count"] += 1
            p.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "mismatch inventory"):
                recovery.replay_parity(ARGS.d12, root)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("d12", "metadata", "replay"):
        p.add_argument("--" + arg, type=Path, required=True)
    ARGS = p.parse_args()
    unittest.main(argv=[__file__], verbosity=2)
