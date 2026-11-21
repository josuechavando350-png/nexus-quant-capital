"""Refute false credits using archived inputs; replaying a receipt never counts as a new execution."""
from types import SimpleNamespace
import unittest

from superhunter.product_reasoning import EvidenceError
from superhunter.product_review import ROOT
from superhunter.safe_io import canonical, strict_json
from superhunter.tools import verify_native_session as native_verifier
from superhunter.tools import verify_review_115 as verifier


class ConsolidatedEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archive = verifier.unpack((ROOT/'superhunter/product_supply/native-session-70.json').read_bytes())
        cls.keys = verifier.response_keys(cls.archive)

    def test_historical_archive_preserves_its_own_acceptance_scope(self):
        result = native_verifier.verify(self.archive)
        self.assertEqual((result['session'], result['executables'], result['reference_data']), (70, 58, 12))
        with self.assertRaisesRegex(EvidenceError, 'incomplete consolidated session'):
            verifier.verify(self.archive, require_consolidated=True)

    def test_native_receipt_without_the_group_report_is_rejected(self):
        raw = b'\n'.join(self.archive.splitlines()[:-1]) + b'\n'
        with self.assertRaisesRegex(EvidenceError, 'no matching producer receipt'):
            verifier.verify(raw)

    def test_source_digest_substitution_is_rejected(self):
        lines = self.archive.splitlines()
        idx = self.keys.index('source-inventory')
        value = strict_json(lines[idx])
        value['snapshot_sha256'] = '0' * 64
        lines[idx] = canonical(value).rstrip(b'\n')
        with self.assertRaisesRegex(EvidenceError, 'unknown source inventory'):
            verifier.verify(b'\n'.join(lines) + b'\n')

    def test_native_failure_gets_no_credit_and_cannot_also_be_a_success(self):
        value = strict_json(self.archive.splitlines()[self.keys.index('native-capabilities')])
        failure = {'web': {'error_type': 'ValueError', 'message': 'deliberate offline failure'}}
        value['blocked_groups'] = failure
        with self.assertRaisesRegex(EvidenceError, 'group membership or scope'):
            verifier.native_bindings({'native-capabilities': value})
        value.update(groups={}, repositories=[], functional_participations=0)
        self.assertEqual(verifier.native_bindings({'native-capabilities': value}), {})

    def test_two_producer_rows_credit_the_identity_once_and_reject_resealed_loss(self):
        from superhunter.product_batches import coverage
        from superhunter.product_component_controls import validate_group
        from superhunter.product_matrix import build

        # Reconstruct the accounting input from actual archived results. This exercise
        # checks the evidence consumer only, and must not be counted as a producer run.
        docs = {k: strict_json(b'{"r":' + line + b'}')['r']
                for k, line in zip(self.keys, self.archive.splitlines(), strict=True)}
        repos = {r['repository'].casefold(): r for r in docs.values() if isinstance(r, dict) and 'catalog_id' in r}
        index = SimpleNamespace(repos=repos, lookup=lambda name: repos[name.casefold()],
                                source_inventory=docs['source-inventory'], root_declarations=docs['root-declarations'],
                                owned_source_checks=docs['owned-source-checks'], census_header=docs['census-header'],
                                geth_header=docs['geth-census'], source_references=docs['source-references'],
                                score_comparison=docs['score-comparison'], fork_headers=docs['fork-headers'])
        results = strict_json((ROOT/'superhunter/product_supply/formats-batch.json').read_bytes())
        for name, receipt in validate_group('object-format', results).items():
            repos[name.casefold()]['component_control_receipt'] = receipt
        docs['component-controls'] = {'requested': ['object-format'], 'blocked': {},
                                      'observations': results, 'digest_corroboration': {}}
        docs['integration-matrix'] = build(index)
        docs['integration-coverage'] = coverage(index)

        def transcript():
            return b''.join(canonical(value) for value in docs.values())

        verified = verifier.verify(transcript())
        self.assertEqual((verified['session'], verified['operations'], verified['multiple_operations']), (71, 72, 1))
        caps = index.lookup('capstone-engine/capstone')['catalog_id'] - 1
        docs['integration-matrix']['rows'][caps]['session_operations'].pop()
        docs['integration-coverage']['identities'][caps]['session_operations'].pop()
        docs['integration-matrix'].update(session_operation_count=71, session_multi_operation_repositories=0)
        with self.assertRaisesRegex(EvidenceError, 'operation ledger'):
            verifier.verify(transcript())

    def test_duplicate_or_out_of_order_supplemental_responses_are_rejected(self):
        lines = self.archive.splitlines()
        for tail in ([lines[-1], lines[-1]], [lines[-2], lines[-3], lines[-1]]):
            with self.subTest():
                raw = b'\n'.join(lines[:-3] + tail) + b'\n'
                with self.assertRaisesRegex(EvidenceError, 'missing or extra responses'):
                    verifier.verify(raw)
