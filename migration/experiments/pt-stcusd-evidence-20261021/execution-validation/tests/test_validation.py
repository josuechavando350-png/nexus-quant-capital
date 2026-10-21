"""Safety/ledger regressions only. No synthetic profit or simulated protocol success."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from acquire import rpc, redact
from economic_audit import ledger
from preflight import validate

class ValidationTests(unittest.TestCase):
    def test_mutating_rpc_cannot_reach_transport(self):
        with patch('acquire.fetch') as transport:
            for method in ('eth_sendRawTransaction','eth_sendTransaction','eth_sign','personal_sign','eth_sendBundle','anvil_setBalance'):
                with self.assertRaises(ValueError):rpc('https://example.invalid',method,[])
            transport.assert_not_called()

    def test_rpc_error_kept_and_not_reported_as_success(self):
        body=json.dumps({'jsonrpc':'2.0','id':1,'error':{'code':-32000,'message':'missing trie node'}})
        with patch('acquire.fetch',return_value={'status':'RECEIVED','http_status':200,'body':body}):
            r=rpc('https://example.invalid','eth_getCode',[])
        self.assertEqual(r['status'],'BLOCKED')
        self.assertEqual(r['rpc_error']['message'],'missing trie node')

    def test_secret_redaction_covers_full_url_and_key(self):
        url='https://eth-mainnet.g.alchemy.com/v2/TEST_CREDENTIAL_NOT_REAL'
        with patch.dict(os.environ,{'NQC_RPC_URL':url}):
            self.assertNotIn('TEST_CREDENTIAL_NOT_REAL',redact(url+' TEST_CREDENTIAL_NOT_REAL'))

    def test_actual_missing_archive_cannot_pass_preflight(self):
        r=validate(ROOT/'evidence/alchemy','alchemy')
        self.assertTrue(r['status'].startswith('BLOCKED'))
        self.assertIn('prestate',r['missing']);self.assertFalse(r['evm_executed'])

    def test_recorded_ledger_and_single_gas_charge(self):
        r=ledger();d=r['historical_deltas_base_units']
        self.assertEqual(d['USDC']['EXECUTOR'],'0')
        self.assertEqual(d['WETH']['EXECUTOR'],'225720514923773')
        self.assertEqual(d['ETH']['HISTORICAL_GAS_EOA'],'-1950204206046304')
        self.assertEqual(d['ETH']['HISTORICAL_COINBASE'],'34081264575152600')
        self.assertTrue(all(sum(map(int,rows.values()))==0 for rows in d.values()))

    def test_unknown_economics_remain_unknown(self):
        r=ledger()
        self.assertIsNone(r['nqc_net_profit']);self.assertIsNone(r['strategies']['winner'])
        self.assertTrue(all(v is None for v in r['nqc_unknown_costs'].values()))
        self.assertFalse(r['zero_proprietary_capital_proven'])
        self.assertFalse(r['conditional_external_owner_residual']['is_NQC_profit'])

if __name__=='__main__':unittest.main(verbosity=2)
