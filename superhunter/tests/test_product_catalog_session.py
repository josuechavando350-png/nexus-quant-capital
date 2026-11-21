from hashlib import blake2b
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from superhunter import product_census_header, product_solidity_headers, product_upstream_notices as notices
from superhunter.product_batches import coverage
from superhunter.product_reasoning import EvidenceError
from superhunter.product_review import ProductIndex, repositories, sha
from superhunter.repository_boundary import git_object
from superhunter.safe_io import canonical, write_new_bundle


class CatalogSessionTests(unittest.TestCase):
    def test_pinned_upstream_notices_cover_each_catalog_identity(self):
        rows = notices.sources()
        self.assertEqual([r['id'] for r in rows], list(range(1, 201)))
        self.assertEqual(len({notices.filename(r) for r in rows}), 200)
        self.assertEqual(len({notices.document_hash(r) for r in rows}), 144)

    def test_excerpt_validates_whole_source_and_selected_bytes(self):
        raw = b'title\nlicense metadata\n'
        notice = {'bytes': len(raw), 'sha256': sha(raw), 'git_blob': git_object('blob', raw),
                  'line': 2, 'selected_sha256': sha(b'license metadata\n')}
        self.assertEqual(notices.select_document({'notice': notice, 'id': 1}, raw), b'license metadata\n')
        for edited in (raw.replace(b'title', b'Title'), raw.upper()):
            with self.assertRaises(EvidenceError):
                notices.select_document({'notice': notice, 'id': 1}, edited)
        with self.assertRaises(EvidenceError):
            notices.select_document({'notice': {**notice, 'line': 1}, 'id': 1}, raw)

    def test_resealed_notice_cannot_replace_committed_document(self):
        doc = b'notice\n'
        rows = [{'id': i, 'repository': f'org/tool{i}', 'github_id': 10 + i, 'revision': 'a'*40,
                 'notice': {'path': 'LICENSE', 'sha256': sha(doc)}} for i in (1, 2)]
        data = {notices.filename(r): doc for r in rows}
        with tempfile.TemporaryDirectory() as tmp, patch.object(notices, 'sources', return_value=rows):
            index = SimpleNamespace(repos={r['repository']: {} for r in rows})
            work = Path(tmp)/'complete'
            write_new_bundle(work, data)
            self.assertEqual(notices.attach(index, work), data)
            self.assertEqual(index.repos['org/tool1']['upstream_notice']['identical_document_ids'], [1, 2])
            self.assertEqual(index.upstream_notices['distinct_documents'], 1)
            name = notices.filename(rows[0])
            (work/name).write_bytes(b'other')
            with self.assertRaises(EvidenceError):
                notices.attach(index, work)
            (work/'COMPLETE.json').write_bytes(canonical({'schema_version': 1, 'sha256':
                {k: sha((work/k).read_bytes()) for k in data}}))
            with self.assertRaises(EvidenceError):
                notices.attach(index, work)
            (work/name).unlink()
            with self.assertRaises(EvidenceError):
                notices.attach(index, work)

    def test_historical_receipts_and_new_receipts_remain_distinguishable(self):
        index = ProductIndex({'repositories': repositories(), 'packages': [], 'census_graph': {'nodes': []},
                              'conflicting_python_pins': {}, 'minimum_python_pin_groups': 2, 'tools': {
                                  'anchore/syft': {}, 'cvc5/cvc5': {}},
                              'profile_whose_isolation_resolves_all_observed_pin_conflicts': 'owned-spec-evm'})
        index.repos['ack3-ai/wake']['solidity_metadata_evidence'] = {'report': 'test'}
        index.repos['ethereum/eips']['census_header_reference'] = {'report': 'test'}
        index.repos['usestrix/strix']['upstream_notice'] = {'document': 'upstream-001-license.txt'}
        result = coverage(index)
        self.assertEqual(result['verified_upstream_notices'], 1)
        self.assertEqual(result['prior_with_receipts'], 38)
        self.assertEqual(result['with_receipts_in_either'], 40)
        self.assertEqual(result['session_with_receipts'], 4)
        self.assertEqual(result['identities'][0]['observed_role'], 'pending')
        self.assertEqual(result['identities'][189]['session_role'], 'reference_data')

    def test_header_consensus_requires_equal_bytes_and_changed_control(self):
        base = {'rlp': '0xa0', 'hash': 'expected'}
        changed = {'rlp': '0xb0', 'hash': 'changed'}
        def votes(row):
            return {k: row.copy() for k in ('ethereumjs', 'viem', 'ethers')}
        out = {'original': votes(base), 'changed_gas_used': votes(changed)}
        self.assertEqual(product_census_header.reconcile(out, 'expected')['original']['rlp_bytes'], 1)
        with self.assertRaises(EvidenceError):
            product_census_header.reconcile({**out, 'changed_gas_used': votes(base)}, 'expected')
        out['original']['viem']['rlp'] = '0xa1'
        with self.assertRaises(EvidenceError):
            product_census_header.reconcile(out, 'expected')

    def test_solidity_join_rejects_disagreement_and_keeps_missing_profile(self):
        path = 'ci/project/a.sol'
        text = '// SPDX-License-Identifier: MIT\npragma solidity ^0.8.24;\n'
        wake = {path: {'imports': [], 'blake2b_256': blake2b(text.encode(), digest_size=32).hexdigest(),
                       'accepts': {'0.8.23': False, '0.8.24': True, '0.8.25': True, '0.9.0': False}}}
        ast = {'nodeType': 'SourceUnit', 'absolutePath': path, 'license': 'MIT', 'nodes': [
               {'nodeType': 'PragmaDirective', 'literals': ['solidity', '^', '0.8', '.24']}]}
        parsed = {'sources': {path: {'ast': ast}}}
        compare = product_solidity_headers.compare
        self.assertIsNone(compare({path: text}, {}, wake, parsed)['solidity_files'][path]['enclosing_profile'])
        with self.assertRaises(EvidenceError):
            compare({path: text}, {'ci/project/foundry.toml': {'solc': '0.9.0'}}, wake, parsed)
        ast['nodes'].append({'nodeType': 'ImportDirective', 'file': './Missing.sol'})
        with self.assertRaises(EvidenceError):
            compare({path: text}, {}, wake, parsed)
