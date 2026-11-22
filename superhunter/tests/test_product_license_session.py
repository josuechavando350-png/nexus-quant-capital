"""Scan session contracts with a tiny verified archive and a simulated producer.

These tests exercise staging, binding and cleanup, not native ScanCode detection.
"""
from io import BytesIO
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from superhunter import product_licenses as licenses
from superhunter import product_source_audit as audit
from superhunter.product_reasoning import EvidenceError
from superhunter.product_review import copy_release, sha
from superhunter.product_upstream_notices import filename
from superhunter.safe_io import canonical, write_new_bundle


class ScanSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.release = self.root/'fixture.tar.gz'
        with tarfile.open(self.release, 'w:gz') as archive:
            data = b'fixture producer; never executed\n'
            member = tarfile.TarInfo('scancode-toolkit-v32.5.0/scancode')
            member.size = len(data)
            member.mode = 0o500
            archive.addfile(member, BytesIO(data))
        pin = patch.object(licenses, 'SCAN_SHA', sha(self.release.read_bytes()))
        pin.start()
        self.addCleanup(pin.stop)
        self.calls = []

    def producer(self, command, **options):
        self.assertEqual(command[:len(licenses.ISOLATE)], licenses.ISOLATE)
        executable = Path(command[len(licenses.ISOLATE)])
        folder = Path(command[-1])
        output = Path(command[command.index('--json') + 1])
        self.assertEqual(folder.name, 'notices')
        self.assertEqual(output.parent, folder.parent)
        self.assertEqual(Path(options['env']['HOME']), folder.parent)
        self.assertEqual(options['env']['PIP_NO_INDEX'], '1')
        self.assertFalse(output.exists())
        files = {p.name: p.read_bytes() for p in folder.iterdir()}
        self.calls.append((executable, folder.parent, output, files))
        report = {'headers': [{'tool_name': 'scancode-toolkit', 'tool_version': '32.5.0', 'errors': []}],
                  'files': [{'type': 'file', 'name': name, 'path': 'notices/' + name,
                             'sha256': sha(raw), 'scan_errors': [], 'license_detections': [],
                             'detected_license_expression_spdx': None}
                            for name, raw in files.items()]}
        output.write_bytes(canonical(report))
        return subprocess.CompletedProcess(command, 0)

    def test_one_distribution_with_fresh_input_output_and_home_per_batch(self):
        with patch.object(licenses.product_review, 'copy_release', wraps=copy_release) as copied, \
                patch.object(licenses.subprocess, 'run', side_effect=self.producer):
            with licenses.scan_session(self.release) as scanner:
                first = scanner({'one.txt': b'first notice\n'})
                self.assertFalse(self.calls[0][1].exists())
                second = scanner({'two.txt': b'second notice\n'})
                self.assertFalse(self.calls[1][1].exists())
                distribution = self.calls[0][0].parent
                self.assertTrue(distribution.exists())
            self.assertEqual(copied.call_count, 1)
        self.assertEqual(self.calls[0][0], self.calls[1][0])
        self.assertNotEqual(self.calls[0][1], self.calls[1][1])
        self.assertEqual(self.calls[1][3], {'two.txt': b'second notice\n'})
        self.assertEqual(first['notices']['one.txt']['sha256'], sha(b'first notice\n'))
        self.assertEqual(second['notices']['two.txt']['sha256'], sha(b'second notice\n'))
        self.assertFalse(distribution.parent.exists())
        with self.assertRaisesRegex(EvidenceError, 'session is closed'):
            scanner({'three.txt': b'after cleanup'})

    def test_compatibility_wrapper_has_identical_normalized_output(self):
        notices = {'license.txt': b'example\n'}
        with patch.object(licenses.subprocess, 'run', side_effect=self.producer):
            wrapped = licenses.scan(self.release, notices)
            with licenses.scan_session(self.release) as scanner:
                shared = scanner(notices)
        self.assertEqual(canonical(wrapped), canonical(shared))

    def test_corrupted_release_is_rejected_before_execution_and_cleaned(self):
        self.release.write_bytes(self.release.read_bytes() + b'corrupted')
        destinations = []

        def capture_copy(*args, **kwargs):
            destinations.append(args[2].parent)
            return copy_release(*args, **kwargs)

        with patch.object(licenses.product_review, 'copy_release', side_effect=capture_copy), \
                patch.object(licenses.subprocess, 'run') as run:
            with self.assertRaisesRegex(EvidenceError, 'release digest mismatch'):
                licenses.scan(self.release, {'license.txt': b'example'})
        run.assert_not_called()
        self.assertTrue(destinations)
        self.assertTrue(all(not p.exists() for p in destinations))

    def test_missing_second_report_cannot_reuse_first_success(self):
        def producer(command, **options):
            if not self.calls:
                return self.producer(command, **options)
            self.failed_batch = Path(command[-1]).parent
            return subprocess.CompletedProcess(command, 0)

        with patch.object(licenses.subprocess, 'run', side_effect=producer):
            with self.assertRaises(FileNotFoundError):
                with licenses.scan_session(self.release) as scanner:
                    scanner({'first.txt': b'first'})
                    scanner({'second.txt': b'second'})
        self.assertFalse(self.failed_batch.exists())
        self.assertFalse(self.calls[0][0].parent.parent.exists())

    def test_timeout_cleans_batch_and_distribution(self):
        def producer(command, **options):
            self.failed_batch = Path(command[-1]).parent
            self.distribution = Path(command[len(licenses.ISOLATE)]).parent.parent
            raise subprocess.TimeoutExpired(command, 300)

        with patch.object(licenses.subprocess, 'run', side_effect=producer):
            with self.assertRaises(subprocess.TimeoutExpired):
                licenses.scan(self.release, {'license.txt': b'example'})
        self.assertFalse(self.failed_batch.exists())
        self.assertFalse(self.distribution.exists())

    def test_mutated_caller_input_cannot_replace_bytes_bound_to_report(self):
        notices = {'license.txt': b'original\n'}

        def producer(command, **options):
            # Try to make the report and caller mapping agree with substituted bytes.
            (Path(command[-1])/'license.txt').write_bytes(b'substituted\n')
            notices['license.txt'] = b'substituted\n'
            return self.producer(command, **options)

        with patch.object(licenses.subprocess, 'run', side_effect=producer):
            with self.assertRaisesRegex(EvidenceError, 'input differs'):
                licenses.scan(self.release, notices)
        self.assertFalse(self.calls[0][0].parent.parent.exists())

    def test_notice_paths_cannot_escape_batch(self):
        with patch.object(licenses.subprocess, 'run') as run:
            with licenses.scan_session(self.release) as scanner:
                for name in ('../escape.txt', '/absolute.txt', 'child/license.txt', '.', '..', 'bad\\name'):
                    with self.subTest(name=name), self.assertRaisesRegex(EvidenceError, 'invalid ScanCode notice'):
                        scanner({name: b'example'})
        run.assert_not_called()

    def test_inventory_shares_distribution_across_deduplicated_batches_and_resolved_link(self):
        rows, corpus = [], {}
        for number in range(1, 33):
            raw = f'notice {number if number < 32 else 1}\n'.encode()
            row = {'id': number, 'github_id': number + 100, 'repository': f'org/tool{number}',
                   'revision': 'a'*40, 'notice': {'path': 'LICENSE', 'sha256': sha(raw)}}
            rows.append(row)
            corpus[filename(row)] = raw
        notices = self.root/'notices'
        write_new_bundle(notices, corpus)
        resolved = b'resolved license\n'
        checked = {'catalog_id': 32, 'path': 'upstream/032-tool32', 'tree': 'b'*40}
        contents = {'notice_link': {'status': 'resolved', 'git_blob': 'c'*40, 'sha256': sha(resolved)}}
        remote = {row['id']: {'tree': 'd'*40} for row in rows[:-1]}
        with patch.object(audit, 'sources', return_value=rows), \
                patch.object(audit, 'verify', return_value={'sources': [checked]}), \
                patch.object(audit, 'remote_trees', return_value=remote), \
                patch.object(audit, 'tree_inventory', return_value=contents), \
                patch.object(audit, 'git', return_value=resolved), \
                patch.object(licenses.product_review, 'copy_release', wraps=copy_release) as copied, \
                patch.object(licenses.subprocess, 'run', side_effect=self.producer):
            result = audit.inventory(self.root, notices, self.release)
        self.assertEqual(copied.call_count, 1)
        self.assertEqual([len(row[3]) for row in self.calls], [30, 1, 1])
        self.assertEqual(result['entries'][0]['notice_scan'], result['entries'][-1]['notice_scan'])
        self.assertEqual(result['entries'][-1]['resolved_notice_scan']['sha256'], sha(resolved))
        self.assertEqual(result['entries_sha256'], sha(canonical(result['entries'])))
        self.assertTrue(all(not row[1].exists() for row in self.calls))
        self.assertFalse(self.calls[0][0].parent.parent.exists())
