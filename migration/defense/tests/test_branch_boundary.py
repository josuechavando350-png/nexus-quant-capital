import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from nqc_defense.codec import Rejected
from nqc_defense.integration import BASE_COMMIT, verify_nqc


class BranchBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        source = Path(__file__).resolve().parents[3]
        self.env = {**os.environ, "GIT_NO_LAZY_FETCH": "1", "PYTHONDONTWRITEBYTECODE": "1"}
        # Clone the common object store so linked worktrees preserve shallow boundaries too.
        common = subprocess.run(["git", "-C", str(source), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                                capture_output=True, text=True, check=True, env=self.env).stdout.strip()
        subprocess.run(["git", "clone", "--shared", "--no-checkout", common, str(self.root)],
                       capture_output=True, check=True, env=self.env)
        self.git("checkout", "--detach", BASE_COMMIT)

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), "-c", "user.name=Local Test",
                               "-c", "user.email=test@example.invalid", *args],
                              capture_output=True, check=True, env=self.env).stdout.decode().strip()

    def test_original_base_still_passes(self):
        self.assertEqual(verify_nqc(self.root)["base_commit"], BASE_COMMIT)

    def test_defense_only_descendant_passes(self):
        path = self.root / "migration/defense/provenance.txt"
        path.parent.mkdir(parents=True)
        path.write_text("Local branch boundary test\n")
        self.git("add", "migration/defense")
        self.git("commit", "-m", "Add bounded defense material")
        result = verify_nqc(self.root)
        self.assertEqual(result["base_commit"], BASE_COMMIT)
        self.assertNotEqual(result["head_commit"], BASE_COMMIT)

    def test_other_committed_change_fails(self):
        with (self.root / "README.md").open("a") as stream:
            stream.write("\nChanged outside defense scope\n")
        self.git("add", "README.md")
        self.git("commit", "-m", "Unreviewed scope test")
        with self.assertRaisesRegex(Rejected, "nqc_unreviewed_change"):
            verify_nqc(self.root)

    def test_other_working_tree_change_fails(self):
        with (self.root / "README.md").open("a") as stream:
            stream.write("\nWorking tree change\n")
        with self.assertRaisesRegex(Rejected, "nqc_unreviewed_change"):
            verify_nqc(self.root)


if __name__ == "__main__":
    unittest.main()
