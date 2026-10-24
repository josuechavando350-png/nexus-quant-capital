import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from flash_financing_intake import (CAPTURE_NAME,EVIDENCE,MORPHO,build_cashflow,build_execution_report,
    build_ledger,build_payments,build_report,load_capture,operation_capture,reconcile,seal,verify_report)
from integrity import canonical,digest,strict_json


class FlashFinancingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.capture=load_capture();cls.cashflow=build_cashflow();cls.payments=build_payments()
        cls.operations=operation_capture();cls.ledger=build_ledger();cls.economics=build_execution_report()
        cls.report=build_report()

    def altered(self,mutate):
        c=copy.deepcopy(self.capture);r=c['record'];body=strict_json(r['raw_body'])
        mutate(body['result']);r['raw_body']=canonical(body).decode();r['raw_sha256']=digest(r['raw_body'].encode())
        return c

    def reject(self,capture,reason,operations=None):
        with self.assertRaisesRegex(ValueError,reason):
            reconcile(capture,self.cashflow,self.payments,operations or self.operations,self.ledger,self.economics)

    def test_exact_principal_and_repayment_zero_weth_premium(self):
        w=self.report['records'][0]['financing_witness']
        self.assertEqual(w['lender_address'],MORPHO)
        self.assertEqual(w['principal_wei'],'10684013854557827871')
        self.assertEqual(w['repayment_wei'],w['principal_wei'])
        self.assertEqual(w['observed_weth_repayment_premium_wei'],'0')
        self.assertIsNone(w['other_financing_costs_wei'])

    def test_normalized_receipt_agreement_is_not_full_parity_or_code_identity(self):
        w=self.report['records'][0]['financing_witness']
        self.assertTrue(w['normalized_receipt_matches_retained_drpc'])
        for k in ('full_receipt_cross_provider_parity','lender_deployed_code_identity_verified','raw_call_ancestry_proven'):
            self.assertFalse(w[k])

    def test_original_aave_simulation_remains_distinct_from_observed_morpho_repayment(self):
        w=self.report['records'][0]['financing_witness']
        self.assertEqual(w['retained_aave_fork_fee_wei'],'5342006927278914')
        for k in ('fork_fee_is_observed_winner_fee','nqc_morpho_route_validated','nqc_cost_saving_proven','current_flash_liquidity_verified'):
            self.assertFalse(w[k])

    def test_all_sample_identities_and_unknown_rows_preserved(self):
        self.assertEqual([r['transaction_hash'] for r in self.report['records']],
                         [r['transaction_hash'] for r in self.cashflow['records']])
        self.assertTrue(all(r['financing_witness'] is None for r in self.report['records'][1:]))
        for r in self.report['records']:
            self.assertFalse(r['complete_costs']);self.assertIsNone(r['complete_net_profit_wei'])
            self.assertFalse(r['nqc_execution']);self.assertFalse(r['titan_coverage_proven'])

    def test_titan_gas_policy_does_not_change_with_principal_lender(self):
        p=self.report['gas_funding_policy'];self.assertEqual(p['payer'],'TITAN')
        self.assertEqual(p['operator_gas_cap_mxn'],0)
        for k in ('operator_prefund_allowed','own_gas_fallback_allowed','execution_coverage_proven'):self.assertFalse(p[k])
        self.assertEqual(self.report['gas_policy_sha256'],digest(canonical(p)))

    def test_report_reproduces_without_network(self):
        with patch('socket.socket',side_effect=AssertionError('network forbidden')):
            self.assertEqual(verify_report(self.report),self.report)

    def test_changed_capture_or_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/CAPTURE_NAME;p.write_bytes((EVIDENCE/CAPTURE_NAME).read_bytes()+b' ')
            with self.assertRaisesRegex(ValueError,'capture_changed'):load_capture(tmp)
            p.unlink();p.symlink_to(EVIDENCE/CAPTURE_NAME)
            with self.assertRaisesRegex(ValueError,'symlink_input'):load_capture(tmp)

    def test_wrong_chain_request_and_raw_hash_rejected(self):
        for mutate,reason in [(lambda c:c.update(chain_id=True),'capture_scope'),
            (lambda c:c['record'].update(url=c['record']['url'].replace('/evm/1/','/evm/8453/')),'request'),
            (lambda c:c['record'].update(raw_sha256='0'*64),'raw_digest')]:
            c=copy.deepcopy(self.capture);mutate(c);self.reject(c,reason)

    def test_receipt_hash_block_index_and_actors_rejected(self):
        for k,v,reason in [('transactionHash','0x'+'0'*64,'receipt_anchor'),('blockHash','0x'+'0'*64,'receipt_anchor'),
                           ('transactionIndex','0x2','receipt_anchor'),('from','0x'+'1'*40,'receipt_actors')]:
            self.reject(self.altered(lambda r:r.update({k:v})),reason)

    def test_failed_or_unsupported_receipt_rejected(self):
        for k,v in [('status','0x0'),('type','0x3'),('contractAddress',MORPHO)]:
            self.reject(self.altered(lambda r:r.update({k:v})),'receipt_status')

    def test_gas_and_aave_log_disagreement_rejected_by_original_normalizer(self):
        self.reject(self.altered(lambda r:r.update(gasUsed='0x1')),'normalized_disagreement')
        self.reject(self.altered(lambda r:r['logs'][14].update(data='0x'+'0'*256)),'logs not equal|data|log')

    def test_missing_or_duplicate_receipt_log_rejected(self):
        self.reject(self.altered(lambda r:r['logs'].pop()),'log_inventory')
        self.reject(self.altered(lambda r:r['logs'][1].update(logIndex='0x7')),'log_inventory')

    def test_removed_log_and_timestamp_drift_rejected(self):
        for k,v in [('removed',True),('blockTimestamp','0x1')]:
            self.reject(self.altered(lambda r:r['logs'][0].update({k:v})),'log_anchor')

    def test_flash_event_caller_token_and_principal_changes_rejected(self):
        for i in (1,2):
            self.reject(self.altered(lambda r:r['logs'][0]['topics'].__setitem__(i,'0x'+'0'*64)),'flash_event')
        self.reject(self.altered(lambda r:r['logs'][0].update(data='0x'+'0'*63+'1')),'principal')

    def test_premium_shortfall_and_repayment_recipient_cannot_be_hidden(self):
        for delta in (-1,1):
            self.reject(self.altered(lambda r:r['logs'][15].update(data='0x'+format(int(r['logs'][15]['data'],16)+delta,'064x'))),'principal_repayment')
        self.reject(self.altered(lambda r:r['logs'][15]['topics'].__setitem__(2,'0x'+'0'*64)),'principal_repayment')

    def test_abi_padding_and_withdrawal_disagreement_rejected(self):
        self.reject(self.altered(lambda r:r['logs'][1]['topics'].__setitem__(1,'0x1'+r['logs'][1]['topics'][1][3:])),'address_padding')
        self.reject(self.altered(lambda r:r['logs'][16].update(data='0x'+'0'*64)),'withdrawal')

    def test_callback_target_selector_or_failure_rejected(self):
        for k,v in [('to','0x'+'1'*40),('methodId','0x00000000'),('status',False)]:
            o=copy.deepcopy(self.operations)
            for record in o['records'][:3]:
                page=strict_json(record['raw_body'])
                for call in page['items']:
                    if call['opIndex']==3:call[k]=v
                record['raw_body']=canonical(page).decode();record['raw_sha256']=digest(record['raw_body'].encode())
            self.reject(self.capture,'flash_call',o)

    def test_resealed_total_zero_cost_route_profit_or_titan_claim_rejected(self):
        for k,v in [('other_financing_costs_wei','0'),('nqc_morpho_route_validated',True),('nqc_cost_saving_proven',True)]:
            r=copy.deepcopy(self.report);r['records'][0]['financing_witness'][k]=v
            r.pop('report_commitment_sha256');seal(r)
            with self.assertRaisesRegex(ValueError,'differs_from_sources'):verify_report(r)
        r=copy.deepcopy(self.report);r['gas_funding_policy']['own_gas_fallback_allowed']=True
        r['gas_policy_sha256']=digest(canonical(r['gas_funding_policy']));r.pop('report_commitment_sha256');seal(r)
        with self.assertRaisesRegex(ValueError,'differs_from_sources'):verify_report(r)


if __name__=='__main__':unittest.main()
