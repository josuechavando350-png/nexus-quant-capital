import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from superhunter.toolkit_static_setup import install_aderyn


class NativeToolkitTests(unittest.TestCase):
    def test_bad_aderyn_archive_cannot_replace_runtime_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / 'aderyn').write_bytes(b'existing')
            archive = base / 'release.tar.xz'
            archive.write_bytes(b'wrong release')
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                install_aderyn(archive, base)
            self.assertEqual((base / 'aderyn').read_bytes(), b'existing')

    @unittest.skipUnless(os.environ.get('NQC_T36_NATIVE_RUNTIME'), 'requires prepared Linux T36 runtime')
    def test_visibility_plugin_distinguishes_called_and_unused_public_methods(self):
        runtime = Path(os.environ['NQC_T36_NATIVE_RUNTIME']).resolve(strict=True)
        source = """pragma solidity ^0.8.24;
contract VisibilityControl {
    uint256 private n;
    function usedInternally() public { n++; }
    function caller() external { usedInternally(); }
    function onlyExternal() public { n++; }
}
"""
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / 'Visibility.sol').write_text(source)
            subprocess.run([runtime / 'static/venv/bin/slither', 'Visibility.sol', '--solc', runtime / 'solc',
                            '--detect', 'pess-public-vs-external', '--json', 'result.json', '--fail-none'],
                           cwd=target, check=True, capture_output=True, timeout=60)
            report = json.loads((target / 'result.json').read_bytes())
            self.assertTrue(report['success'])
            findings = report['results']['detectors']
            self.assertEqual([row['check'] for row in findings], ['pess-public-vs-external'])
            self.assertEqual([elem['name'] for elem in findings[0]['elements'] if elem['type'] == 'function'],
                             ['onlyExternal'])
