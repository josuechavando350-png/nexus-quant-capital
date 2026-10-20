import io,json,tempfile,unittest,urllib.error
from pathlib import Path
from rpc_guard import Guard,validate,Closed,PARENT,TX
class Resp(io.BytesIO):
    status=200
class Tests(unittest.TestCase):
    def test_01_allow_only_pinned_state(self):
        validate('eth_getStorageAt',['0x'+'12'*20,'0x0',hex(PARENT)])
        validate('eth_getCode',['0x'+'12'*20,hex(PARENT)])
    def test_02_write_refused(self):
        for m in ['eth_sendRawTransaction','eth_sendTransaction','personal_sign','eth_sign','debug_traceTransaction']:
            with self.assertRaises(Closed):validate(m,[])
    def test_03_latest_refused(self):
        with self.assertRaises(Closed):validate('eth_getCode',['0x'+'12'*20,'latest'])
    def test_04_wrong_history_refused(self):
        with self.assertRaises(Closed):validate('eth_getCode',['0x'+'12'*20,hex(PARENT+1)])
    def test_05_other_tx_refused(self):
        with self.assertRaises(Closed):validate('eth_getTransactionByHash',['0x'+'ab'*32])
    def test_06_state_override_refused(self):
        with self.assertRaises(Closed):validate('eth_getCode',['0x'+'12'*20,hex(PARENT),{}])
    def test_07_cache_avoids_repeat(self):
        calls=[]
        def op(r,timeout):calls.append(r);return Resp(b'{"jsonrpc":"2.0","id":1,"result":"0x1"}')
        with tempfile.TemporaryDirectory() as d:
            g=Guard(Path(d),op,sleep=lambda _:None)
            self.assertEqual(g.call('eth_chainId',[]),'0x1');self.assertEqual(g.call('eth_chainId',[]),'0x1');self.assertEqual(len(calls),1)
    def test_08_403_no_retry(self):
        calls=[]
        def op(r,timeout):calls.append(r);raise urllib.error.HTTPError(r.full_url,403,'denied',{},None)
        with tempfile.TemporaryDirectory() as d:
            g=Guard(Path(d),op,sleep=lambda _:None)
            for _ in range(2):
                with self.assertRaises(Closed):g.call('eth_chainId',[])
            self.assertEqual(len(calls),1)
    def test_09_null_never_success(self):
        def op(r,timeout):return Resp(b'{"jsonrpc":"2.0","id":1,"result":null}')
        with tempfile.TemporaryDirectory() as d:
            g=Guard(Path(d),op,sleep=lambda _:None)
            with self.assertRaises(Closed):g.call('eth_getTransactionByHash',[TX])
            self.assertIsNotNone(g.halted)
    def test_10_budget(self):
        with tempfile.TemporaryDirectory() as d:
            g=Guard(Path(d),sleep=lambda _:None);g.used=1200
            with self.assertRaises(Closed):g.call('eth_chainId',[])
    def test_11_bad_address(self):
        with self.assertRaises(Closed):validate('eth_getCode',['0x0',hex(PARENT)])
    def test_12_future_block(self):
        with self.assertRaises(Closed):validate('eth_getBlockByNumber',[hex(PARENT+2),False])
if __name__=='__main__':unittest.main()
