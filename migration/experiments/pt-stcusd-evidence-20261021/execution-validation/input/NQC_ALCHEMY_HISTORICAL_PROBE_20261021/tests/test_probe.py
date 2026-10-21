import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from probe import request_rpc, RPCFailure, run_probe,TX_HASH,BLOCK_NUMBER

URL='https://eth-mainnet.g.alchemy.com/v2/PLACEHOLDER12345'

def fixture_transport(url,method,params):
    if method=='eth_chainId': return '0x1'
    if method=='eth_getBlockByNumber': return {'number':params[0], 'stateRoot':'0x1234'}
    if method=='eth_getTransactionByHash':return {'hash':TX_HASH,'blockNumber':hex(BLOCK_NUMBER),'transactionIndex':'0x0', 'input':'0xabcdef'}
    if method=='eth_getTransactionReceipt':return {'transactionHash':TX_HASH,'status':'0x1'}
    if method=='eth_getProof':return {'address':params[0], 'accountProof':[]}
    if method=='eth_getCode':return '0x6000'
    if method=='debug_traceTransaction':return {'0x1234':{'balance':'0x0'}}
    raise AssertionError(method)

class Tests(unittest.TestCase):
    def test_allowlist_rejects_send(self):
        with self.assertRaises(ValueError): request_rpc(URL,'eth_sendRawTransaction',['0x01'])
    def test_default_five_required_and_two_more(self):
        with tempfile.TemporaryDirectory() as d:
            x=run_probe(URL,d,transport=fixture_transport)
            self.assertEqual(x['status'],'BASE_READS_PASS_REPLAY_NOT_VERIFIED')
            self.assertEqual(len(x['runs']),7)
            self.assertNotIn('prestate_trace',x['runs'])
    def test_trace_opt_in(self):
        with tempfile.TemporaryDirectory() as d:
            x=run_probe(URL,d,trace=True,transport=fixture_transport)
            self.assertEqual(len(x['runs']),9)
            self.assertEqual(x['runs']['prestate_trace']['status'],'SAVED')
    def test_wrong_chain_blocks_all_else(self):
        def wrong(url,method,params):return '0x89' if method=='eth_chainId' else fixture_transport(url,method,params)
        with tempfile.TemporaryDirectory() as d:
            x=run_probe(URL,d,transport=wrong)
            self.assertEqual(x['status'],'BLOCKED')
            self.assertEqual(x['runs']['original_receipt']['status'],'NOT_ATTEMPTED_CHAIN_UNVERIFIED')
    def test_invalid_original_stops_pass(self):
        def wrong(url,method,params):return dict(fixture_transport(url,method,params),transactionIndex='0x5') if method=='eth_getTransactionByHash' else fixture_transport(url,method,params)
        with tempfile.TemporaryDirectory() as d:
            x=run_probe(URL,d,transport=wrong)
            self.assertEqual(x['status'],'BLOCKED')
            self.assertEqual(x['runs']['original_transaction']['category'],'TX_NOT_AT_EXPECTED_POSITION')
    def test_endpoint_restriction(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):run_probe('https://example.org/v2/SECRET12345',d)
    def test_key_not_in_report(self):
        with tempfile.TemporaryDirectory() as d:
            run_probe(URL,d,transport=fixture_transport)
            self.assertNotIn('PLACEHOLDER12345',(pathlib.Path(d)/'report.json').read_text())
    def test_keeps_rpc_errors_as_codes_only(self):
        def failure(url,method,params):
            if method=='eth_getProof':raise RPCFailure('RPC_ERROR', -32000)
            return fixture_transport(url,method,params)
        with tempfile.TemporaryDirectory() as d:
            x=run_probe(URL,d,transport=failure)
            self.assertEqual(x['status'],'BASE_READS_PASS_REPLAY_NOT_VERIFIED')
            self.assertEqual(x['runs']['morpho_account_proof_parent']['code'],-32000)

if __name__=='__main__':unittest.main()
