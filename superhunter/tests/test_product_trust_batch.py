import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from superhunter import product_trust_batch as b
from superhunter.product_reasoning import EvidenceError


class LockChecks(unittest.TestCase):
    def test_node_resolves_nested_and_shared_dependencies(self):
        p = json.loads((b.SUPPLY / b.LOCK).read_bytes())['packages']
        edges = b.locked_edges(p)
        self.assertEqual(len(edges), 61)
        row = next(r for r in edges if r['parent'] == 'node_modules/viem' and r['name'] == '@noble/curves')
        self.assertEqual(row['child'], 'node_modules/viem/node_modules/@noble/curves')
        self.assertNotEqual(row['actual'], p['node_modules/@noble/curves']['version'])

    def test_missing_package_is_rejected(self):
        with self.assertRaisesRegex(EvidenceError, 'unresolved'):
            b.locked_edges({'': {'dependencies': {'missing': '2.5.0'}}})
        with self.assertRaisesRegex(EvidenceError, 'empty'):
            b.locked_edges({'': {}})

    def test_range_contract(self):
        for selector, bounds, accepted, rejected in (
            ('~1.2.3', ['>=1.2.3', '<1.3.0'], '1.2.5', '1.3.0'),
            ('^0.2.0', ['>=0.2.0', '<0.3.0'], '0.2.1', '0.3.0'),
            ('^0.0.4', ['>=0.0.4', '<0.0.5'], '0.0.4', '0.0.5'),
            ('^2.2.3', ['>=2.2.3', '<3.0.0'], '2.9.1', '2.2.2'),
            ('4.0.0-beta.5', ['=4.0.0-beta.5'], '4.0.0-beta.5', '4.0.0'),
        ):
            with self.subTest(selector=selector):
                self.assertEqual(b.version_bounds(selector), bounds)
                self.assertTrue(b.oracle(selector, accepted))
                self.assertFalse(b.oracle(selector, rejected))
        for unsupported in ('^1.0.0-rc.1', 'latest', '*', 'file:some-file', 'git+ssh://'):
            with self.assertRaises(EvidenceError):
                b.version_bounds(unsupported)

    def test_substituted_file_record_is_rejected(self):
        files = {'dependency': b'first\r\nsecond\nlast'}
        facts = [{'Digest': b.digest(files['dependency']), 'Lines': [5, 6, 4]}]
        self.assertEqual(b.check_files(files, facts)['dependency']['lines'], 3)
        for invalid in ([], [dict(facts[0], Lines=[5, 6, 5])], [dict(facts[0], Digest='0' * 64)]):
            with self.assertRaises(EvidenceError):
                b.check_files(files, invalid)


@unittest.skipUnless(os.environ.get('NQC_TRUST_TEST_SOURCES'), 'set NQC_TRUST_TEST_SOURCES to the checkout directory')
class SourceChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(os.environ['NQC_TRUST_TEST_SOURCES']).resolve()
        cls.receipt = b.review(cls.root)

    def test_joint_consumer(self):
        rows = self.receipt
        self.assertEqual(set(rows), set(b.PINS))
        self.assertEqual({r['input_lock_sha256'] for r in rows.values()}, {rows[b.OSSF]['files'][b.LOCK]['sha256']})
        self.assertEqual(rows[b.GRYPE]['out_of_range_controls_rejected'], len(rows[b.GRYPE]['edges']))
        self.assertEqual(rows[b.DC]['unrelated_cpe_controls_preserved'], len(rows[b.DC]['package_urls']))
        self.assertTrue(rows[b.OSSF]['same_width_mutation_detected'])
        self.assertEqual(rows[b.OSSF]['native_build_sha256'], rows[b.GRYPE]['native_build_sha256'])
        self.assertEqual(b.canonical(rows), (b.SUPPLY / 'trust-batch-receipt.json').read_bytes())

    def test_npm_semver_and_resolution_independent(self):
        # A separate implementation uses Node path traversal, canonical semver and
        # the original npm selectors. It sees neither normalized bounds nor verdicts.
        script = '''const fs=require('node:fs'), path=require('node:path').posix, semver=require('semver');
const pkgs=JSON.parse(fs.readFileSync(process.argv[1])).packages, rows=[];
for(const [parent,rec] of Object.entries(pkgs))for(const [name,selector] of Object.entries(rec.dependencies||{})){
  let dir=parent, child;
  while(true){ child=path.join(dir,'node_modules',name);if(Object.hasOwn(pkgs,child))break;
    if(!dir || dir==='.')throw Error(name);dir=path.dirname(dir); }
  const actual=pkgs[child].version, outside=(semver.major(actual)+1)+'.0.0';
  rows.push({parent,name,child,selector,actual,positive:semver.satisfies(actual,selector),negative:semver.satisfies(outside,selector)});
}process.stdout.write(JSON.stringify(rows));'''
        node = shutil.which('node')
        self.assertIsNotNone(node)
        proc = subprocess.run([node, '-e', script, str(b.SUPPLY / b.LOCK)], check=True,
                              capture_output=True, timeout=10)
        native = self.receipt[b.GRYPE]['edges']
        observed = json.loads(proc.stdout)
        self.assertEqual(len(observed), len(native))
        for row in observed:
            self.assertTrue(row.pop('positive'))
            self.assertFalse(row.pop('negative'))
            self.assertIn(row, native)

    def test_wrong_cpe_rule_cannot_credit_an_unrelated_package(self):
        source = b.original_sources(self.root)[b.DC]
        p = json.loads((b.SUPPLY / b.LOCK).read_bytes())['packages']
        original = source[b.RULES]
        for bound in (b'^.+$', b'^pkg:npm/flat@.*$'):
            corrupted = original.replace(b'^(?!pkg:npm/flat@).+$', bound)
            self.assertNotEqual(original, corrupted)
            with self.assertRaises(EvidenceError):
                b.attribution(p, {**source, b.RULES: corrupted})

    def test_bad_source_or_cache_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'bad').write_bytes(b'neither a binary nor a receipt')
            from unittest.mock import patch
            with patch.dict(os.environ, NQC_TRUST_BINARY=str(root / 'bad')):
                with self.assertRaisesRegex(EvidenceError, 'cached'):
                    b.native(root, {}, [], [])
            with self.assertRaises((EvidenceError, subprocess.CalledProcessError)):
                b.original_sources(root)
