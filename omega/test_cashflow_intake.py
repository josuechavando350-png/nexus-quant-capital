import copy
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from cashflow_intake import (EVIDENCE, build_cashflow, load_price, query_cashflow,
                             store_cashflow, verify_cashflow)
from evidence_store import admit, create, export_store, read_batch, restore_store, revoke
from integrity import canonical, digest, strict_json


class CashflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.report=build_cashflow()

    def test_real_nine_bound_to_actual_liquidators_and_ranked_price_sample(self):
        r=self.report
        self.assertEqual(r['summary']['transaction_count'],9)
        self.assertEqual(r['summary']['preblock_priced_count'],2)
        self.assertEqual(r['summary']['priced_ranks'],[1,3])
        self.assertTrue(all(x['liquidator_address'] for x in r['records']))
        self.assertEqual(r['records'][0]['gross_delta_minus_full_transaction_gas_wei'],'96136430295441074')

    def test_full_transaction_gas_charged_once_and_raw_amounts_exact(self):
        for r in self.report['records']:
            gross=int(r['weth_collateral_wei'])-int(r['weth_debt_wei'])
            self.assertEqual(str(gross),r['same_asset_gross_delta_wei'])
            self.assertEqual(str(gross-int(r['full_transaction_gas_wei'])),r['gross_delta_minus_full_transaction_gas_wei'])

    def test_seven_unpriced_rows_stay_null_and_no_current_price_fallback(self):
        rows=[r for r in self.report['records'] if r['preblock_price_reference'] is None]
        self.assertEqual(len(rows),7)
        self.assertTrue(all(r['gross_minus_gas_usd_wad_at_preblock_reference'] is None for r in rows))

    def test_hypothetical_fee_is_never_an_observed_cost(self):
        for r in self.report['records']:
            f=r['hypothetical_fee_sensitivity']
            self.assertFalse(f['is_observed_cost']);self.assertFalse(f['is_provider_quote'])
            self.assertEqual(int(f['fee_wei_ceil']),(int(r['weth_debt_wei'])*5+9999)//10000)

    def test_unknown_costs_and_oracle_delay_are_not_zero(self):
        for r in self.report['records']:
            for n in ('builder_payment_wei','other_observed_costs_wei','complete_net_profit_wei',
                      'complete_net_profit_usd_wad','oracle_update_block','oracle_delay_blocks'):
                self.assertIsNone(r[n])
            self.assertFalse(r['complete_costs']);self.assertFalse(r['nqc_execution'])

    def test_all_authorities_false_and_no_intratransaction_price_claim(self):
        self.assertTrue(all(v is False for v in self.report['authorities'].values()))
        self.assertFalse(self.report['prices_are_transaction_prestate'])
        self.assertFalse(self.report['price_change_is_oracle_update_proof'])

    def test_deterministic_without_network(self):
        with patch('socket.socket',side_effect=AssertionError('network forbidden')):
            self.assertEqual(verify_cashflow(self.report),self.report)

    def test_resealed_false_profit_price_or_identity_rejected(self):
        for field,value in [('complete_net_profit_wei','1'),('builder_payment_wei','0'),
                ('liquidator_address','0x'+'a'*40),('oracle_delay_blocks',0),
                ('gross_minus_gas_usd_wad_at_preblock_reference','999')]:
            with self.subTest(field=field):
                r=copy.deepcopy(self.report);r['records'][0][field]=value
                for x in r['records']:x['record_commitment_sha256']=digest(canonical({
                    k:v for k,v in x.items() if k!='record_commitment_sha256'}))
                r['report_commitment_sha256']=digest(canonical({k:v for k,v in r.items() if k!='report_commitment_sha256'}))
                with self.assertRaisesRegex(ValueError,'cashflow_differs_from_sources'):verify_cashflow(r)

    def test_missing_duplicate_or_reordered_rows_rejected(self):
        for change in (lambda r:r['records'].pop(),lambda r:r['records'].append(r['records'][0]),
                       lambda r:r['records'].reverse()):
            r=copy.deepcopy(self.report);change(r)
            with self.assertRaises(ValueError):verify_cashflow(r)

    def test_changed_archive_metadata_or_symlink_rejected(self):
        for name in ('weth-price-original.zip','weth-price-metadata.json'):
            with tempfile.TemporaryDirectory() as tmp:
                d=Path(tmp)
                for n in ('weth-price-original.zip','weth-price-metadata.json'):shutil.copyfile(EVIDENCE/n,d/n)
                (d/name).write_bytes((d/name).read_bytes()+b' ')
                with self.assertRaises(ValueError):load_price(d)
                (d/name).unlink();(d/name).symlink_to(EVIDENCE/name)
                with self.assertRaises(ValueError):load_price(d)

    def test_real_store_restore_and_revocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=create(Path(tmp)/'source.sqlite');r=store_cashflow(db)
            self.assertEqual(query_cashflow(db,r['cashflow_batch']),self.report)
            copy_db=Path(tmp)/'copy.sqlite';restore_store(copy_db,export_store(db))
            self.assertEqual(query_cashflow(copy_db,r['cashflow_batch']),self.report)
            revoke(copy_db,r['cashflow_batch'],'TEST_ONLY',b'test witness not chain evidence')
            with self.assertRaises(ValueError):query_cashflow(copy_db,r['cashflow_batch'])
            self.assertIn('cashflow-report.json',read_batch(copy_db,r['cashflow_batch'],include_revoked=True))

    def test_self_consistent_store_cannot_launder_changed_sources_or_economics(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=create(Path(tmp)/'source.sqlite');r=store_cashflow(db)
            good=read_batch(db,r['cashflow_batch'])
            for name,field in [('cashflow-report.json','complete_net_profit_wei'),
                               ('liquidator-report.json','liquidator_address'),
                               ('historical-ledger.json','winner_address')]:
                objects=dict(good);v=strict_json(objects[name])
                key='events' if name=='liquidator-report.json' else 'records'
                v[key][0][field]='0';objects[name]=canonical(v)
                batch=admit(db,objects)
                with self.assertRaises(ValueError):query_cashflow(db,batch)


if __name__=='__main__':unittest.main()
