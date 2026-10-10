"""Real denied preflight plus explicitly synthetic collector/ABI control tests."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

import collect as c
import readback as r

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'ci/nqc-census'))
from typed_observation_vectors import keccak256

class RealFailureChecks(unittest.TestCase):
    def setUp(self):
        self.files=r.members((r.HERE/'capture-001.zip').read_bytes())

    def change_acquisition(self, key, value):
        doc=json.loads(self.files['acquisition.json']);doc[key]=value
        self.files['acquisition.json']=c.encoded(doc)

    def test_real_capture_replays(self):
        report=r.verify()
        self.assertEqual((report['http_requests'],report['http_status']),(1,403))
        self.assertIsNone(report['chain_id_observed'])
        self.assertIsNone(report['reserve_count'])
        self.assertIsNone(report['net_pnl'])
        self.assertFalse(report['census_closed'])

    def test_corrupted_archive_rejected(self):
        raw=bytearray((r.HERE/'capture-001.zip').read_bytes());raw[40]^=1
        with self.assertRaisesRegex(ValueError,'archive bytes/digest'):r.members(raw)

    def test_body_substitution_rejected(self):
        self.files['0001.response.bin']=b'{}'
        with self.assertRaisesRegex(ValueError,'digests'):r.reconcile(self.files)

    def test_completion_promotion_rejected(self):
        self.change_acquisition('status','COMPLETE')
        with self.assertRaisesRegex(ValueError,'remain failed'):r.reconcile(self.files)

    def test_erased_failure_rejected(self):
        self.change_acquisition('failure','none')
        with self.assertRaisesRegex(ValueError,'remain failed'):r.reconcile(self.files)

    def test_wrong_chain_scope_rejected(self):
        self.change_acquisition('chain_id',1)
        with self.assertRaisesRegex(ValueError,'scope'):r.reconcile(self.files)

    def test_producer_substitution_rejected(self):
        self.files['collect.py']+=b'\n'
        with self.assertRaisesRegex(ValueError,'source identity'):r.reconcile(self.files)

class SyntheticControlChecks(unittest.TestCase):
    def test_all_selectors_match_keccak(self):
        for signature,selector in c.SELECTORS.items():
            self.assertEqual(selector,'0x'+keccak256(signature.encode())[:4].hex())

    def test_strict_reserve_array(self):
        def data(w):return '0x'+''.join(f'{v:064x}' for v in w)
        self.assertEqual(c.reserves(data([32,2,1,2])),[c.address(1),c.address(2)])
        for row in [[],[64,1,1],[32,2,1],[32,2,1,1],[32,1,0],[32,1,2**160],[32,0],[32,1,1,2]]:
            with self.subTest(row=row),self.assertRaises(ValueError):c.reserves(data(row))

    def test_wrong_chain_stops_before_anchor(self):
        class WrongChain:
            count=0
            def rpc(self,*args):self.count+=1;return '0x1'
        x=WrongChain()
        with self.assertRaisesRegex(ValueError,'wrong chain'):c.capture(x)
        self.assertEqual(x.count,1)

    def test_synthetic_http_denial_persisted_once(self):
        with tempfile.TemporaryDirectory() as temp:
            dest=Path(temp)/'new'
            err=urllib.error.HTTPError(c.ENDPOINT,403,'Forbidden',{},io.BytesIO(b'error code: 1010\n'))
            with patch('urllib.request.urlopen',side_effect=err) as network:
                self.assertEqual(c.main(dest),1)
                self.assertEqual(network.call_count,1)
            doc=json.loads((dest/'acquisition.json').read_bytes())
            self.assertEqual(doc['status'],'FAILED')
            self.assertEqual(len(doc['records']),1)

    def test_writes_never_reach_transport(self):
        with tempfile.TemporaryDirectory() as temp:
            cap=c.Capture(Path(temp)/'new')
            with patch('urllib.request.urlopen') as network:
                with self.assertRaisesRegex(ValueError,'read-only'):cap.rpc('forbidden','eth_sendRawTransaction',['0x'])
                network.assert_not_called()

    def test_old_output_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(FileExistsError):c.Capture(Path(temp))

if __name__=='__main__':unittest.main()
