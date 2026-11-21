"""Compare inventory workers over real Git trees; isolate checkout setup metadata."""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from superhunter import product_source_audit as audit, product_sources
from superhunter.repository_boundary import git_object
from superhunter.safe_io import canonical


class ParallelInventoryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.rows, checked = [], []
        for number in range(1, 4):
            folder = self.root/f'tool-{number}'
            folder.mkdir()
            def git(*args):
                return subprocess.check_output(['git', '-C', str(folder), '-c', 'core.hooksPath=/dev/null',
                    '-c', 'commit.gpgsign=false', '-c', 'user.name=Fixture',
                    '-c', 'user.email=fixture@example.invalid', *args], stderr=subprocess.PIPE)
            git('init', '-q')
            raw = f'owned notice {number}\n'.encode()
            (folder/'LICENSE').write_bytes(raw)
            (folder/'Cargo.toml').write_text(f'[package]\nname = "owned{number}"\n')
            git('add', '.')
            git('commit', '-qm', 'owned tree')
            revision = git('rev-parse', 'HEAD').decode().strip()
            row = {'id': number, 'github_id': 100 + number, 'repository': f'owned/tool{number}',
                   'revision': revision, 'notice': {'path': 'LICENSE', 'git_blob': git_object('blob', raw),
                                                  'sha256': audit.sha(raw), 'bytes': len(raw)}}
            self.rows.append(row)
            checked.append({'catalog_id': number, 'path': folder.name,
                            'tree': git('rev-parse', 'HEAD^{tree}').decode().strip()})
        self.rows.append({'id': 4, 'github_id': 104, 'repository': 'owned/metadata-only',
                          'revision': 'b'*40, 'notice': {'path': 'LICENSE'}})
        # Checkout verification has its own real-Git suite. These fixtures target
        # tree enumeration, catalog joining, and fail-closed inventory publication.
        self.enterContext(patch.object(audit, 'verify', return_value={'sources': checked}))
        self.enterContext(patch.object(audit, 'sources', return_value=self.rows))
        self.enterContext(patch.object(audit, 'remote_trees', return_value={4: {'tree': 'c'*40}}))

    def test_parallel_tree_inventory_has_identical_bytes_and_metadata_only_row(self):
        serial = audit.inventory(self.root, jobs=1)
        parallel = audit.inventory(self.root, jobs=4)
        self.assertEqual(canonical(serial), canonical(parallel))
        self.assertEqual([row['id'] for row in parallel['entries']], [1, 2, 3, 4])
        self.assertEqual(parallel['entries'][0]['contents']['manifest_counts_by_filename'], {'Cargo.toml': 1})
        self.assertIsNone(parallel['entries'][-1]['contents'])
        self.assertEqual(parallel['entries'][-1]['evidence'], 'github_commit_metadata')

    def test_invalid_tree_notice_aborts_before_license_producer(self):
        self.rows[1]['notice']['git_blob'] = '0'*40
        with patch('superhunter.product_licenses.scan_session', side_effect=AssertionError('producer started')):
            for jobs in (1, 4):
                with self.subTest(jobs=jobs), self.assertRaisesRegex(ValueError, 'notice path differs'):
                    audit.inventory(self.root, self.root/'notices', self.root/'release', jobs=jobs)

    def test_cli_jobs_reaches_inventory(self):
        with patch.object(audit, 'inventory', return_value={'complete': True}) as inventory, \
                redirect_stdout(StringIO()):
            self.assertEqual(product_sources.main(['--inventory', '--jobs', '2']), 0)
        inventory.assert_called_once_with(product_sources.ROOT, None, None, jobs=2)
