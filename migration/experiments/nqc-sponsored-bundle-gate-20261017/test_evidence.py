"""Independent failure-oriented assertions on receipts, state diffs and accounting."""
import copy
import json
import unittest
from local_node import HERE, ref
from economics import evaluate, comparable_state
from reconcile_flows import reconcile
from run_coordinated import diff_balances

def read(name):return json.loads((HERE/'evidence'/f'{name}.json').read_text())

class EvidenceTests(unittest.TestCase):
    def test_separate_blocks_and_one_block_have_identical_charged_gas(self):
        a=read('A1_six_blocks');b=read('A2_C1_zero_cash')
        self.assertEqual(len({t['receipt']['blockHash'] for t in a['transactions']}),6)
        self.assertEqual(len({t['receipt']['blockHash'] for t in b['transactions']}),1)
        self.assertEqual([int(t['receipt']['transactionIndex'],16) for t in b['transactions']],list(range(6)))
        self.assertEqual([t['gas_cost_wei'] for t in a['transactions']],[t['gas_cost_wei'] for t in b['transactions']])
        self.assertEqual(sum(int(t['receipt']['gasUsed'],16) for t in b['transactions']),2339206)

    def test_pool_override_does_not_fund_or_include_unfunded_transaction(self):
        rows=read('pool-admission-probe')
        self.assertIn('Insufficient funds',rows[0]['transactions'][-1]['error'])
        self.assertEqual(sum(bool(t.get('receipt')) for t in rows[2]['transactions']),2)
        self.assertIsNone(rows[3]['transactions'][0]['receipt'])
        self.assertEqual(rows[3]['final'][ref.addr(0x1003)]['ETH'],0)

    def test_every_coordinated_step_has_independent_state_diff_and_reconciles(self):
        for item in read('run-index')['runs']:
            r=read(item['scenario']);evaluate(r)
            for t in r['transactions']:
                if 'state_diff' in t:
                    self.assertEqual(diff_balances(t['before'],t['state_diff'],r['actors']),t['after'])

    def test_receipt_corruption_and_storage_corruption_are_rejected(self):
        r=read('A2_C1_zero_cash');bad=copy.deepcopy(r)
        bad['transactions'][0]['receipt']['gasUsed']=hex(21001)
        with self.assertRaises(AssertionError):reconcile(bad)
        bad=copy.deepcopy(r);t=bad['transactions'][0]
        t['state_diff']['post'][r['actors']['nqc_sender_and_beneficiary']]['balance']='0x1'
        self.assertNotEqual(diff_balances(t['before'],t['state_diff'],r['actors']),t['after'])
        with self.assertRaises(AssertionError):evaluate(bad)

    def test_same_state_and_C2_total_costs_include_all_first_deployments(self):
        a=read('A2_C1_cash8');b=read('C2a_cash8')
        self.assertEqual(comparable_state(a),comparable_state(b))
        self.assertEqual(a['transactions'][0]['block']['timestamp'],b['transactions'][0]['block']['timestamp'])
        self.assertEqual(len(b['transactions']),8)
        self.assertEqual(sum(int(t['receipt']['gasUsed'],16) for t in b['transactions']),5196129)
        self.assertEqual(evaluate(a)['nqc']['liquidation_generated_WETH'],evaluate(b)['nqc']['liquidation_generated_WETH'])
        self.assertLess(evaluate(b)['sponsor']['cash_margin_wei'],evaluate(a)['sponsor']['cash_margin_wei'])
        self.assertEqual(b['post_call_authorizations']['general_morpho_allowance'],2**256-1)

    def test_flash_cash_failure_is_not_refunded_deployment_or_whole_block_rollback(self):
        for name in ('C2b_cash0','C2b_cash_below'):
            r=read(name);l=evaluate(r)
            self.assertEqual(int(next(t for t in r['transactions'] if t['label']=='liquidate')['receipt']['status'],16),0)
            self.assertEqual(r['initial']['position'],r['final']['position'])
            self.assertTrue(all(int(t['receipt']['status'],16)==1 for t in r['transactions'] if 'to' not in t['request']))
            self.assertLess(l['sponsor']['cash_margin_wei'],0)
            self.assertFalse(l['policy']['admitted_under_measured_and_explicit_lab_costs'])

    def test_financier_loss_is_rejected_even_with_positive_NQC_WETH(self):
        for name in ('A2_C1_high_gas','A3_excess_no_return'):
            l=evaluate(read(name))
            self.assertGreater(l['nqc']['liquidation_generated_WETH'],0)
            self.assertLess(l['sponsor']['cash_margin_wei'],0)
            self.assertFalse(l['policy']['admitted_under_measured_and_explicit_lab_costs'])
        self.assertEqual(evaluate(read('A2_C1_high_gas'))['sponsor']['cash_margin_wei'],-1123326000000000)

    def test_failed_return_does_not_count_as_received_U(self):
        r=read('A3_return_reject');t=next(t for t in r['transactions'] if t['label']=='return_unused_advance')
        self.assertEqual(int(t['receipt']['status'],16),0)
        self.assertGreater(t['gas_cost_wei'],0)
        l=evaluate(r);self.assertEqual(l['sponsor']['U_actually_returned_wei'],0)
        self.assertGreater(l['nqc']['native_retained_advance_wei'],0)

    def test_fee_cap_and_actual_price_are_not_interchangeable(self):
        r=read('A3_fee_discrepancy');l=evaluate(r)
        self.assertEqual(r['accepted_not_included'][0]['label'],'return_unused_advance')
        tx=r['accepted_not_included'][0]['request'];needed=int(tx['value'],16)+int(tx['gas'],16)*int(tx['maxFeePerGas'],16)
        self.assertGreater(needed,r['final']['balances'][tx['from']]['ETH'])
        self.assertFalse(l['policy']['admitted_under_measured_and_explicit_lab_costs'])

    def test_policy_floor_and_priority_are_not_EVM_atomicity(self):
        l=evaluate(read('A3_low_tip'))
        self.assertTrue(l['EVM_liquidation_local_pass'])
        self.assertIn('hypothetical_proposer_tip_not_met',l['policy']['rejection_reasons'])
        r=read('A3_priority_change');labels=[t['label'] for t in r['transactions']]
        # Anvil's actual fee order moves payment before U, NOT necessarily before liquidation.
        # Do not replace observed scheduling with an assumption about priority ordering.
        self.assertLess(labels.index('separate_builder_fee'),labels.index('return_unused_advance'))
        base=[t['label'] for t in read('A2_C1_zero_cash')['transactions']]
        self.assertNotEqual(labels,base)

    def test_omitted_deployment_empty_address_call_success_is_not_liquidation(self):
        r=read('A3_omit_deploy');t=next(t for t in r['transactions'] if t['label']=='liquidate')
        self.assertEqual(int(t['receipt']['status'],16),1)
        self.assertFalse(evaluate(r)['EVM_liquidation_local_pass'])
        self.assertEqual(r['initial']['position'],r['final']['position'])

    def test_reproduced_dust_and_underpayment_controls(self):
        d=read('R003_dust');ex=d['actors']['nqc_executor']
        self.assertEqual(d['final']['balances'][ex],{'ETH':10**18,'WETH':10**18,'COLLATERAL':10**18})
        self.assertEqual(evaluate(d)['nqc']['liquidation_generated_WETH'],159365645570551238)
        r=read('R003_one_wei_underpay')
        self.assertFalse(evaluate(r)['EVM_liquidation_local_pass'])
        self.assertEqual(r['initial']['position'],r['final']['position'])

    def test_selection_policy_rejects_without_selected_transactions(self):
        for r in read('policy-exclusion'):
            self.assertEqual(r['selected_block']['transactions'],[])
            self.assertEqual(r['before']['balances'],r['after']['balances'])
            self.assertFalse(r['policy']['admitted_under_measured_and_explicit_lab_costs'])

    def test_sources_and_unknowns_cannot_be_promoted_to_commercial_pass(self):
        parity=read('bytecode-parity');self.assertTrue(parity['all_C1_creation_bytecodes_equal_corrected_003'])
        self.assertEqual(parity['bytecode_sha256']['Morpho'],'a73008812cf3c42dd17d5e7521b85b975813e430103ebb072f803a368a5113e3')
        for item in read('run-index')['runs']:
            l=evaluate(read(item['scenario']))
            self.assertIsNone(l['policy']['real_builder_acceptance'])
            self.assertIsNone(l['expected_monthly_profit'])
            self.assertEqual(l['realized_nqc_pnl_usd'],'0')

if __name__=='__main__':unittest.main()
