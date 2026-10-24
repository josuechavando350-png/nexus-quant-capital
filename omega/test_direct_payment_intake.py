import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cashflow_intake import build_cashflow
from direct_payment_intake import (CAPTURE_NAME, EVIDENCE, build_report, inclusion_capture,
    load_capture, reconcile, seal, verify_report)
from historical_intake import build_ledger
from inclusion_fee_intake import build_inclusion_report
from integrity import canonical, digest, strict_json


class DirectPaymentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.capture = load_capture(); cls.cashflow = build_cashflow()
        cls.fees = build_inclusion_report(); cls.ledger = build_ledger()
        cls.observed = next(r for r in inclusion_capture()['records'] if r['rank']==1
                           and r['kind']=='transaction')['response']['data']
        cls.report = build_report()

    def altered(self, name, mutate):
        c = copy.deepcopy(self.capture); record = next(r for r in c['records'] if r['name']==name)
        body = strict_json(record['raw_body']); mutate(body)
        record['raw_body'] = canonical(body).decode(); record['raw_sha256'] = digest(record['raw_body'].encode())
        return c

    def reject(self, capture, reason):
        with self.assertRaisesRegex(ValueError, reason):
            reconcile(capture, self.cashflow, self.fees, self.ledger, self.observed)

    def test_authentic_payment_and_all_sample_identities_preserved(self):
        self.assertEqual([r['transaction_hash'] for r in self.report['records']],
                         [r['transaction_hash'] for r in self.cashflow['records']])
        w=self.report['records'][0]['direct_payment_witness']
        self.assertEqual(w['direct_fee_recipient_payment_wei'],'95915734379292898')
        self.assertEqual(w['indexed_operation_count'],57)
        self.assertEqual(w['indexed_pages'],3)
        self.assertTrue(all(r['direct_payment_witness'] is None for r in self.report['records'][1:]))

    def test_native_unwrap_split_and_payment_ratio_recompute_exactly(self):
        w=self.report['records'][0]['direct_payment_witness']
        total, payment, rest=map(int,(w['unwrap_native_transfer_wei'],w['direct_fee_recipient_payment_wei'],
                                     w['residual_native_transfer_wei']))
        self.assertEqual(payment+rest,total)
        self.assertEqual(total,int(self.cashflow['records'][0]['same_asset_gross_delta_wei']))
        self.assertEqual(w['payment_to_gross_delta_wad'],str(payment*10**18//total))
        self.assertEqual(payment,total*9975//10000)

    def test_root_value_is_separate_from_internal_payments_and_gas(self):
        w=self.report['records'][0]['direct_payment_witness']
        self.assertEqual(w['transaction_native_value_wei'],'9975')
        self.assertEqual(w['execution_gas_paid_wei'],'19694395579376')
        self.assertTrue(w['direct_payment_is_separate_from_execution_gas'])
        self.assertNotEqual(w['transaction_sender'],w['residual_recipient'])
        self.assertIsNone(w['residual_recipient_control']); self.assertFalse(w['residual_is_realized_profit'])

    def test_indexer_listing_is_not_trace_proof_or_total_builder_compensation(self):
        w=self.report['records'][0]['direct_payment_witness']
        for k in ('raw_trace_available','full_call_ancestry_proven','native_balance_reconciliation_complete',
                  'independent_trace_provider_agreement','exclusive_liquidation_cost_attribution_proven'):
            self.assertFalse(w[k])
        self.assertIsNone(w['total_builder_compensation_wei']); self.assertIsNone(w['fee_recipient_builder_identity'])

    def test_titan_policy_does_not_attribute_competitor_payment_to_titan(self):
        p=self.report['gas_funding_policy']; self.assertEqual(p['payer'],'TITAN')
        self.assertEqual(p['operator_gas_cap_mxn'],0); self.assertFalse(p['own_gas_fallback_allowed'])
        self.assertEqual(self.report['summary']['titan_covered_executions'],0)
        for r in self.report['records']:
            self.assertFalse(r['complete_costs']); self.assertFalse(r['titan_coverage_proven'])
            self.assertIsNone(r['complete_net_profit_wei']); self.assertFalse(r['nqc_execution'])

    def test_reader_reproduces_without_network(self):
        with patch('socket.socket',side_effect=AssertionError('network forbidden')):
            self.assertEqual(verify_report(self.report),self.report)

    def test_capture_changed_bytes_or_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/CAPTURE_NAME; p.write_bytes((EVIDENCE/CAPTURE_NAME).read_bytes()+b' ')
            with self.assertRaisesRegex(ValueError,'capture_changed'):load_capture(tmp)
            p.unlink();p.symlink_to(EVIDENCE/CAPTURE_NAME)
            with self.assertRaisesRegex(ValueError,'symlink_input'):load_capture(tmp)

    def test_missing_page_and_wrong_cursor_rejected(self):
        c=copy.deepcopy(self.capture);c['records'].pop(1);self.reject(c,'capture_inventory')
        c=copy.deepcopy(self.capture);c['records'][1]['url']+='x';self.reject(c,'cursor_disagreement')

    def test_truncated_nonterminal_and_unreliable_initial_count_rejected(self):
        for name, mutate, reason in (
            ('operations-0',lambda p:p.update(countType='lowerBound'),'page_coverage'),
            ('operations-0',lambda p:p.update(count=True),'page_coverage'),
            ('operations-2',lambda p:p['items'].pop(),'page_coverage'),
            ('operations-2',lambda p:p['link'].update(next='/unexpected'),'page_not_terminal')):
            self.reject(self.altered(name,mutate),reason)

    def test_duplicate_or_bool_operation_indices_rejected(self):
        for value in (True,55,900):
            self.reject(self.altered('operations-0',lambda p:p['items'][0].update(opIndex=value)),
                        'operation_inventory')

    def test_chain_hash_index_and_block_drift_rejected(self):
        for k,v in [('chainId','8453'),('id','0x'+'0'*64),('blockHash','0x'+'0'*64),('index',2),('blockNumber',True)]:
            self.reject(self.altered('transaction',lambda t:t.update({k:v})),
                        'transaction_identity' if k in ('chainId','id') else 'transaction_anchor')
        self.reject(self.altered('operations-1',lambda p:p['items'][0].update(txHash='0x'+'0'*64)),
                    'operation_anchor')

    def test_gas_and_initial_native_value_disagreement_rejected(self):
        self.reject(self.altered('transaction',lambda t:t.update(gasUsed='1')),'gas_disagreement')
        self.reject(self.altered('transaction',lambda t:t.update(value='0')),'native_value_disagreement')

    def test_failed_operation_or_noncall_value_cannot_count_as_transfer(self):
        self.reject(self.altered('operations-1',lambda p:p['items'][0].update(status=False)),
                    'operation_failed_or_unsupported')
        self.reject(self.altered('operations-0',lambda p:p['items'][1].update(type='DELEGATECALL')),
                    'transfer_inventory')

    def test_payment_recipient_and_transfer_amount_rejected_when_changed(self):
        self.reject(self.altered('operations-0',lambda p:p['items'][1].update(to='0x'+'1'*40)),
                    'transfer_role')
        self.reject(self.altered('operations-0',lambda p:p['items'][1].update(value='1')),
                    'native_split_disagreement')

    def test_same_provider_other_api_disagreement_rejected(self):
        self.reject(self.altered('value-transfers',lambda p:p['result'][1].update(value='1')),
                    'same_provider_api_disagreement')
        self.reject(self.altered('value-transfers',lambda p:p['result'][1].update(isError='1')),
                    'compat_anchor')

    def test_resealed_zero_builder_total_profit_or_titan_coverage_rejected(self):
        for key,value in [('total_builder_compensation_wei','0'),('residual_is_realized_profit',True)]:
            r=copy.deepcopy(self.report);r['records'][0]['direct_payment_witness'][key]=value
            r.pop('report_commitment_sha256');seal(r)
            with self.assertRaisesRegex(ValueError,'differs_from_sources'):verify_report(r)
        r=copy.deepcopy(self.report);r['gas_funding_policy']['execution_coverage_proven']=True
        r['gas_policy_sha256']=digest(canonical(r['gas_funding_policy']));r.pop('report_commitment_sha256');seal(r)
        with self.assertRaisesRegex(ValueError,'differs_from_sources'):verify_report(r)


if __name__=='__main__':unittest.main()
