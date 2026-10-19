"""NQC051: tests of EXACT SHA256-verified NQC037 source excerpts only.
No network, external RPC, credential access, transactions or state acquisition.
"""
import copy
import pathlib
import sys
import unittest

HERE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(HERE.parent / 'nqc-050-openssl-crypto-overlay'))
sys.path.insert(0,str(HERE.parent / 'nqc-050-openssl-crypto-overlay' / 'compat'))
from parent_header_rehash import H
from test_saved_headers import TARGET
import verbatim_functions as subset
import pinned_prefix as pinned
import rlp
from Crypto.Hash import keccak

BODY=pathlib.Path(subset.__file__).read_text()

class OriginalSourceExcerptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env,step=pinned.compile_original_prefix(BODY,BODY,rlp,keccak)
        cls.step=staticmethod(step)
        cls.header=dict(H)
        cls.header.update(sendRoot='0xa2368ad058f0612fc03cc014fc0fca5ff4e974244980a7b9c08e4ec73f34d269',
                          sendCount='0xa00',l1BlockNumber='0x18cdc9b')

    def assertReject(self,fn):
        with self.assertRaises((self.env['ValidationError'],pinned.UnsafeEvidence)):
            fn()

    def test_01_all_eight_excerpts_byte_exact(self):
        self.assertEqual(len(pinned.excerpts(BODY,['ValidationError','require','k256','data_hex','quantity','validate_header'])),6)
        self.assertEqual(len(pinned.excerpts(BODY,['envelope','validate_step'])),2)

    def test_02_captured_parent_verified_with_metadata(self):
        self.assertEqual(self.env['validate_header'](self.header,self.env['PARENT_HASH'],66744161),H['hash'])

    def test_03_captured_target_verified_consecutive_parent(self):
        self.assertEqual(self.env['validate_header'](TARGET,TARGET['hash'],66744162),TARGET['hash'])
        self.assertEqual(TARGET['parentHash'],self.header['hash'])

    def test_04_chain_step_accepts_only_4663(self):
        s={}
        self.step({'purpose':'chain','request':{'id':1}},dict(jsonrpc='2.0',id=1,result='0x1237'),s)
        self.assertEqual(s['chain'],'0x1237')

    def test_05_original_captured_id6_is_not_plan_id2(self):
        raw={'jsonrpc':'2.0','id':6,'result':self.header}
        self.assertReject(lambda:self.step({'purpose':'parent','request':{'id':2}},raw,{}))

    def test_06_rewrapped_fixture_id2_for_test_only(self):
        s={}
        self.step({'purpose':'parent','request':{'id':2}},dict(jsonrpc='2.0',id=2,result=self.header),s)
        self.assertEqual(s['parent']['stateRoot'],self.env['PARENT_ROOT'])

    def test_07_wrong_chain_rejected(self):
        self.assertReject(lambda:self.step({'purpose':'chain','request':{'id':1}},dict(jsonrpc='2.0',id=1,result='0x1'),{}))

    def test_08_wrong_parent_state_root_rejected(self):
        h=self.header.copy();h['stateRoot']='0x'+'00'*32
        self.assertReject(lambda:self.step({'purpose':'parent','request':{'id':2}},dict(jsonrpc='2.0',id=2,result=h),{}))

    def test_09_parent_hash_mutation_rejected(self):
        h=self.header.copy();h['gasUsed']='0x01'
        self.assertReject(lambda:self.env['validate_header'](h,self.env['PARENT_HASH'],66744161))

    def test_10_send_count_metadata_tamper_rejected(self):
        h=self.header.copy();h['sendCount']='0xb00'
        self.assertReject(lambda:self.env['validate_header'](h,self.env['PARENT_HASH'],66744161))

    def test_11_send_root_metadata_tamper_rejected(self):
        h=self.header.copy();h['sendRoot']='0x'+'ff'*32
        self.assertReject(lambda:self.env['validate_header'](h,self.env['PARENT_HASH'],66744161))

    def test_12_nitro_extra_header_field_refused(self):
        h=self.header.copy();h['blobGasUsed']='0x1'
        self.assertReject(lambda:self.env['validate_header'](h,self.env['PARENT_HASH'],66744161))

    def test_13_bool_rpc_id_refused(self):
        self.assertReject(lambda:self.step({'purpose':'chain','request':{'id':1}},dict(jsonrpc='2.0',id=True,result='0x1237'),{}))

    def test_14_third_step_must_remain_disabled(self):
        self.assertReject(lambda:self.step({'purpose':'priority_proof','request':{'id':3}},dict(jsonrpc='2.0',id=3,result={}),{}))

    def test_15_invalid_jsonrpc_error_refused(self):
        self.assertReject(lambda:self.step({'purpose':'chain','request':{'id':1}},dict(jsonrpc='2.0',id=1,error={'code':429}),{}))

    def test_16_excerpt_mutation_rejected(self):
        self.assertRaisesRegex(pinned.UnsafeEvidence,'ORIGINAL_FUNCTION_HASH_CHANGED',
            pinned.excerpts,BODY.replace('Wrong chain','Wrong network'),['validate_step'])

    def test_17_full_source_missing_blocks(self):
        with self.assertRaises(pinned.UnsafeEvidence):pinned.audit_checkout(HERE)

    def test_18_captured_header_unchanged_on_tests(self):
        self.assertEqual(self.header['hash'],self.env['PARENT_HASH'])
        self.assertNotIn('latest',str(self.header).lower())

if __name__=='__main__':unittest.main(verbosity=2)
