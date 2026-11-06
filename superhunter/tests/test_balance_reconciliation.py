"""Exact accounting on constructed local records; never a vulnerability demo."""
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from superhunter import balance_reconciliation as br
from superhunter.safe_io import canonical, strict_json


class AccountingTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name);self.data=br.example_input()

    def check(self):
        return br.reconcile(self.data)

    def make(self):
        return br.create_bundle(self.data,self.root/'case')

    def alter(self, name, edit):
        root=self.root/'case';value=strict_json((root/name).read_bytes());edit(value)
        raw=canonical(value);(root/name).write_bytes(raw)
        marker=strict_json((root/'COMPLETE.json').read_bytes());marker['sha256'][name]=br.digest(raw)
        (root/'COMPLETE.json').write_bytes(canonical(marker))

    def test_known_cashflows_reconcile_exactly(self):
        r=self.check();self.assertEqual(r['status'],'ACCOUNTING_RECONCILED')
        self.assertEqual(r['cells_checked'],6);self.assertEqual(r['unexplained_cells'],0)
        by_asset={x['asset']:x for x in r['asset_totals']}
        self.assertEqual(by_asset['usd6']['external_net_atomic'],'25000000')
        self.assertEqual(by_asset['eth18']['external_net_atomic'],'-10000000000000000')
        self.assertEqual(r['declared_price_usd_total_delta'],'0')

    def test_one_atomic_unit_is_not_rounded_away(self):
        self.data['after']['usd6']['vault']='1124000001'
        r=self.check();self.assertEqual(r['status'],'ACCOUNTING_MISMATCH')
        row=next(x for x in r['rows'] if x['asset']=='usd6' and x['account']=='vault')
        self.assertEqual(row['residual_atomic'],'1')
        self.assertEqual(r['declared_price_usd_total_delta'],'0.000001')

    def test_internal_misallocation_cannot_hide_in_total(self):
        self.data['after']['usd6']['vault']='1124000001';self.data['after']['usd6']['alice']='399999999'
        r=self.check();self.assertEqual(r['unexplained_cells'],2)
        self.assertEqual(r['status'],'ACCOUNTING_MISMATCH')
        self.assertTrue(all(x['residual_atomic']=='0' for x in r['asset_totals']))

    def test_incomplete_even_when_all_residuals_zero(self):
        self.data['flow_coverage']='declared_incomplete'
        r=self.check();self.assertEqual(r['status'],'ACCOUNTING_INCONCLUSIVE');self.assertEqual(r['unexplained_cells'],0)

    def test_missing_flows_not_inferred(self):
        self.data['flows']=[f for f in self.data['flows'] if f['id']!='incoming']
        self.data['flow_coverage']='declared_incomplete'
        r=self.check();self.assertEqual(r['status'],'ACCOUNTING_INCONCLUSIVE')
        row=next(x for x in r['rows'] if x['asset']=='usd6' and x['account']=='vault')
        self.assertEqual(row['residual_atomic'],'25000000')

    def test_missing_balance_not_zero(self):
        del self.data['after']['eth18']['fee']
        with self.assertRaises(br.AccountingError):self.check()

    def test_decimals_are_required_not_assumed(self):
        del self.data['assets']['usd6']['decimals']
        with self.assertRaises(br.AccountingError):self.check()

    def test_unknown_price_keeps_usd_unknown(self):
        self.data['prices'].pop('eth18')
        r=self.check();self.assertFalse(r['valuation_complete']);self.assertIsNone(r['declared_price_usd_total_delta'])
        self.assertIsNone(next(x for x in r['rows'] if x['asset']=='eth18')['declared_price_usd_delta'])
        self.assertEqual(r['status'],'ACCOUNTING_RECONCILED')

    def test_no_prices_is_not_zero_usd(self):
        self.data['prices']={};self.assertIsNone(self.check()['declared_price_usd_total_delta'])

    def test_amounts_above_float_precision(self):
        self.data['before']['usd6']['vault']=str(2**200)
        self.data['after']['usd6']['vault']=str(2**200+124000001)
        r=self.check();self.assertEqual(r['status'],'ACCOUNTING_MISMATCH')
        row=next(x for x in r['rows'] if x['asset']=='usd6' and x['account']=='vault')
        self.assertEqual(row['residual_atomic'],'1')

    def test_maximum_decimals_exact_no_float(self):
        self.data['assets']['usd6']['decimals']=255
        r=self.check();row=next(x for x in r['rows'] if x['asset']=='usd6' and x['account']=='fee')
        self.assertEqual(row['observed_delta_tokens'],'0.'+'0'*248+'1')

    def test_zero_decimals_not_eighteen(self):
        self.data['assets']['usd6']['decimals']=0
        row=next(x for x in self.check()['rows'] if x['asset']=='usd6' and x['account']=='fee')
        self.assertEqual(row['observed_delta_tokens'],'1000000')

    def test_uint256_boundary_and_noncanonical_inputs(self):
        for value in (str(2**256),'01','-1','1.0','1e3','²',1,True):
            with self.subTest(value=type(value).__name__),self.assertRaises(br.AccountingError):br.uint(value)
        self.assertEqual(br.uint(str(2**256-1)),2**256-1)

    def test_float_price_not_accepted(self):
        self.data['prices']['usd6']['usd_per_token']=0.1
        with self.assertRaises(br.AccountingError):self.check()

    def test_price_zero_negative_exponent_nan_not_accepted(self):
        for val in ('0','-1','1e5','NaN','Infinity',' 1','00.1'):
            with self.subTest(val=val),self.assertRaises(br.AccountingError):
                self.data['prices']['usd6']['usd_per_token']=val;self.check()

    def test_decimal_price_exact(self):
        self.data['prices']['usd6']['usd_per_token']='0.123456789123456789'
        r=self.check();row=next(x for x in r['rows'] if x['asset']=='usd6' and x['account']=='fee')
        self.assertEqual(row['declared_price_usd_delta'],'0.123456789123456789')

    def test_boolean_metadata_not_integers(self):
        for place,key in ((self.data,'schema_version'),(self.data['assets']['usd6'],'decimals'),
                          (self.data['subject'],'chain_id'),(self.data['subject']['anchor'],'block_number')):
            old=place[key];place[key]=True
            with self.subTest(key=key),self.assertRaises(br.AccountingError):self.check()
            place[key]=old

    def test_duplicate_flow_rejected(self):
        self.data['flows'].append(deepcopy(self.data['flows'][0]))
        with self.assertRaisesRegex(br.AccountingError,'DUPLICATE_FLOW'):self.check()

    def test_unknown_flow_account_rejected(self):
        self.data['flows'][0]['to']='unlisted'
        with self.assertRaisesRegex(br.AccountingError,'UNKNOWN_ACCOUNT'):self.check()

    def test_unknown_asset_rejected(self):
        self.data['flows'][0]['asset']='other'
        with self.assertRaisesRegex(br.AccountingError,'UNKNOWN_ASSET'):self.check()

    def test_ambiguous_flow_endpoints_rejected(self):
        for endpoint in ('alice',None):
            self.data['flows'][0]['from']=endpoint;self.data['flows'][0]['to']=endpoint
            with self.subTest(endpoint=endpoint),self.assertRaisesRegex(br.AccountingError,'ENDPOINTS'):self.check()

    def test_no_claim_of_profit_exploit_or_authenticated_prices(self):
        r=self.check()
        for k in ('execution_verified','vulnerability_confirmed','coverage_authenticated','prices_authenticated','price_freshness_verified'):
            self.assertIs(r[k],False)
        for k in ('funds_at_risk_usd','attacker_profit_usd','final_severity'):
            self.assertIsNone(r[k])

    def test_input_is_not_mutated(self):
        before=canonical(self.data);self.check();self.assertEqual(before,canonical(self.data))

    def test_reference_does_not_call_primary(self):
        with patch.object(br,'_primary',side_effect=AssertionError):
            r=br._reference(br.validate(self.data))
        self.assertEqual(r['declared_price_usd_total_delta'],'0')

    def test_disagreement_blocks_evidence(self):
        fake=br._reference(self.data);fake['rows'][0]['residual_atomic']='77'
        with patch.object(br,'_reference',return_value=fake),self.assertRaisesRegex(br.AccountingError,'DISAGREEMENT'):self.make()
        self.assertFalse((self.root/'case').exists())

    def test_flow_order_does_not_change_accounting(self):
        a=self.check();self.data['flows'].reverse();b=self.check()
        for k in ('rows','asset_totals','status','declared_price_usd_total_delta'):self.assertEqual(a[k],b[k])
        self.assertNotEqual(a['input_sha256'],b['input_sha256'])

    def test_seeded_arithmetic_properties(self):
        rng=random.Random(20261104)
        for i in range(80):
            n=rng.randrange(1,2**180)
            model=br.example_input();model['before']['usd6']['vault']=str(n)
            model['after']['usd6']['vault']=str(n+124000000)
            result=br.reconcile(model);self.assertEqual(result['unexplained_cells'],0)
            model['after']['usd6']['vault']=str(n+124000001)
            self.assertEqual(br.reconcile(model)['unexplained_cells'],1)

    def test_original_bytes_preserved(self):
        raw=json.dumps(self.data,indent=3).encode()
        br.create_bundle(self.data,self.root/'case',original_bytes=raw)
        self.assertEqual((self.root/'case/input.json').read_bytes(),raw)

    def test_wrong_original_bytes_rejected(self):
        with self.assertRaises(br.AccountingError):br.create_bundle(self.data,self.root/'case',original_bytes=b'{}')
        self.assertFalse((self.root/'case').exists())

    def test_roundtrip_and_no_network(self):
        with patch('socket.socket',side_effect=AssertionError),patch('subprocess.run',side_effect=AssertionError):
            r=self.make();self.assertEqual(br.verify_bundle(self.root/'case'),r)

    def test_private_permissions(self):
        self.make();root=self.root/'case';self.assertEqual(root.stat().st_mode&0o777,0o700)
        for p in root.iterdir():self.assertEqual(p.stat().st_mode&0o777,0o600)

    def test_no_overwrite(self):
        self.make();marker=(self.root/'case/COMPLETE.json').read_bytes()
        with self.assertRaises(br.AccountingError):self.make()
        self.assertEqual(marker,(self.root/'case/COMPLETE.json').read_bytes())

    def test_resealed_result_rejected(self):
        self.make();self.alter('analysis.json',lambda r:r.update(vulnerability_confirmed=True))
        with self.assertRaisesRegex(br.AccountingError,'RESULT_MISMATCH'):br.verify_bundle(self.root/'case')

    def test_resealed_input_recomputed(self):
        self.make();self.alter('input.json',lambda r:r['after']['usd6'].update(vault='0'))
        with self.assertRaisesRegex(br.AccountingError,'RESULT_MISMATCH'):br.verify_bundle(self.root/'case')

    def test_audit_rebound_values_not_accepted(self):
        self.make()
        def change(j):
            native=br.load_components();previous='0'*64
            j['entries'][1]['data']['index']=77
            for e in j['entries']:
                e['prev_hash']=previous;e['hash']=native.audit.AuditEntry(**e).recompute();previous=e['hash']
            self.last=previous
        self.alter('audit.json',change);self.alter('receipt.json',lambda r:r.update(audit_head=self.last))
        with self.assertRaisesRegex(br.AccountingError,'AUDIT_SEMANTICS'):br.verify_bundle(self.root/'case')

    def test_code_identity_checked(self):
        self.make();self.alter('receipt.json',lambda r:r.update(code_sha256='0'*64))
        with self.assertRaisesRegex(br.AccountingError,'STALE_CODE'):br.verify_bundle(self.root/'case')

    def test_extra_file_not_exported_silently(self):
        self.make();(self.root/'case/extra').write_text('unexpected')
        with self.assertRaisesRegex(br.AccountingError,'BUNDLE_FILES'):br.verify_bundle(self.root/'case')

    def test_symlink_not_read(self):
        self.make();p=self.root/'case/input.json';raw=p.read_bytes();p.unlink();other=self.root/'other';other.write_bytes(raw);p.symlink_to(other)
        with self.assertRaises((OSError,ValueError)):br.verify_bundle(self.root/'case')

    def test_cli_roundtrip_in_separate_processes(self):
        inp=self.root/'input.json';inp.write_bytes(canonical(self.data))
        for args in (['reconcile-balances','--input',str(inp),'--out',str(self.root/'case')],
                     ['verify-balances','--bundle',str(self.root/'case')]):
            p=subprocess.run([sys.executable,'-B','-m','superhunter',*args],cwd=br.ROOT.parent,capture_output=True,text=True,timeout=15)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertFalse(json.loads(p.stdout)['execution_verified'])

    def test_cli_privacy_and_error_status(self):
        with redirect_stdout(io.StringIO()) as stream:
            code=br.main(['verify-balances','--bundle',str(self.root/'PRIVATE_MARKER')])
        self.assertEqual(code,2);self.assertNotIn('PRIVATE_MARKER',stream.getvalue())

    def test_fixed_controls_connected_and_verified(self):
        r=br.run_examples(self.root/'controls');self.assertEqual(r['status'],'LOCAL_ACCOUNTING_CONTROLS_PASS')
        self.assertEqual(r['controls']['one_unit_gap']['status'],'ACCOUNTING_MISMATCH')
        self.assertEqual(r['controls']['incomplete']['status'],'ACCOUNTING_INCONCLUSIVE')
        self.assertEqual(br.verify_examples(self.root/'controls'),r)

    def test_control_inputs_cannot_change_even_when_internally_consistent(self):
        br.run_examples(self.root/'controls')
        target=self.root/'controls/balanced';shutil.rmtree(target)
        m=br.example_input();m['case_id']='different';br.create_bundle(m,target)
        with self.assertRaisesRegex(br.AccountingError,'CONTROL_INPUT_CHANGED'):br.verify_examples(self.root/'controls')

    def test_control_summary_cannot_lie(self):
        br.run_examples(self.root/'controls');p=self.root/'controls/summary/result.json';p.write_bytes(b'{}')
        marker=strict_json((p.parent/'COMPLETE.json').read_bytes());marker['sha256']['result.json']=br.digest(b'{}')
        (p.parent/'COMPLETE.json').write_bytes(canonical(marker))
        with self.assertRaisesRegex(br.AccountingError,'CONTROL_SUMMARY_CHANGED'):br.verify_examples(p.parent.parent)


    def test_ambient_decimal_context_cannot_change_result(self):
        from decimal import localcontext, ROUND_UP
        self.data['assets']['usd6']['decimals']=255
        expected=self.check()
        with localcontext() as ctx:
            ctx.prec=2;ctx.Emin=-2;ctx.Emax=2;ctx.rounding=ROUND_UP
            self.assertEqual(self.check(),expected)


if __name__=='__main__':unittest.main()
