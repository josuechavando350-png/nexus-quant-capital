"""Receipt routing controls. Native producers have separate real execution tests."""
import copy
import argparse
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from superhunter import product_native_capabilities as native
from superhunter.product_batches import receipt
from superhunter.product_reasoning import EvidenceError
from superhunter.product_review import sha
from superhunter.safe_io import canonical


class NativeCapabilityJoinTests(unittest.TestCase):
    def setUp(self):
        self.reports = {group: {'positive': ['owned_expected'], 'negative': [], 'engine': group}
                        for group in native.MODULES}
        self.groups = {group: {'repositories': {f'owned/{group}': 'executable'},
                               'report_sha256': sha(canonical(self.reports[group]))}
                       for group in native.MODULES}
        self.record = {'schema_version': 1, 'groups': self.groups}
        self.raw = canonical(self.record)
        self.enterContext(patch.object(native, 'CONTRACT_SHA', sha(self.raw)))
        self.enterContext(patch.object(native, 'read_artifact', return_value=self.raw))
        self.index = SimpleNamespace(repos={f'owned/{group}': {'repository': f'owned/{group}'}
                                           for group in native.MODULES}, native_capabilities=None)

    def producer(self, module, package):
        group = next(k for k, v in native.MODULES.items() if module == '.' + v)
        return SimpleNamespace(REPOSITORIES=self.groups[group]['repositories'],
                               run=lambda kit: copy.deepcopy(self.reports[group]))

    def test_real_consumer_receipt_is_bound_to_registered_group_result(self):
        with patch.object(native, 'import_module', side_effect=self.producer):
            result = native.attach(self.index, {'evm': 'controlled-kit'})
        self.assertEqual(result['functional_participations'], 1)
        self.assertEqual(receipt(self.index.repos['owned/evm']), ('executable', 'native_capability_receipt'))
        self.assertNotIn('native_capability_receipt', self.index.repos['owned/web'])

    def test_wrong_or_missing_negative_result_cannot_publish_any_receipt(self):
        self.reports['web']['negative'] = ['unexpected_diagnostic']
        with patch.object(native, 'import_module', side_effect=self.producer):
            with self.assertRaisesRegex(EvidenceError, 'output differs'):
                native.attach(self.index, {'evm': 'kit-a', 'web': 'kit-b'})
        self.assertTrue(all('native_capability_receipt' not in row for row in self.index.repos.values()))
        self.assertIsNone(self.index.native_capabilities)

    def test_producer_failure_does_not_publish_a_partial_group(self):
        def producer(module, package):
            value = self.producer(module, package)
            if module == '.' + native.MODULES['web']:
                def fail(kit):
                    raise ValueError('native execution failed')
                value.run = fail
            return value
        with patch.object(native, 'import_module', side_effect=producer), self.assertRaises(ValueError):
            native.attach(self.index, {'evm': 'kit-a', 'web': 'kit-b'})
        self.assertTrue(all('native_capability_receipt' not in row for row in self.index.repos.values()))

    def test_independent_groups_survive_and_failed_replay_removes_stale_credit(self):
        with patch.object(native, 'import_module', side_effect=self.producer):
            first = native.attach(self.index, {'evm': 'kit-a', 'web': 'kit-b'})
            self.assertEqual(first['functional_participations'], 2)
            self.assertNotIn('blocked_groups', first)
            self.reports['evm']['negative'] = ['unexpected_diagnostic']
            result = native.attach(self.index, {'evm': 'kit-a', 'web': 'kit-b'}, allow_partial=True)
        self.assertEqual(result['repositories'], ['owned/web'])
        self.assertEqual(result['functional_participations'], 1)
        self.assertEqual(set(result['blocked_groups']), {'evm'})
        self.assertNotIn('native_capability_receipt', self.index.repos['owned/evm'])
        self.assertIn('native_capability_receipt', self.index.repos['owned/web'])

    def test_partial_selection_rejects_an_entire_group_if_an_identity_is_missing(self):
        self.index.repos.pop('owned/web')
        with patch.object(native, 'import_module', side_effect=self.producer):
            result = native.attach(self.index, {'evm': 'kit-a', 'web': 'kit-b'}, allow_partial=True)
        self.assertEqual(set(result['groups']), {'evm'})
        self.assertEqual(result['blocked_groups']['web']['error_type'], 'EvidenceError')
        self.assertEqual(result['repositories'], ['owned/evm'])

    def test_arbitrary_report_hash_cannot_be_counted_as_native_execution(self):
        row = self.index.repos['owned/evm']
        row['native_capability_receipt'] = native.expected_receipt('evm', 'owned/evm', self.groups['evm'])
        row['native_capability_receipt']['report_sha256'] = '0'*64
        with self.assertRaisesRegex(EvidenceError, 'accepted controls'):
            receipt(row)

    def test_metadata_only_row_stays_pending(self):
        row = {'repository': 'owned/evm', 'source_inventory': {'evidence': 'local_git_tree'}}
        self.assertEqual(receipt(row), ('pending', None))

    def test_changed_contract_is_rejected(self):
        with patch.object(native, 'read_artifact', return_value=self.raw + b' '):
            with self.assertRaisesRegex(EvidenceError, 'reviewed controls'):
                native.attach(self.index, {'evm': 'kit'})

    def test_unknown_group_and_unregistered_receipt_are_rejected(self):
        with self.assertRaisesRegex(EvidenceError, 'unknown or empty'):
            native.attach(self.index, {'unregistered': 'kit'})
        with self.assertRaisesRegex(EvidenceError, 'unregistered native'):
            receipt({'repository': 'other/tool', 'native_capability_receipt': {}})


class NativeContractHistoryTests(unittest.TestCase):
    def test_historical_domains_and_result_bindings_stay_verifiable(self):
        old = native.contracts(version=70)
        live = native.contracts()
        self.assertEqual(set(old), {'evm', 'web', 'static', 'slither', 'secrets'})
        self.assertEqual({key: live[key] for key in old if key != 'evm'},
                         {key: value for key, value in old.items() if key != 'evm'})
        self.assertNotEqual(live['evm']['report_sha256'], old['evm']['report_sha256'])
        self.assertIn('salesforce/policy_sentry', live['iam']['repositories'])
        with self.assertRaisesRegex(EvidenceError, 'unknown historical'):
            native.contracts(version=999)


class NativeKitManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'evm').mkdir()
        self.path = self.root/'kits.json'
        self.path.write_bytes(canonical({'evm': 'evm'}))
        self.parser = argparse.ArgumentParser()
        native.add_arguments(self.parser)

    def select(self, *extra):
        return native.selected_kits(self.parser.parse_args(['--native-kits', str(self.path), *extra]))

    def test_one_manifest_resolves_local_groups_relative_to_its_own_directory(self):
        self.assertEqual(self.select(), {'evm': self.root/'evm'})

    def test_manifest_and_cli_cannot_silently_override_the_same_group(self):
        with self.assertRaisesRegex(EvidenceError, 'selected twice'):
            self.select('--evm-native-kit', str(self.root/'evm'))

    def test_unknown_group_cannot_select_an_arbitrary_module(self):
        self.path.write_bytes(canonical({'unreviewed.module': 'evm'}))
        with self.assertRaisesRegex(EvidenceError, 'unknown or empty'):
            self.select()

    def test_manifest_cannot_use_a_file_as_an_executable_kit(self):
        self.path.write_bytes(canonical({'evm': 'kits.json'}))
        with self.assertRaisesRegex(EvidenceError, 'local directory'):
            self.select()
