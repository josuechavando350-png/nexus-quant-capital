#!/usr/bin/env python3
"""Adversarial integration tests against the real externally acquired D06 ZIP.

Requires --archive and --metadata-dir. Missing real input is an error, never a
silent skipped test or a synthetic replacement.
"""
import argparse
import copy
import datetime as dt
from pathlib import Path
import unittest

import verify_d06_readback as v


class ReadbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = ARGS.archive.read_bytes()
        cls.snapshots = {k: (ARGS.metadata_dir / (k + ".json")).read_bytes()
                         for k in ("run", "artifact", "jobs", "commit")}
        cls.docs = {k: v.SOURCE.strict_json(raw, k) for k, raw in cls.snapshots.items()}
        cls.members, cls.index = v.inventory(cls.raw)

    def meta(self, docs):
        return v.metadata(*(docs[k] for k in ("run", "artifact", "jobs", "commit")),
                          now=dt.datetime.now(dt.timezone.utc))

    def test_real_artifact_and_final_metadata(self):
        result = v.verify(self.raw, self.snapshots)
        self.assertEqual(result["verified"]["new_indexed_members"], 4327)
        self.assertEqual(result["verified"]["source_indexed_members"], 4234)
        self.assertFalse(result["canonical_recertification"])
        self.assertFalse(result["downstream_acceptance"])

    def test_wrong_producer_repository_tree_attempt_status_and_timing(self):
        changes = [("run", "head_sha", "a" * 40), ("run", "run_attempt", 2),
                   ("run", "run_attempt", True), ("run", "conclusion", "failure"),
                   ("run", "status", "in_progress"), ("run", "event", "pull_request"),
                   ("run", "head_branch", "main"), ("run", "updated_at", "2026-10-09T06:22:00Z"),
                   ("artifact", "expired", True), ("artifact", "digest", "sha256:" + "b" * 64),
                   ("artifact", "id", 1), ("artifact", "size_in_bytes", 12)]
        for doc, key, value in changes:
            with self.subTest(doc=doc, key=key):
                docs = copy.deepcopy(self.docs)
                docs[doc][key] = value
                with self.assertRaises(v.SOURCE.SourceError):
                    self.meta(docs)
        for key in ("repository", "head_repository"):
            docs = copy.deepcopy(self.docs)
            docs["run"][key]["id"] = 1333360261
            with self.assertRaises(v.SOURCE.SourceError):
                self.meta(docs)
        docs = copy.deepcopy(self.docs)
        docs["commit"]["commit"]["tree"]["sha"] = "b" * 40
        with self.assertRaises(v.SOURCE.SourceError):
            self.meta(docs)

    def test_skipped_steps_and_cross_run_job_rejected(self):
        for key, value in (("run_id", 1), ("head_sha", "a" * 40), ("run_attempt", 2)):
            docs = copy.deepcopy(self.docs)
            docs["jobs"]["jobs"][0][key] = value
            with self.assertRaises(v.SOURCE.SourceError):
                self.meta(docs)
        docs = copy.deepcopy(self.docs)
        docs["jobs"]["jobs"][0]["steps"][9]["conclusion"] = "skipped"
        with self.assertRaises(v.SOURCE.SourceError):
            self.meta(docs)

    def test_archive_truncation_and_same_length_mutation_rejected(self):
        for raw in (self.raw[:-1], self.raw[:1000] + bytes([self.raw[1000] ^ 1]) + self.raw[1001:]):
            with self.assertRaises(v.SOURCE.SourceError):
                v.inventory(raw)

    def test_duplicate_json_metadata_rejected(self):
        bad = dict(self.snapshots, run=b'{"id":1,"id":2}')
        with self.assertRaises(v.SOURCE.SourceError):
            v.verify(self.raw, bad)

    def test_independent_output_equality_detects_replay_disagreement(self):
        for name in ("current-rerun.json", "closeout-rerun/closeout-report.json"):
            members = dict(self.members)
            members[name] += b" "
            with self.assertRaises(v.SOURCE.SourceError):
                v.semantics(members, self.index, self.docs["run"])

    def test_original_store_mutation_detected(self):
        members = dict(self.members)
        name = next(n for n in members if n.startswith("store/objects/artifacts/"))
        members[name] += b"0"
        with self.assertRaises(v.SOURCE.SourceError):
            v.semantics(members, self.index, self.docs["run"])

    def test_failed_negative_case_and_self_certification_rejected(self):
        members = dict(self.members)
        data = v.SOURCE.strict_json(members["negative-tests/results.json"], "negatives")
        data["cases"][0]["rejected"] = False
        members["negative-tests/results.json"] = v.json.dumps(data).encode()
        with self.assertRaises(v.SOURCE.SourceError):
            v.semantics(members, self.index, self.docs["run"])
        idx = dict(self.index, canonical_recertification=True)
        with self.assertRaises(v.SOURCE.SourceError):
            v.semantics(self.members, idx, self.docs["run"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--metadata-dir", required=True, type=Path)
    ARGS = parser.parse_args()
    unittest.main(argv=[__file__])
