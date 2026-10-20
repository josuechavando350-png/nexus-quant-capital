"""Offline transport integrity checks; no economic certification."""
from pathlib import Path
import json, tempfile, unittest
from continue_original import PinnedHead, rg, restore, run, HERE

class Boundaries(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        def forbidden(*args,**kwargs):raise AssertionError('Network must not be called')
        self.guard=rg.Guard(Path(self.tmp.name),opener=forbidden)
        restore(self.guard);self.adapter=PinnedHead(self.guard)
    def test_head_from_saved_header_only(self):
        self.assertEqual(self.adapter.call('eth_blockNumber',[]),'0x14c1351')
        self.assertEqual(self.guard.used,10)
    def test_gas_from_saved_receipt_only(self):
        self.assertEqual(int(self.adapter.call('eth_gasPrice',[]),16),302819782345)
        self.assertEqual(self.guard.used,10)
    def test_no_latest_writes_overrides_or_target_state(self):
        for method,params in [('eth_getBlockByNumber',['latest',False]),('eth_sendRawTransaction',['0x']),('eth_call',[{},'0x14c1350']),('eth_getCode',['0x'+'00'*20,'0x14c1351'])]:
            with self.subTest(method=method),self.assertRaises(rg.Closed):self.adapter.call(method,params)
    def test_case_canonicalization_reuses_original(self):
        self.assertEqual(self.adapter.call('eth_getBalance',['0x0EF3794CB89864337E15A9F077020C285EF0989B','0x14c1350']),'0x676a371ff6adb23')
        self.assertEqual(self.guard.used,10)
    def test_metadata_tamper_fails(self):
        key=json.dumps(['eth_getBlockByNumber',['0x14c1351',False]],sort_keys=True,separators=(',',':'))
        self.guard.cache[key]['hash']='0x'+'00'*32
        with self.assertRaises(rg.Closed):self.adapter.call('eth_blockNumber',[])
    def test_stop_applies_to_metadata(self):
        self.guard.halted='access denied'
        with self.assertRaises(rg.Closed):self.adapter.call('eth_blockNumber',[])
        with self.assertRaises(rg.Closed):self.adapter.call('eth_gasPrice',[])
    def test_published_network_driver_cannot_retry_after_denial(self):
        with self.assertRaisesRegex(rg.Closed,'ACCESS_STOP_RECORDED'):
            run(Path(self.tmp.name),Path('/unused'),Path('/unused'))

if __name__=='__main__':unittest.main(verbosity=2)
