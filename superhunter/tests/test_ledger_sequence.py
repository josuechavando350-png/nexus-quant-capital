"""Tests on declared own-model ledgers; no blockchain, contracts or exploits."""
from contextlib import redirect_stdout
from copy import deepcopy
from decimal import localcontext
from fractions import Fraction
import io
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from superhunter import ledger_sequence as ls
from superhunter import balance_reconciliation as accounting
from superhunter.safe_io import canonical, strict_json


class LedgerSequenceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.ledger, self.order = ls.example_input()

    def refresh(self):
        self.order['ledger_sha256'] = ls.sha(canonical(self.ledger))

    def result(self):
        return ls.analyze(self.ledger, self.order)

    def pins(self):
        return {'ledger_pin': ls.sha(canonical(self.ledger)), 'sequence_pin': ls.sha(canonical(self.order))}

    def make(self):
        return ls.create(canonical(self.ledger), canonical(self.order), self.root/'case', **self.pins())

    def change(self, filename, transform):
        p = self.root/'case'/filename
        value = strict_json(p.read_bytes()); transform(value); raw = canonical(value); p.write_bytes(raw)
        marker = strict_json((p.parent/'COMPLETE.json').read_bytes())
        marker['sha256'][filename] = ls.sha(raw)
        (p.parent/'COMPLETE.json').write_bytes(canonical(marker))

    def reverse_order(self):
        self.order['entries'][0]['position'], self.order['entries'][1]['position'] = 1, 0

    def test_valid_order_and_intermediate_balances(self):
        result = self.result()
        self.assertEqual(result['status'], 'LEDGER_SEQUENCE_CONSISTENT')
        self.assertEqual(result['last_supported_state'], self.ledger['after'])
        self.assertEqual(result['steps_applied'], 2)
        self.assertEqual(result['trace'][1]['source_balance_atomic'], '7')
        self.assertTrue(result['full_replay_complete'])

    def test_equal_totals_do_not_prove_possible_prefix(self):
        good = self.result()
        self.reverse_order()
        bad = self.result()
        self.assertEqual(good['aggregate_status'], bad['aggregate_status'])
        self.assertEqual(bad['aggregate_status'], 'ACCOUNTING_RECONCILED')
        self.assertEqual(bad['status'], 'LEDGER_SEQUENCE_CONTRADICTION')
        self.assertEqual(bad['first_contradiction']['contradictions'], ['INSUFFICIENT_DECLARED_BALANCE'])
        self.assertEqual(bad['steps_applied'], 0)
        self.assertEqual(bad['steps_not_attempted'], 1)
        self.assertEqual(bad['last_supported_state'], self.ledger['before'])
        self.assertEqual(bad['trace'][0]['before_sha256'], bad['trace'][0]['after_sha256'])

    def test_array_order_not_assumed_as_transaction_order(self):
        expected = self.result()
        self.ledger['flows'].reverse(); self.order['entries'].reverse(); self.refresh()
        actual = self.result()
        for key in ('trace', 'status', 'last_supported_state'):
            self.assertEqual(expected[key], actual[key])

    def test_unknown_order_does_not_execute_arbitrary_prefix(self):
        self.order['order_coverage'] = 'unknown'
        result = self.result()
        self.assertEqual(result['status'], 'LEDGER_SEQUENCE_INCONCLUSIVE')
        self.assertEqual(result['trace'], [])
        self.assertEqual(result['steps_not_attempted'], 2)
        self.assertIn('ORDER_UNKNOWN', result['inconclusive_reasons'])

    def test_missing_flows_do_not_prove_a_production_failure(self):
        self.reverse_order(); self.ledger['flow_coverage'] = 'declared_incomplete'; self.refresh()
        result = self.result()
        self.assertEqual(result['status'], 'LEDGER_SEQUENCE_INCONCLUSIVE')
        self.assertIsNotNone(result['first_contradiction'])
        self.assertFalse(result['vulnerability_confirmed'])

    def test_budget_does_not_certify_unseen_suffix(self):
        self.order['steps_budget'] = 1
        result = self.result()
        self.assertEqual(result['status'], 'LEDGER_SEQUENCE_INCONCLUSIVE')
        self.assertEqual(result['steps_applied'], 1)
        self.assertEqual(result['steps_not_attempted'], 1)
        self.assertFalse(result['full_replay_complete'])
        self.assertEqual(result['final_differences'], [])

    def test_zero_budget_is_recorded(self):
        self.order['steps_budget'] = 0
        result = self.result()
        self.assertEqual(result['status'], 'LEDGER_SEQUENCE_INCONCLUSIVE')
        self.assertEqual(result['steps_attempted'], 0)

    def test_early_contradiction_not_hidden_by_remaining_budget(self):
        self.reverse_order(); self.order['steps_budget'] = 1
        result = self.result()
        self.assertEqual(result['status'], 'LEDGER_SEQUENCE_CONTRADICTION')
        self.assertEqual(result['steps_not_attempted'], 1)

    def test_overflow_cannot_be_repaired_by_a_later_debit(self):
        self.ledger['before']['usd6'] = {'vault': '1', 'alice': str(ls.LIMIT), 'fee': '0'}
        self.ledger['after'] = deepcopy(self.ledger['before'])
        self.ledger['flows'] = [
            {'id': 'fund', 'asset': 'usd6', 'from': 'vault', 'to': 'alice', 'amount_atomic': '1'},
            {'id': 'send', 'asset': 'usd6', 'from': 'alice', 'to': 'vault', 'amount_atomic': '1'}]
        self.refresh(); result = self.result()
        self.assertEqual(result['aggregate_status'], 'ACCOUNTING_RECONCILED')
        self.assertEqual(result['status'], 'LEDGER_SEQUENCE_CONTRADICTION')
        self.assertEqual(result['first_contradiction']['contradictions'], ['UINT256_BALANCE_OVERFLOW'])
        self.assertEqual(result['steps_applied'], 0)

    def test_values_above_float_precision_remain_exact(self):
        amount = 2**200 + 1
        self.ledger['before']['usd6']['vault'] = str(amount)
        self.ledger['flows'][0]['amount_atomic'] = str(amount)
        self.ledger['flows'][1]['amount_atomic'] = str(amount)
        self.ledger['after']['usd6'].update(vault='0', fee=str(amount))
        self.refresh(); result = self.result()
        self.assertEqual(result['status'], 'LEDGER_SEQUENCE_CONSISTENT')
        self.assertEqual(result['trace'][1]['source_balance_atomic'], str(amount))

    def test_single_unit_shortfall_not_rounded_away(self):
        self.ledger['flows'][1]['amount_atomic'] = '8'
        self.ledger['after']['usd6']['fee'] = '8'
        self.refresh(); result = self.result()
        self.assertEqual(result['first_contradiction']['source_balance_atomic'], '7')
        self.assertEqual(result['steps_applied'], 1)

    def test_terminal_mismatch_distinct_from_prefix_failure(self):
        self.ledger['after']['usd6']['fee'] = '8'; self.refresh()
        result = self.result()
        self.assertTrue(result['full_replay_complete'])
        self.assertIsNone(result['first_contradiction'])
        self.assertEqual(result['final_differences'][0]['delta_atomic'], '1')
        self.assertEqual(result['status'], 'LEDGER_SEQUENCE_CONTRADICTION')

    def test_external_credit_and_debit_have_declared_boundary_only(self):
        self.ledger['flows'][0]['from'] = None
        self.ledger['flows'][1]['to'] = None
        self.ledger['after'] = deepcopy(self.ledger['before']); self.refresh()
        result = self.result()
        self.assertEqual(result['status'], 'LEDGER_SEQUENCE_CONSISTENT')
        self.assertIsNone(result['trace'][0]['source_balance_atomic'])
        self.assertIsNone(result['trace'][1]['destination_balance_atomic'])
        self.assertFalse(result['chain_state_authenticated'])

    def test_empty_declared_ledger_checks_only_unchanged_state(self):
        self.ledger['flows'] = []; self.ledger['after'] = deepcopy(self.ledger['before'])
        self.order['entries'] = []; self.order['steps_budget'] = 0; self.refresh()
        self.assertEqual(self.result()['status'], 'LEDGER_SEQUENCE_CONSISTENT')
        self.ledger['after']['usd6']['vault'] = '11'; self.refresh()
        self.assertEqual(self.result()['status'], 'LEDGER_SEQUENCE_CONTRADICTION')

    def test_order_identity_requires_exact_ledger(self):
        self.order['ledger_sha256'] = '0'*64
        with self.assertRaisesRegex(ls.SequenceError, 'LEDGER_IDENTITY_MISMATCH'):
            self.result()

    def test_order_cannot_omit_or_add_a_movement(self):
        self.order['entries'].pop()
        with self.assertRaisesRegex(ls.SequenceError, 'EXACT_FLOW_SET'):
            self.result()
        self.order['entries'].append({'flow_id': 'extra', 'position': 1})
        with self.assertRaisesRegex(ls.SequenceError, 'EXACT_FLOW_SET'):
            self.result()

    def test_duplicate_identity_and_position_rejected(self):
        for field in ('flow_id', 'position'):
            old = deepcopy(self.order)
            self.order['entries'][1][field] = self.order['entries'][0][field]
            with self.subTest(field=field), self.assertRaises(ls.SequenceError):
                self.result()
            self.order = old

    def test_boolean_not_integer_metadata(self):
        for where, key in ((self.order, 'schema_version'), (self.order, 'steps_budget'),
                            (self.order['entries'][0], 'position')):
            old = where[key]; where[key] = True
            with self.subTest(key=key), self.assertRaises(ls.SequenceError):
                self.result()
            where[key] = old

    def test_unsupported_semantics_rejected(self):
        self.order['profile'] = 'credit-and-rebase-model'
        with self.assertRaisesRegex(ls.SequenceError, 'UNSUPPORTED'):
            self.result()

    def test_order_extra_fields_rejected(self):
        self.order['entries'][0]['execute'] = 'never'
        with self.assertRaises(ls.SequenceError):
            self.result()

    def test_input_objects_not_changed(self):
        before = canonical({'l': self.ledger, 's': self.order})
        self.result()
        self.assertEqual(before, canonical({'l': self.ledger, 's': self.order}))

    def test_reference_does_not_call_primary(self):
        with patch.object(ls, '_primary', side_effect=AssertionError('primary invoked')):
            expected = ls._reference(self.ledger, self.order)
        self.assertEqual(expected['last_supported_state'], self.ledger['after'])

    def test_reference_disagreement_prevents_bundle(self):
        fake = ls._reference(self.ledger, self.order)
        fake['last_supported_state']['usd6']['fee'] = '8'
        with patch.object(ls, '_reference', return_value=fake), self.assertRaisesRegex(ls.SequenceError, 'DISAGREE'):
            self.make()
        self.assertFalse((self.root/'case').exists())

    def test_global_decimal_context_cannot_alter_result(self):
        expected = self.result()
        with localcontext() as context:
            context.prec = 2; context.Emax = 2; context.Emin = -2
            context.traps[__import__('decimal').Inexact] = True
            self.assertEqual(self.result(), expected)

    def test_price_absence_does_not_invent_valuation(self):
        result = self.result()
        self.assertEqual(result['status'], 'LEDGER_SEQUENCE_CONSISTENT')
        for key in ('attacker_profit_usd', 'funds_at_risk_usd', 'final_severity'):
            self.assertNotIn(key, result)

    def test_no_network_or_code_execution(self):
        with patch('socket.socket', side_effect=AssertionError('network')), \
             patch('subprocess.run', side_effect=AssertionError('subprocess')):
            self.make(); ls.verify(self.root/'case', **self.pins())

    def test_native_audit_records_each_attempt(self):
        native = ls.load_components()
        with patch.object(native.audit.AuditLog, 'append', autospec=True,
                          side_effect=native.audit.AuditLog.append) as append:
            self.make()
        self.assertEqual(append.call_count, 4)

    def test_complete_private_roundtrip(self):
        first = self.make(); self.assertEqual(first, ls.verify(self.root/'case', **self.pins()))
        self.assertEqual((self.root/'case').stat().st_mode & 0o777, 0o700)
        for p in (self.root/'case').iterdir():
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.root/'case/ledger.json').read_bytes(), canonical(self.ledger))

    def test_original_noncanonical_whitespace_preserved(self):
        raw = json.dumps(self.ledger, indent=4).encode()
        ls.create(raw, canonical(self.order), self.root/'case', **self.pins())
        self.assertEqual((self.root/'case/ledger.json').read_bytes(), raw)

    def test_external_reviewer_pins_mandatory(self):
        self.make()
        with self.assertRaisesRegex(ls.SequenceError, 'EXTERNAL_IDENTITY'):
            ls.verify(self.root/'case', ledger_pin='0'*64, sequence_pin=self.pins()['sequence_pin'])
        with self.assertRaises(TypeError):
            ls.verify(self.root/'case')

    def test_resealed_result_cannot_claim_success(self):
        self.reverse_order(); self.make()
        self.change('result.json', lambda d: d.update(status='LEDGER_SEQUENCE_CONSISTENT'))
        with self.assertRaisesRegex(ls.SequenceError, 'RESULT_REPLAY_MISMATCH'):
            ls.verify(self.root/'case', **self.pins())

    def test_resealed_truncation_of_trace_rejected(self):
        self.make(); self.change('result.json', lambda d: d['trace'].pop())
        with self.assertRaisesRegex(ls.SequenceError, 'RESULT_REPLAY_MISMATCH'):
            ls.verify(self.root/'case', **self.pins())

    def test_changed_order_cannot_rebind_to_original_pins(self):
        self.make()
        self.change('sequence.json', lambda d: d['entries'][0].update(position=42))
        with self.assertRaisesRegex(ls.SequenceError, 'EXTERNAL_IDENTITY_MISMATCH'):
            ls.verify(self.root/'case', **self.pins())

    def test_audit_cannot_reassign_result(self):
        self.make(); self.change('audit.json', lambda d: d['entries'][-1]['data'].update(result_sha256='0'*64))
        with self.assertRaisesRegex(ls.SequenceError, 'AUDIT_SEMANTICS'):
            ls.verify(self.root/'case', **self.pins())

    def test_untracked_extra_file_rejected(self):
        self.make(); (self.root/'case/extra').write_text('untracked')
        with self.assertRaisesRegex(ls.SequenceError, 'UNDECLARED'):
            ls.verify(self.root/'case', **self.pins())

    def test_missing_marker_rejected(self):
        self.make(); (self.root/'case/COMPLETE.json').unlink()
        with self.assertRaises(OSError):
            ls.verify(self.root/'case', **self.pins())

    def test_symlink_artifact_rejected(self):
        self.make(); p = self.root/'case/ledger.json'; raw = p.read_bytes(); p.unlink()
        (self.root/'elsewhere').write_bytes(raw); p.symlink_to(self.root/'elsewhere')
        with self.assertRaises((OSError, ValueError)):
            ls.verify(self.root/'case', **self.pins())

    def test_no_overwrite_or_output_inside_checkout(self):
        self.make()
        with self.assertRaisesRegex(ls.SequenceError, 'OUTPUT_EXISTS'):
            self.make()
        with self.assertRaisesRegex(ls.SequenceError, 'OUTPUT_INSIDE_CODE'):
            ls.create(canonical(self.ledger), canonical(self.order), ls.ROOT/'generated-should-not-exist', **self.pins())

    def test_invalid_original_json_rejected(self):
        with self.assertRaises(ValueError):
            ls.create(b'{"schema_version":1,"schema_version":2}', canonical(self.order), self.root/'x', **self.pins())

    def test_stale_code_identity_rejected(self):
        self.make()
        with patch.object(ls, 'identity', return_value={'changed': True}), self.assertRaisesRegex(ls.SequenceError, 'STALE_ENGINE'):
            ls.verify(self.root/'case', **self.pins())

    def test_all_controls_have_computed_results(self):
        out = self.root/'controls'; result = ls.run_controls(out)
        self.assertEqual(result, ls.verify_controls(out))
        self.assertEqual(result['cases_checked'], 4)
        self.assertEqual(result['results']['funds_late']['aggregate_status'], 'ACCOUNTING_RECONCILED')

    def test_changed_control_even_when_resealed_is_rejected(self):
        out = self.root/'controls'; ls.run_controls(out)
        (out/'ordered/sequence.json').write_bytes(canonical({'changed': True}))
        with self.assertRaisesRegex(ls.SequenceError, 'CONTROL_INPUT_CHANGED'):
            ls.verify_controls(out)

    def test_cli_runs_real_separate_processes(self):
        (self.root/'ledger.json').write_bytes(canonical(self.ledger))
        (self.root/'sequence.json').write_bytes(canonical(self.order))
        suffix = ['--ledger-sha256', self.pins()['ledger_pin'], '--sequence-sha256', self.pins()['sequence_pin']]
        for args in (['replay-ledger', '--ledger', str(self.root/'ledger.json'), '--sequence', str(self.root/'sequence.json'),
                      '--out', str(self.root/'case')] + suffix,
                     ['verify-ledger-replay', '--bundle', str(self.root/'case')] + suffix):
            run = subprocess.run([sys.executable, '-B', '-m', 'superhunter', *args], cwd=ls.ROOT.parent,
                                 capture_output=True, text=True, timeout=20)
            self.assertEqual(run.returncode, 0, run.stdout+run.stderr)
            self.assertFalse(json.loads(run.stdout)['vulnerability_confirmed'])

    def test_cli_failures_private_and_nonzero(self):
        args = ['verify-ledger-replay', '--bundle', str(self.root/'PRIVATE_PATH'),
                '--ledger-sha256', '0'*64, '--sequence-sha256', '1'*64]
        with redirect_stdout(io.StringIO()) as stream:
            self.assertEqual(ls.main(args), 2)
        self.assertNotIn('PRIVATE_PATH', stream.getvalue())
        with patch('sys.stderr', new_callable=io.StringIO) as stream, self.assertRaises(SystemExit):
            ls.main(args + ['--unknown', 'PRIVATE_VALUE'])
        self.assertNotIn('PRIVATE_VALUE', stream.getvalue())

    def test_seeded_orders_against_independent_fraction_oracle(self):
        rng = random.Random(20261104)
        for example in range(96):
            model = deepcopy(self.ledger)
            initial = {u: rng.randrange(20) for u in model['accounts']}
            state = dict(initial); flows = []
            for index in range(12):
                src, dst = rng.sample(model['accounts'], 2)
                if state[src] == 0:
                    continue
                value = rng.randint(1, state[src])
                flows.append({'id': f'f{index}', 'asset': 'usd6', 'from': src, 'to': dst, 'amount_atomic': str(value)})
                state[src] -= value; state[dst] += value
            model['before'] = {'usd6': {u: str(v) for u, v in initial.items()}}
            model['after'] = {'usd6': {u: str(v) for u, v in state.items()}}
            model['flows'] = flows
            permuted = list(flows)
            if example % 2:
                rng.shuffle(permuted)
            order = {'schema_version': 1, 'profile': ls.PROFILE, 'ledger_sha256': ls.sha(canonical(model)),
                     'order_coverage': 'declared_total', 'steps_budget': 2048,
                     'entries': [{'flow_id': f['id'], 'position': i} for i, f in enumerate(permuted)]}
            expected = {u: Fraction(v) for u, v in initial.items()}; first_bad = None
            for i, flow in enumerate(permuted):
                value = Fraction(flow['amount_atomic'])
                if expected[flow['from']] < value:
                    first_bad = i; break
                expected[flow['from']] -= value; expected[flow['to']] += value
            result = ls.analyze(model, order)
            with self.subTest(example=example):
                self.assertEqual(result['status'], 'LEDGER_SEQUENCE_CONSISTENT' if first_bad is None else 'LEDGER_SEQUENCE_CONTRADICTION')
                self.assertEqual(result['steps_applied'], len(permuted) if first_bad is None else first_bad)
                self.assertEqual(result['last_supported_state']['usd6'], {u: str(int(v)) for u,v in expected.items()})


if __name__ == '__main__':
    unittest.main()
