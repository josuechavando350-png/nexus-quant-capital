import io
from pathlib import Path
import secrets
import subprocess
import sys
import unittest
import zipfile

from test_defense import Fixture
from nqc_defense.audit import GENESIS, mac
from nqc_defense.audit_pages import (AuditPageVerifier, MAX_ARCHIVE_BYTES, MAX_PAGE_BYTES,
                                    MAX_RECORDS, verify_page)
from nqc_defense.build import archive
from nqc_defense.codec import Rejected, canonical, decode
from nqc_defense.files import create_local
from nqc_defense.verify_export import verify as verify_export

ORIGIN = {"sequence": 0, "head": GENESIS}


def unpack(data):
    with zipfile.ZipFile(io.BytesIO(data)) as bundle:
        return decode(bundle.read("page.json"), max_bytes=MAX_PAGE_BYTES, max_nodes=8192)


def rewrite(data, change):
    with zipfile.ZipFile(io.BytesIO(data)) as bundle:
        entries = {name: bundle.read(name) for name in ("page.json", "policy.json", "policy.sha3")}
    page = decode(entries["page.json"], max_bytes=MAX_PAGE_BYTES, max_nodes=8192)
    change(page)
    entries["page.json"] = canonical(page)
    return archive(entries)


class AuditPageTests(Fixture):
    def populate(self, count=3):
        for i in range(count):
            self.engine.admit_bytes(canonical({"request_id": f"consume-{i}", "asset": "nqc-evidence"}), self.token())
        return self.engine.checkpoint()

    def pages(self, target, limit=2, max_bytes=MAX_PAGE_BYTES):
        start = dict(ORIGIN)
        while True:
            data = self.engine.export_page(start, target, limit, max_bytes)
            result = verify_page(data, self.key, self.digest, start, target)
            yield data
            if result["complete"]:
                break
            start = result["checkpoint"]

    def test_empty_ledger_requires_verified_genesis_page(self):
        verifier = AuditPageVerifier(self.key, self.digest, ORIGIN)
        with self.assertRaisesRegex(Rejected, "audit_pages_incomplete"):
            verifier.finish()
        verifier.accept(self.engine.export_page(ORIGIN, ORIGIN))
        result = verifier.finish()
        self.assertTrue(result["from_genesis"])
        self.assertEqual(result["record_count"], 0)

    def test_all_page_sizes_preserve_counts_and_final_checkpoint(self):
        target = self.populate()
        full = verify_export(self.engine.export(), self.key, self.digest, target)
        for limit in (1, 2, 3, 4, 8, 512):
            with self.subTest(limit=limit):
                verifier = AuditPageVerifier(self.key, self.digest, target)
                for data in self.pages(target, limit):
                    result = verifier.accept(data)
                    self.assertLessEqual(result["record_count"], limit)
                result = verifier.finish()
                self.assertEqual(result["record_count"], 9)
                self.assertEqual(result["checkpoint"], target)
                for field in ("replayed_decisions", "authorized_snapshots", "legacy_unreplayed_decisions"):
                    self.assertEqual(result[field], full[field])

    def test_snapshot_boundary_replays_preceding_decision_without_counting_it_twice(self):
        target = self.populate(1)
        pages = list(self.pages(target, 2))
        second = unpack(pages[1])
        self.assertEqual(decode(second["predecessor"]["payload"].encode())["kind"], "decision")
        result = verify_page(pages[1], self.key, self.digest, second["start"], target)
        self.assertEqual(result["authorized_snapshots"], 1)
        self.assertEqual(result["replayed_decisions"], 0)

    def test_new_events_do_not_move_pinned_target_or_change_page_bytes(self):
        target = self.populate(1)
        before = list(self.pages(target))
        self.send(request_id="after-target")
        self.assertGreater(self.engine.checkpoint()["sequence"], target["sequence"])
        self.assertEqual(list(self.pages(target)), before)

    def test_restart_resumes_from_verified_checkpoint(self):
        target = self.populate()
        first = self.engine.export_page(ORIGIN, target, 2)
        start = verify_page(first, self.key, self.digest, ORIGIN, target)["checkpoint"]
        self.engine = self.open()
        verifier = AuditPageVerifier(self.key, self.digest, target, start)
        while not verifier.complete:
            verifier.accept(self.engine.export_page(verifier.current, target, 2))
        self.assertFalse(verifier.finish()["from_genesis"])
        self.assertEqual(verifier.finish()["record_count"], 7)

    def test_missing_middle_page_rejected_without_advancing_verifier(self):
        target = self.populate()
        pages = list(self.pages(target, 2))
        verifier = AuditPageVerifier(self.key, self.digest, target)
        verifier.accept(pages[0])
        saved = dict(verifier.current)
        with self.assertRaisesRegex(Rejected, "audit_page_anchor_mismatch"):
            verifier.accept(pages[2])
        self.assertEqual(verifier.current, saved)
        for data in pages[1:]:
            verifier.accept(data)
        self.assertTrue(verifier.finish()["complete"])

    def test_repeated_page_rejected(self):
        target = self.populate()
        first = next(self.pages(target))
        verifier = AuditPageVerifier(self.key, self.digest, target)
        verifier.accept(first)
        with self.assertRaisesRegex(Rejected, "audit_page_anchor_mismatch"):
            verifier.accept(first)

    def test_missing_final_page_cannot_finish(self):
        target = self.populate()
        verifier = AuditPageVerifier(self.key, self.digest, target)
        for data in list(self.pages(target))[:-1]:
            verifier.accept(data)
        with self.assertRaisesRegex(Rejected, "audit_pages_incomplete"):
            verifier.finish()

    def test_appending_after_completion_rejected(self):
        target = self.populate(1)
        page = self.engine.export_page(ORIGIN, target)
        verifier = AuditPageVerifier(self.key, self.digest, target)
        verifier.accept(page)
        with self.assertRaisesRegex(Rejected, "audit_page_already_complete"):
            verifier.accept(page)

    def test_truncated_prefix_is_incomplete_even_with_rebuilt_end(self):
        target = self.populate(1)
        def truncate(page):
            page["records"].pop()
            row = page["records"][-1]
            page["end"] = {"sequence": row["sequence"], "head": row["mac"]}
        changed = rewrite(self.engine.export_page(ORIGIN, target), truncate)
        verifier = AuditPageVerifier(self.key, self.digest, target)
        self.assertFalse(verifier.accept(changed)["complete"])
        with self.assertRaisesRegex(Rejected, "audit_pages_incomplete"):
            verifier.finish()

    def test_wrong_key_or_policy_rejected(self):
        target = self.populate(1)
        data = self.engine.export_page(ORIGIN, target)
        for key, digest in ((secrets.token_bytes(32), self.digest), (self.key, "f" * 64)):
            with self.subTest(digest=digest), self.assertRaises(Rejected):
                verify_page(data, key, digest, ORIGIN, target)

    def test_rebuilt_archive_manifest_does_not_authenticate_changed_payload(self):
        target = self.populate(1)
        changed = rewrite(self.engine.export_page(ORIGIN, target),
                          lambda page: page["records"][0].update(payload='{"kind":"changed"}'))
        with self.assertRaisesRegex(Rejected, "audit_integrity"):
            verify_page(changed, self.key, self.digest, ORIGIN, target)

    def test_context_cannot_be_omitted_or_substituted(self):
        target = self.populate(1)
        second = list(self.pages(target, 2))[1]
        start = unpack(second)["start"]
        for predecessor in (None, unpack(list(self.pages(target, 1))[1])["predecessor"]):
            changed = rewrite(second, lambda page: page.update(predecessor=predecessor))
            with self.subTest(predecessor=predecessor), self.assertRaises(Rejected):
                verify_page(changed, self.key, self.digest, start, target)

    def test_context_receipt_semantics_checked_even_with_valid_hmac(self):
        target = self.populate(1)
        second = list(self.pages(target, 2))[1]
        anchors = {}
        def change(page):
            before, row = page["predecessor"], page["records"][0]
            event = decode(before["payload"].encode())
            event["receipt"]["outcome"]["decision"] = "denied"
            before["payload"] = canonical(event).decode()
            before["mac"] = mac(self.key, before["sequence"], before["previous"], before["payload"])
            page["start"]["head"] = before["mac"]
            row["previous"] = before["mac"]
            row["mac"] = mac(self.key, row["sequence"], row["previous"], row["payload"])
            page["end"]["head"] = row["mac"]
            page["target"]["head"] = row["mac"]
            anchors.update(start=page["start"], target=page["target"])
        changed = rewrite(second, change)
        with self.assertRaisesRegex(Rejected, "receipt_integrity"):
            verify_page(changed, self.key, self.digest, anchors["start"], anchors["target"])

    def test_record_gap_and_reordering_rejected(self):
        target = self.populate(1)
        original = self.engine.export_page(ORIGIN, target)
        for change in (lambda page: page["records"].pop(1), lambda page: page["records"].reverse()):
            with self.assertRaisesRegex(Rejected, "audit_sequence"):
                verify_page(rewrite(original, change), self.key, self.digest, ORIGIN, target)

    def test_end_and_target_are_pinned(self):
        target = self.populate(1)
        original = self.engine.export_page(ORIGIN, target)
        for field in ("start", "end", "target"):
            changed = rewrite(original, lambda page: page[field].update(head="f" * 64))
            with self.subTest(field=field), self.assertRaises(Rejected):
                verify_page(changed, self.key, self.digest, ORIGIN, target)

    def test_deleted_target_refuses_export(self):
        target = self.populate(1)
        with self.engine.state.transaction() as db:
            db.execute("DELETE FROM audit WHERE seq=?", (target["sequence"],))
        with self.assertRaisesRegex(Rejected, "audit_anchor_unavailable"):
            self.engine.export_page(ORIGIN, target)

    def test_corruption_outside_requested_page_refuses_export(self):
        target = self.populate()
        with self.engine.state.transaction() as db:
            db.execute("UPDATE audit SET payload='{}' WHERE seq=?", (target["sequence"],))
        with self.assertRaisesRegex(Rejected, "audit_integrity"):
            self.engine.export_page(ORIGIN, target, 1)

    def test_invalid_limits_and_anchors_rejected(self):
        target = self.populate(1)
        for limit, maximum in ((0, 1024), (513, 1024), (True, 1024), (1, 1023), (1, MAX_PAGE_BYTES + 1)):
            with self.subTest(limit=limit, maximum=maximum), self.assertRaises(Rejected):
                self.engine.export_page(ORIGIN, target, limit, maximum)
        for start in ({"sequence": True, "head": GENESIS}, {"sequence": 0, "head": "f" * 64},
                      {"sequence": 4, "head": "f" * 64}):
            with self.assertRaises(Rejected):
                self.engine.export_page(start, target)

    def test_byte_budget_bounds_every_exported_page(self):
        target = self.populate()
        pages = list(self.pages(target, 512, 4096))
        self.assertGreater(len(pages), 1)
        for data in pages:
            with zipfile.ZipFile(io.BytesIO(data)) as bundle:
                self.assertLessEqual(bundle.getinfo("page.json").file_size, 4096)

    def test_too_small_budget_fails_explicitly_instead_of_looping(self):
        target = self.populate(1)
        first = self.engine.export_page(ORIGIN, target, 1)
        start = verify_page(first, self.key, self.digest, ORIGIN, target)["checkpoint"]
        with self.assertRaisesRegex(Rejected, "audit_page_no_progress"):
            self.engine.export_page(start, target, 512, 1024)

    def test_wire_size_and_count_limits_reject_excess(self):
        target = self.populate(1)
        original = self.engine.export_page(ORIGIN, target)
        changed = rewrite(original, lambda page: page.update(records=[page["records"][0]] * (MAX_RECORDS + 1)))
        with self.assertRaisesRegex(Rejected, "audit_page_count"):
            verify_page(changed, self.key, self.digest, ORIGIN, target)
        with self.assertRaisesRegex(Rejected, "audit_page_size"):
            verify_page(b"x" * (MAX_ARCHIVE_BYTES + 1), self.key, self.digest, ORIGIN, target)

    def test_no_empty_page_can_claim_progress(self):
        target = self.populate(1)
        changed = rewrite(self.engine.export_page(ORIGIN, target),
                          lambda page: page.update(records=[], end=dict(ORIGIN)))
        with self.assertRaisesRegex(Rejected, "audit_page_no_progress"):
            verify_page(changed, self.key, self.digest, ORIGIN, target)

    def test_invalid_unicode_payload_is_rejected_not_an_uncaught_encoding_error(self):
        target = self.populate(1)
        changed = rewrite(self.engine.export_page(ORIGIN, target),
                          lambda page: page["records"][0].update(payload="\ud800"))
        with self.assertRaisesRegex(Rejected, "audit_payload"):
            verify_page(changed, self.key, self.digest, ORIGIN, target)

    def test_cli_exports_and_offline_cli_requires_every_page(self):
        target = self.populate(1)
        create_local(self.root, "ledger.key", self.key)
        create_local(self.root, "target.json", canonical(target))
        common = [sys.executable, "-B", "-m", "nqc_defense", "--assets", str(self.assets),
                  "--configs", str(self.store.root), "--state", str(self.root / "state"),
                  "--policy", self.digest, "--key-file", str(self.root / "ledger.key")]
        start = None
        files = []
        for i in range(3):
            output = self.root / f"page-{i}.zip"
            args = [*common, "export-page", str(output), "--target", str(self.root / "target.json"), "--limit", "1"]
            if start:
                create_local(self.root, f"start-{i}.json", canonical(start))
                args += ["--start", str(self.root / f"start-{i}.json")]
            result = subprocess.run(args, check=True, capture_output=True)
            start = decode(result.stdout)["checkpoint"]
            files.append(str(output))
        script = Path(__file__).resolve().parents[1] / "tools/verify_audit_pages.py"
        args = [sys.executable, "-B", str(script), "--key-file", str(self.root / "ledger.key"),
                "--policy-digest", self.digest, "--target", str(self.root / "target.json")]
        result = subprocess.run([*args, *files], check=True, capture_output=True)
        self.assertEqual(decode(result.stdout)["record_count"], 3)
        incomplete = subprocess.run([*args, *files[:-1]], capture_output=True)
        self.assertEqual(incomplete.returncode, 2)
        self.assertEqual(decode(incomplete.stdout)["reason"], "audit_pages_incomplete")
        # Export is create-only; existing page bytes cannot be silently replaced.
        repeat = subprocess.run(common + ["export-page", files[0], "--target", str(self.root / "target.json")],
                                capture_output=True)
        self.assertEqual(repeat.returncode, 2)


if __name__ == "__main__":
    unittest.main()
