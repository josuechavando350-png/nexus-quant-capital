"""Check precision of the fixed NQC source/stub call contract."""
import json
from pathlib import Path
import unittest

from superhunter import product_static_contracts as profile


class ReaderContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = json.loads((profile.ROOT/'superhunter/product_supply/static-contracts.json').read_bytes())
        cls.source = profile.pinned(profile.ROOT, profile.OWNED, profile.OWNED_SHA).decode()
        cls.actual = (Path('evidence'), 'header.json')

    def test_replayed_input_contract_has_total_case_coverage(self):
        interfaces = self.rows[profile.PYSA]['result']['interfaces']
        decisions = self.rows[profile.INFER]['result']['decisions']
        self.assertEqual(set(interfaces), set(profile.STUBS))
        self.assertEqual(set(decisions), set(profile.STUBS))
        self.assertEqual(self.rows[profile.CPG]['result']['interfaces_sha256'], profile.sha(profile.canonical(interfaces)))
        for label, stub in profile.STUBS.items():
            with self.subTest(label=label):
                oracle = profile.oracle(self.source, stub, self.actual)
                self.assertEqual(oracle['binds'], decisions[label]['positional_call_binds'])
                self.assertEqual(oracle['infer'], decisions[label]['type_diagnostic'])
                self.assertEqual(oracle['binds'] and oracle['accepts_types'], decisions[label]['accepted'])

    def test_positional_call_accepts_renames_but_rejects_keyword_only_parameter(self):
        for label in ('renamed_parameter', 'positional_only'):
            self.assertTrue(profile.oracle(self.source,profile.STUBS[label],self.actual)['binds'])
        self.assertFalse(profile.oracle(self.source,profile.STUBS['keyword_only'],self.actual)['binds'])

    def test_missing_annotation_and_missing_slot_have_different_witnesses(self):
        decisions = self.rows[profile.INFER]['result']['decisions']
        self.assertEqual(decisions['untyped_parameter']['type_diagnostic'], 'Null value')
        self.assertEqual(decisions['missing_parameter']['type_diagnostic'], 'Key not found')
        self.assertEqual(decisions['nullable_result']['type_diagnostic'], 'nullable output')

    def test_broken_stub_blocks_instead_of_falling_back(self):
        evidence = self.rows[profile.PYSA]['result']['interfaces']['broken_stub']
        self.assertFalse(evidence['parsed'])
        self.assertEqual(evidence['selected'], 'safe_io.pyi')

    def test_rejects_unrecognised_frontend_argument_map(self):
        with self.assertRaisesRegex(profile.EvidenceError, 'argument record'):
            profile.cpg_fields({profile.FRONT+'Python.kt':b'', profile.FRONT+'DeclarationHandler.kt':b''})
