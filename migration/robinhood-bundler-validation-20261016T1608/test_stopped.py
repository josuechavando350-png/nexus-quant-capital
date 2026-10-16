import copy
import unittest
from validation import HERE, PM, CASES, fixture, read
from run_local import genesis
from audit_stopped import audit, failed_op
from prepare_next import preserve_native_precompiles


class StoppedTests(unittest.TestCase):
    def test_actual_prefix_and_scope(self):
        result = audit(HERE/'evidence/pilot')
        self.assertEqual(result['successful_validation_cases'],0)
        self.assertFalse(result['paymaster_reached'])
        self.assertFalse(result['full_bundler_admission_proven'])

    def test_error_decoder_rejects_truncated_or_extra_data(self):
        raw = read(HERE/'evidence/pilot/04-debug_traceCall.json')['result']['calls'][-1]['data']
        for wrong in (raw[:-2], raw+'00', '0x', '0x00000000'+raw[10:]):
            with self.assertRaises(ValueError): failed_op(wrong)

    def test_proposal_preserves_signed_input_and_all_other_state(self):
        for name in CASES:
            old = fixture(name); initial = genesis()
            fresh, proposed, moved = preserve_native_precompiles(old, initial)
            self.assertEqual(fresh['transaction'], old['transaction'])
            self.assertEqual(fresh['window'], old['window'])
            self.assertEqual(fresh['stateOverrides'][PM],old['stateOverrides'][PM])
            self.assertEqual(initial,genesis())
            self.assertEqual(old,fixture(name))
            self.assertEqual(len(moved),1)
            address = moved[0]['address']
            self.assertEqual(int(address,16),1)
            self.assertEqual(proposed['alloc'][address[2:]]['balance'],old['stateOverrides'][address]['balance'])
            expected = copy.deepcopy(old['stateOverrides']); del expected[address]
            self.assertEqual(fresh['stateOverrides'],expected)

    def test_proposal_rejects_code_storage_and_moves_on_precompiles(self):
        address = '0x'+'0'*39+'1'
        for change in ({'code':'0x00'}, {'state':{'0x00':'0x01'}}, {'movePrecompileToAddress':PM}, {'unknown':0}):
            case = fixture(CASES[0]); case['stateOverrides'][address].update(change)
            with self.assertRaisesRegex(ValueError,'non-passive'): preserve_native_precompiles(case,genesis())

    def test_proposal_rejects_genesis_collision(self):
        case=fixture(CASES[0]); initial=genesis()
        initial['alloc']['0'*39+'1']={'balance':'0x0'}
        with self.assertRaisesRegex(ValueError,'collision'): preserve_native_precompiles(case,initial)

    def test_proposal_covers_shanghai_precompiles_but_keeps_arbos(self):
        case=fixture(CASES[0]); case['stateOverrides']['0x'+(9).to_bytes(20,'big').hex()]={'balance':'0x2'}
        fresh,_,moved=preserve_native_precompiles(case,genesis())
        self.assertEqual(len(moved),2)
        self.assertIn('0x'+(100).to_bytes(20,'big').hex(),fresh['stateOverrides'])
        self.assertFalse(any(1<=int(a,16)<=9 for a in fresh['stateOverrides']))


if __name__ == '__main__':
    unittest.main()
