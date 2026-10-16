import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import probe_environment as p


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def package(self, name="ethers", version="5.7.2", main="lib/index.js"):
        directory = self.root / "pkg"
        directory.mkdir(exist_ok=True)
        (directory / "package.json").write_text(json.dumps(
            {"name": name, "version": version, "main": main}))
        return directory

    def test_lock_resolves_grouped_selector(self):
        self.assertEqual(p.locked_version(
            'ethers@^5.5.3, ethers@^5.7.0:\n  version "5.7.2"\n',
            "ethers", "^5.7.0"), "5.7.2")

    def test_lock_resolves_scoped_selector(self):
        self.assertEqual(p.locked_version(
            '"@ethersproject/providers@^5.7.0":\n  version "5.7.2"\n',
            "@ethersproject/providers", "^5.7.0"), "5.7.2")

    def test_missing_or_duplicate_lock_fails(self):
        block = 'ethers@^5.7.0:\n  version "5.7.2"'
        for lock in ("", block + "\n\n" + block, 'ethers@^5.7.0:\n  integrity "x"'):
            with self.subTest(lock=lock), self.assertRaises(ValueError):
                p.locked_version(lock, "ethers", "^5.7.0")

    def test_absent_dependency(self):
        self.assertEqual(p.inspect_package(self.root / "absent", "ethers", "5.7.2")["status"], "ABSENT")

    def test_v6_cannot_replace_v5(self):
        item = p.inspect_package(self.package(version="6.0.0"), "ethers", "5.7.2")
        self.assertEqual(item["status"], "NAME_OR_VERSION_MISMATCH")

    def test_source_manifest_without_build_is_not_ready(self):
        item = p.inspect_package(self.package(), "ethers", "5.7.2")
        self.assertEqual(item["status"], "ENTRY_MISSING")

    def test_malformed_manifest_is_not_ready(self):
        directory = self.package()
        (directory / "package.json").write_text("[]")
        self.assertEqual(p.inspect_package(directory, "ethers", "5.7.2")["status"], "UNREADABLE_MANIFEST_OR_ENTRY")

    def test_entry_is_only_hashed_never_executed(self):
        directory = self.package()
        (directory / "lib").mkdir()
        (directory / "lib/index.js").write_text("throw new Error('must not run');")
        item = p.inspect_package(directory, "ethers", "5.7.2")
        self.assertEqual(item["status"], "NECESSARY_FILES_PRESENT")
        self.assertEqual(len(item["entry_sha256"]), 64)

    def test_entry_cannot_escape_package(self):
        directory = self.package(main="../external.js")
        (self.root / "external.js").write_text("not a package entry")
        self.assertEqual(p.inspect_package(directory, "ethers", "5.7.2")["status"], "ENTRY_OUTSIDE_PACKAGE")

    def test_cache_is_scoped_to_requested_name(self):
        (self.root / "npm-ethers-5.7.2-abc").mkdir()
        (self.root / "npm-unrelated-1.0.0").mkdir()
        items = p.candidates("ethers", [], [self.root])
        self.assertEqual(items, [self.root / "npm-ethers-5.7.2-abc/node_modules/ethers"])

    def test_wrong_checkout_never_becomes_evidence(self):
        with self.assertRaises(ValueError):
            p.inventory(self.root, [], [], "another-commit")

    def test_complete_inventory_is_never_admission(self):
        (self.root / "yarn.lock").write_text('ethers@^5.7.0:\n  version "5.7.2"\n')
        directory = self.root / "node_modules/ethers"
        directory.mkdir(parents=True)
        (directory / "package.json").write_text(json.dumps({"name": "ethers", "version": "5.7.2"}))
        (directory / "index.js").write_text("throw new Error('not executed');")
        with patch.object(p, "SOURCE_FILES", ("yarn.lock",)), patch.object(p, "WORKSPACES", ()), patch.object(p, "SELECTORS", {"ethers": "^5.7.0"}):
            report = p.inventory(self.root, [self.root / "node_modules"], [], p.PIN)
        self.assertEqual(report["status"], "REQUIRES_BUILD_AND_RUNTIME_VALIDATION")
        self.assertFalse(report["full_admission_proven"])
        self.assertFalse(report["bundler_executed"])


if __name__ == "__main__":
    unittest.main()
