"""Native test transport/source checks; does not claim a PostgreSQL execution."""
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import build_termux_sync_check as builder


class TermuxSyncRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script, cls.inputs = builder.render()

    def test_embedded_client_and_pinned_fixtures_exact(self):
        pattern = r'base64 -d <<\'(NQC_MINER_SYNC_INPUT_\d+)\' \| gzip -d > "\$MINER_TEST_EVIDENCE/([^"/]+)"\n([A-Za-z0-9+/=\n]+)\n\1\n'
        inputs = {name: gzip.decompress(base64.b64decode(encoded)) for _, name, encoded in re.findall(pattern, self.script)}
        self.assertEqual(inputs, self.inputs); self.assertEqual(len(inputs), 8)
        for name in ['collection_transport.py', 'postgres_transport_runtime.py']:
            self.assertEqual(inputs[name], (builder.ROOT / 'scripts' / name).read_bytes())
        source = json.loads(inputs['transport-source.json'])
        self.assertEqual(len(source['checks']), 17)
        self.assertFalse(source['postgres_client_runtime_executed'])
        for name, digest in source['input_hashes'].items():
            self.assertEqual(hashlib.sha256(inputs[name]).hexdigest(), digest)

    def test_deterministic_delivery_and_bash_parse(self):
        self.assertEqual(builder.render(), (self.script, self.inputs))
        self.assertEqual(self.script, (builder.ROOT / 'scripts/nqc-miner-sync-check.sh').read_text())
        subprocess.run(['bash', '-n'], input=self.script.encode(), check=True, capture_output=True)

    def test_foreign_environment_guard_runs_before_any_owned_directory(self):
        with tempfile.TemporaryDirectory(prefix='nqc-sync-runner-') as temp:
            script = Path(temp) / 'runner.sh'; script.write_text(self.script)
            result = subprocess.run(['bash', str(script)], env=dict(os.environ, PREFIX='/not-termux'), capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn(b'Evidence:', result.stdout)

    def test_manifest_detects_changed_transport(self):
        with tempfile.TemporaryDirectory(prefix='nqc-sync-manifest-') as temp:
            root = Path(temp)
            for name, raw in self.inputs.items(): (root / name).write_bytes(raw)
            sums = ''.join(f'{hashlib.sha256(raw).hexdigest()}  {name}\n' for name, raw in self.inputs.items())
            (root / 'input.sha256').write_text(sums)
            subprocess.run(['sha256sum', '-c', 'input.sha256'], cwd=root, capture_output=True, check=True)
            with (root / 'collection_transport.py').open('ab') as stream: stream.write(b'\n# altered')
            result = subprocess.run(['sha256sum', '-c', 'input.sha256'], cwd=root, capture_output=True)
            self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
