"""Exercise serial and parallel verification against disposable real Git checkouts."""
from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from superhunter import product_sources as sources
from superhunter.repository_boundary import git_object
from superhunter.safe_io import canonical


def fixture_git(root, *args, **kwargs):
    return subprocess.check_output(
        ['git', '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false',
         '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
         '-C', str(root), *args], stderr=subprocess.PIPE,
        env={**os.environ, 'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1'}, **kwargs)


class ParallelSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='nqc-source-parallel-')
        cls.addClassCleanup(cls.temp.cleanup)
        base = Path(cls.temp.name)
        seed = base/'seed'
        seed.mkdir()
        fixture_git(seed, 'init', '-q', '-b', 'fixture')
        (seed/'owned.txt').write_bytes(b'owned source fixture\n')
        fixture_git(seed, 'add', 'owned.txt')
        fixture_git(seed, 'commit', '-qm', 'first')
        cls.revision = fixture_git(seed, 'rev-parse', 'HEAD').decode().strip()
        fixture_git(seed, 'checkout', '-qb', 'different')
        (seed/'owned.txt').write_bytes(b'another owned source revision\n')
        fixture_git(seed, 'commit', '-qam', 'second')
        cls.different_revision = fixture_git(seed, 'rev-parse', 'HEAD').decode().strip()
        fixture_git(seed, 'checkout', '-q', 'fixture')
        cls.root = base/'product'
        cls.root.mkdir()
        fixture_git(cls.root, 'init', '-q', '-b', 'fixture')
        (cls.root/'upstream').mkdir()
        cls.catalog = [{'id': number, 'repository': f'owned/tool{number:03}', 'revision': cls.revision}
                       for number in range(1, 201)]
        manifest, index = [], []
        for row in cls.catalog:
            path = f"upstream/{row['id']:03}-{row['repository'].split('/')[1]}"
            fixture_git(cls.root, 'clone', '-q', '--shared', str(seed), path)
            manifest.append(f'[submodule "{path}"]\n\tpath = {path}\n'
                            f"\turl = https://github.com/{row['repository']}.git\n\tshallow = true\n")
            index.append(f'160000 {cls.revision}\t{path}\n')
        cls.manifest = ''.join(manifest).encode()
        (cls.root/'.gitmodules').write_bytes(cls.manifest)
        fixture_git(cls.root, 'add', '.gitmodules')
        fixture_git(cls.root, 'update-index', '--index-info', input=''.join(index).encode())
        fixture_git(cls.root, 'commit', '-qm', 'direct source fixtures')
        cls.first = cls.root/'upstream/001-tool001'

    def setUp(self):
        self.enterContext(patch.object(sources, 'sources', return_value=self.catalog))
        self.enterContext(patch.dict(sources.ROOT_FILES, {'.gitmodules': git_object('blob', self.manifest)}))

    def tearDown(self):
        fixture_git(self.first, 'reset', '--hard', self.revision)

    def assert_rejected_in_both_modes(self, diagnostic):
        for jobs in (1, 4):
            with self.subTest(jobs=jobs), self.assertRaisesRegex(ValueError, diagnostic):
                sources.verify(self.root, require_checkout=True, jobs=jobs)

    def test_parallel_inventory_is_byte_identical_and_keeps_catalog_order(self):
        serial = sources.verify(self.root, require_checkout=True, jobs=1)
        parallel = sources.verify(self.root, require_checkout=True, jobs=4)
        self.assertEqual(canonical(serial), canonical(parallel))
        self.assertEqual(parallel['status_counts'], {'checked_out': 200})
        self.assertEqual(parallel['catalog_only_count'], 0)
        self.assertEqual([row['catalog_id'] for row in parallel['sources']], list(range(1, 201)))
        self.assertFalse(parallel['upstream_code_executed_by_verifier'])

    def test_index_flags_cannot_hide_modified_source(self):
        path = self.first/'owned.txt'
        for flag in ('assume-unchanged', 'skip-worktree'):
            with self.subTest(flag=flag):
                fixture_git(self.first, 'update-index', '--' + flag, '--', path.name)
                try:
                    path.write_bytes(b'unreviewed replacement')
                    self.assertFalse(sources.tracked_files_match(self.first))
                finally:
                    fixture_git(self.first, 'update-index', '--no-' + flag, '--', path.name)
                    fixture_git(self.first, 'restore', '--', path.name)

    def test_restored_files_with_stale_stat_cache_match_the_original_blob(self):
        path = self.first/'owned.txt'
        os.utime(path, (1, 1))
        index = self.first/'.git/index'
        before = index.read_bytes()
        self.assertIn(b'owned.txt', fixture_git(self.first, 'diff-files', '--name-only'))
        self.assertTrue(sources.tracked_files_match(self.first))
        self.assertEqual(index.read_bytes(), before)
        path.write_bytes(b'x' * path.stat().st_size)
        os.utime(path, (1, 1))
        self.assertFalse(sources.tracked_files_match(self.first))

    def test_committed_eol_rule_allows_exact_crlf_expansion_only(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = Path(folder)
            fixture_git(repo, 'init', '-q')
            (repo/'.gitattributes').write_bytes(b'file text eol=crlf\n')
            path = repo/'file'
            path.write_bytes(b'x' * (1024 * 1024 - 1) + b'\r\ny\r\n')
            fixture_git(repo, 'add', '.')
            fixture_git(repo, 'commit', '-qm', 'declare CRLF working representation')
            os.utime(path, (1, 1))
            self.assertTrue(sources.tracked_files_match(repo))
            path.write_bytes(path.read_bytes().replace(b'y\r\n', b'y\n'))
            self.assertFalse(sources.tracked_files_match(repo))

    def test_ident_expansion_uses_pinned_attributes_without_local_filter_commands(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = Path(folder)
            fixture_git(repo, 'init', '-q')
            (repo/'.gitattributes').write_bytes(b'sample ident filter=local-driver\n')
            path = repo/'sample'
            path.write_bytes(b'$Id$\n')
            fixture_git(repo, 'add', '.')
            fixture_git(repo, 'commit', '-qm', 'declare an identity substitution')
            oid = fixture_git(repo, 'rev-parse', 'HEAD:sample').strip()
            path.write_bytes(b'$Id: ' + oid + b' $\n')
            marker = repo/'executed'
            fixture_git(repo, 'config', 'filter.local-driver.smudge', 'touch ' + shlex.quote(str(marker)) + '; cat')
            self.assertTrue(sources.tracked_files_match(repo))
            self.assertFalse(marker.exists())
            path.write_bytes(b'$Id: ' + b'0' * 40 + b' $\n')
            self.assertFalse(sources.tracked_files_match(repo))

    def test_mode_and_removal_are_rejected(self):
        path = self.first/'owned.txt'
        path.chmod(0o755)
        self.assertFalse(sources.tracked_files_match(self.first))
        path.unlink()
        self.assertFalse(sources.tracked_files_match(self.first))

    def test_symlink_commits_compare_the_link_text(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = Path(folder)
            fixture_git(repo, 'init', '-q')
            path = repo/'link'
            path.symlink_to('original-missing-target')
            fixture_git(repo, 'add', 'link')
            fixture_git(repo, 'commit', '-qm', 'track link text')
            path.unlink()
            path.symlink_to('original-missing-target')
            self.assertTrue(sources.tracked_files_match(repo))
            path.unlink()
            path.symlink_to('replacement-missing-target')
            self.assertFalse(sources.tracked_files_match(repo))

    def test_changed_tracked_bytes_are_rejected_without_cached_success(self):
        sources.verify(self.root, require_checkout=True, jobs=4)
        (self.first/'owned.txt').write_bytes(b'changed tracked source\n')
        self.assert_rejected_in_both_modes('tracked submodule files differ')

    def test_staged_changes_are_rejected(self):
        (self.first/'owned.txt').write_bytes(b'staged owned source\n')
        fixture_git(self.first, 'add', 'owned.txt')
        self.assert_rejected_in_both_modes('submodule index differs')

    def test_wrong_head_is_rejected(self):
        fixture_git(self.first, 'checkout', '-q', '--detach', self.different_revision)
        self.assert_rejected_in_both_modes('different revision')

    def test_uninitialized_checkout_is_rejected(self):
        gitdir = self.first/'.git'
        hidden = Path(self.temp.name)/'temporarily-hidden-git'
        gitdir.rename(hidden)
        try:
            self.assert_rejected_in_both_modes('submodule not initialized')
        finally:
            hidden.rename(gitdir)

    def test_catalog_failure_precedes_checkout_workers(self):
        wrong = [{**row, 'revision': 'f'*40} if row['id'] == 153 else row for row in self.catalog]
        with patch.object(sources, 'sources', return_value=wrong), \
                patch.object(sources, 'ThreadPoolExecutor', side_effect=AssertionError('workers started')):
            with self.assertRaisesRegex(ValueError, 'Git tree and catalog revision differ'):
                sources.verify(self.root, require_checkout=True, jobs=4)

    def test_worker_limit_rejects_invalid_values(self):
        for jobs in (0, 9, -1, True, 1.0, '4', None):
            with self.subTest(jobs=jobs), self.assertRaisesRegex(ValueError, 'jobs must be an integer'):
                sources.verify(self.root, require_checkout=True, jobs=jobs)

    def test_cli_preserves_pinned_output_with_explicit_jobs(self):
        output = StringIO()
        with patch.object(sources, 'ROOT', self.root), redirect_stdout(output):
            self.assertEqual(sources.main(['--jobs', '4']), 0)
        self.assertEqual(json.loads(output.getvalue()), sources.verify(self.root))


if __name__ == '__main__':
    unittest.main()
