#!/usr/bin/env python3
"""Adversarial checks requiring the real historical archives and API snapshots."""
import argparse
import json
from pathlib import Path
import tempfile
import unittest

import verify_historical_inputs as v


class HistoricalInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pins = v.parse(v.PINS.read_bytes())
        cls.snapshots = {s: {k: (ARGS.metadata_root / s / (k + ".json")).read_bytes()
                             for k in ("run", "artifact", "commit")} for s in v.KEYS}

    def test_real_archives_and_cross_stage_coherence(self):
        r = v.verify(ARGS.archive_root, ARGS.metadata_root)
        self.assertEqual(len(r["stages"]), 5)
        self.assertEqual(r["observation_anchor"]["block_number"], 26095351)
        self.assertFalse(r["upstream_authority_lock_issued"])
        self.assertFalse(r["real_market_census_closed"])
        self.assertEqual(r["d08_summary"]["token_admission"]["execution_proven_compatible"], 0)

    def test_changed_origin_identity_success_and_artifact_rejected(self):
        for s in v.KEYS:
            for kind, path, value in [
                ("run", ["id"], 1), ("run", ["conclusion"], "failure"),
                ("run", ["repository", "id"], 1411047452),
                ("artifact", ["workflow_run", "id"], 1),
                ("artifact", ["expired"], 0), ("artifact", ["expired"], True),
                ("artifact", ["digest"], "sha256:" + "a" * 64),
                ("commit", ["commit", "tree", "sha"], "a" * 40),
            ]:
                with self.subTest(stage=s, kind=kind, path=path):
                    raw = dict(self.snapshots[s])
                    doc = v.parse(raw[kind])
                    at = doc
                    for part in path[:-1]:
                        at = at[part]
                    at[path[-1]] = value
                    raw[kind] = json.dumps(doc).encode()
                    with self.assertRaises(ValueError):
                        v.transport(self.pins[s], raw, self.pins["repository"])

    def test_duplicate_keys_and_nonfinite_numbers_rejected(self):
        for raw in (b'{"id":1,"id":2}', b'{"a":NaN}', b'{"a":Infinity}'):
            with self.assertRaises(ValueError):
                v.parse(raw)

    def test_unsafe_archive_paths_rejected(self):
        for path in ("../x", "/x", "a/../x", "a//x", "a/./x", "a\\x", "a\x00b", "", "."):
            with self.assertRaises(ValueError):
                v.safe(path)

    def test_same_length_archive_tampering_rejected(self):
        s = "d06"
        art, tree, _ = v.transport(self.pins[s], self.snapshots[s], self.pins["repository"])
        raw = bytearray((ARGS.archive_root / (s + "-original.zip")).read_bytes())
        raw[100] ^= 1
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "corrupt.zip"
            p.write_bytes(raw)
            with self.assertRaises(ValueError):
                v.archive(p, self.pins[s], art, tree)

    def test_cross_stage_substitution_rejected(self):
        for s in v.KEYS[:-1]:
            with self.assertRaises(ValueError):
                v.transport(self.pins[s], self.snapshots["d10"], self.pins["repository"])


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive-root", type=Path, required=True)
    p.add_argument("--metadata-root", type=Path, required=True)
    ARGS = p.parse_args()
    unittest.main(argv=[__file__])
