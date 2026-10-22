"""Build/transport tests only. PostgreSQL execution is never simulated or claimed."""
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import build_termux_import_check as builder


def extract(script):
    pattern=r'base64 -d <<\'(NQC_MINER_IMPORT_INPUT_\d+)\' \| gzip -d > "\$MINER_TEST_EVIDENCE/([^"/]+)"\n([A-Za-z0-9+/=\n]+)\n\1\n'
    return {name:gzip.decompress(base64.b64decode(data)) for _,name,data in re.findall(pattern,script)}


class TermuxImportRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary=Path(os.environ['NQC_MINER_TEST_BINARY'])
        cls.script,cls.hashes,cls.labels=builder.render(cls.binary)
        cls.inputs=extract(cls.script)

    def test_exact_sources_and_real_rust_fixture_reports_survive_embedding(self):
        self.assertEqual(set(self.inputs),set(self.hashes))
        for name,data in self.inputs.items():
            self.assertEqual(hashlib.sha256(data).hexdigest(),self.hashes[name])
        for name,source in [('postgres.sql','infra/postgres.sql'),('postgres_import.sql','infra/postgres_import.sql'),
                            ('cases.sql','scripts/postgres_import_cases.sql'),('holder.sql','scripts/postgres_import_holder.sql')]:
            self.assertEqual(self.inputs[name],(builder.ROOT/source).read_bytes())
        report=json.loads(self.inputs['fixture-verification.json'])
        payloads=re.findall(r"VALUES \('([^']+)',convert_from\(decode\('([0-9a-f]+)','hex'\),'UTF8'\)::jsonb\);",self.inputs['fixtures.sql'].decode())
        self.assertEqual(len(payloads),16)
        self.assertEqual({name for name,_ in payloads},set(builder.SCENARIOS))
        for name,encoded in payloads:
            raw=bytes.fromhex(encoded);p=json.loads(raw);r=report['fixtures'][name]
            self.assertEqual(hashlib.sha256(raw+b'\n').hexdigest(),r['request_sha256'])
            self.assertTrue(r['rust_verification']['integrity_verified'])
            self.assertFalse(r['rust_verification']['authenticity_verified'])
            self.assertEqual(len(p['records']),r['rust_verification']['records'])
            self.assertEqual(p['database_id'],builder.DATABASE_ID)
            self.assertEqual(p['owner']['data_class'],'synthetic')
        self.assertFalse(report['postgres_executed'])

    def test_bundle_is_reproducible_with_same_verifier_and_sources(self):
        script,hashes,labels=builder.render(self.binary)
        self.assertEqual(script,self.script)
        self.assertEqual(hashes,self.hashes)
        self.assertEqual(labels,self.labels)

    def test_bash_syntax_and_native_environment_guard(self):
        with tempfile.TemporaryDirectory(prefix='nqc-miner-runner-guard-') as work:
            path=Path(work)/'runner.sh';path.write_text(self.script)
            subprocess.run(['bash','-n',str(path)],check=True,capture_output=True)
            # Explicit foreign PREFIX: the real preflight must reject this host.
            result=subprocess.run(['bash',str(path)],env=dict(os.environ,PREFIX='/not-termux'),capture_output=True,timeout=5)
            self.assertEqual(result.returncode,2)
            self.assertIn(b'REJECTED: use ordinary native Termux',result.stderr)
            self.assertNotIn(b'Evidence:',result.stdout)

    def test_hash_manifest_rejects_changed_embedded_input(self):
        sums=''.join(f'{digest}  {name}\n' for name,digest in self.hashes.items())
        with tempfile.TemporaryDirectory(prefix='nqc-miner-runner-hashes-') as work:
            root=Path(work)
            for name,data in self.inputs.items(): (root/name).write_bytes(data)
            (root/'input.sha256').write_text(sums)
            subprocess.run(['sha256sum','-c','input.sha256'],cwd=root,check=True,capture_output=True)
            with (root/'fixtures.sql').open('ab') as stream:stream.write(b'-- changed\n')
            result=subprocess.run(['sha256sum','-c','input.sha256'],cwd=root,capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn(b'fixtures.sql: FAILED',result.stdout)


if __name__=='__main__':unittest.main()
