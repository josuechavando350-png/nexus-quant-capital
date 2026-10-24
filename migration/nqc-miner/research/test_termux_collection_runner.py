"""Real fixture preparation and transport checks, not simulated PostgreSQL."""
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
import build_termux_collection_check as builder


def extract(script):
    pattern = r'base64 -d <<\'(NQC_MINER_COLLECTION_INPUT_\d+)\' \| gzip -d > "\$MINER_TEST_EVIDENCE/([^"/]+)"\n([A-Za-z0-9+/=\n]+)\n\1\n'
    return {name: gzip.decompress(base64.b64decode(data)) for _, name, data in re.findall(pattern, script)}


class TermuxCollectionRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = Path(os.environ['NQC_MINER_TEST_BINARY'])
        cls.script, cls.inputs, cls.labels = builder.render(cls.binary)

    def test_embedded_sources_and_verified_artificial_inputs_match(self):
        self.assertEqual(extract(self.script), self.inputs)
        self.assertEqual(len(self.labels), 33)
        for name in ['postgres.sql', 'postgres_import.sql', 'postgres_collection.sql']:
            self.assertEqual(self.inputs[name], (builder.ROOT / 'infra' / name).read_bytes())
        report = json.loads(self.inputs['fixture-verification.json'])
        rows = re.findall(r"VALUES \('([^']+)',convert_from\(decode\('([0-9a-f]+)','hex'\),'UTF8'\)::jsonb\);", self.inputs['fixtures.sql'].decode())
        self.assertEqual(len(rows), 12)
        for name, encoded in rows:
            request = bytes.fromhex(encoded); result = report['fixtures'][name]
            self.assertEqual(hashlib.sha256(request + b'\n').hexdigest(), result['request_sha256'])
            verification = result['rust_verification']
            if verification.get('status') == 'quarantined': verification = verification['control']
            self.assertTrue(verification['integrity_verified'])
            self.assertFalse(result['manifest']['database_applied'])
        self.assertFalse(report['economic_evidence'])
        self.assertFalse(report['postgres_executed'])

    def test_repeat_build_is_identical_for_same_verifier_and_sources(self):
        script, inputs, labels = builder.render(self.binary)
        self.assertEqual(script, self.script)
        self.assertEqual(inputs, self.inputs)
        self.assertEqual(labels, self.labels)

    def test_current_verifier_binding_and_original_delivery_are_preserved(self):
        # The historical native run pins its original executable. A new build
        # must change generated fixture provenance, not rewrite that evidence.
        current = json.loads(self.inputs['fixture-verification.json'])
        binary_sha = hashlib.sha256(self.binary.read_bytes()).hexdigest()
        about = json.loads(subprocess.check_output([str(self.binary), 'about']))
        for fixture in current['fixtures'].values():
            self.assertEqual(fixture['manifest']['verifier_sha256'], binary_sha)
            self.assertEqual(fixture['manifest']['verifier_build'], about)
        delivered = (builder.ROOT / 'scripts/nqc-miner-collection-check.sh').read_bytes()
        native = json.loads((builder.ROOT / 'evidence/termux-collection-20261022/audit.json').read_bytes())
        self.assertEqual(hashlib.sha256(delivered).hexdigest(), native['runner_sha256'])
        old = json.loads(extract(delivered.decode())['fixture-verification.json'])
        for fixture in old['fixtures'].values():
            self.assertEqual(fixture['manifest']['verifier_sha256'],
                             '47292cd97732d246099b63f07cea6dc128dfd5612efe3341a6cefb4e631d4548')
        if binary_sha == '47292cd97732d246099b63f07cea6dc128dfd5612efe3341a6cefb4e631d4548':
            self.assertEqual(self.script.encode(), delivered)

    def test_bash_syntax_and_foreign_environment_guard(self):
        with tempfile.TemporaryDirectory(prefix='nqc-collection-runner-') as work:
            p = Path(work) / 'runner.sh'; p.write_text(self.script)
            subprocess.run(['bash', '-n', str(p)], check=True, capture_output=True)
            r = subprocess.run(['bash', str(p)], env=dict(os.environ, PREFIX='/not-termux'), capture_output=True, timeout=5)
            self.assertEqual(r.returncode, 2)
            self.assertNotIn(b'Evidence:', r.stdout)

    def test_manifest_detects_changed_collection_sql(self):
        with tempfile.TemporaryDirectory(prefix='nqc-collection-hashes-') as work:
            root = Path(work)
            for name, raw in self.inputs.items(): (root / name).write_bytes(raw)
            (root / 'input.sha256').write_text(''.join(f'{hashlib.sha256(raw).hexdigest()}  {name}\n' for name, raw in self.inputs.items()))
            subprocess.run(['sha256sum', '-c', 'input.sha256'], cwd=root, check=True, capture_output=True)
            with (root / 'postgres_collection.sql').open('ab') as stream: stream.write(b'-- altered\n')
            r = subprocess.run(['sha256sum', '-c', 'input.sha256'], cwd=root, capture_output=True)
            self.assertNotEqual(r.returncode, 0)


if __name__ == '__main__':
    unittest.main()
