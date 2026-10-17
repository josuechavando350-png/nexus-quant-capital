"""ABI shape tests; no output certifies mainnet execution or profitability."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bundler3_abi import (Call, selector, _word, keccak, encode_call_array,
                          abi_encode_calls, multicall_calldata, flashloan_callback_hash,
                          encode_flashloan_top_call, erc20_approve,
                          morpho_liquidate_no_callback)

ADAPTER="0x4A6c312ec70E8747a587EE860a0353cd42Be0aE0"
BUNDLER="0x6566194141eefa99Af43Bb5Aa71460Ca2Dc90245"
MORPHO="0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb"
WETH="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"

class Bundler3AbiTests(unittest.TestCase):
    def test_known_erc20_selector(self):
        self.assertEqual(selector("transfer(address,uint256)").hex(), "a9059cbb")
        self.assertEqual(selector("approve(address,uint256)").hex(), "095ea7b3")

    def test_one_dynamic_tuple_empty_payload_layout(self):
        blob=abi_encode_calls((Call(to=ADAPTER,data=b""),))
        self.assertEqual(len(blob), 32+32+32+160+32)
        self.assertEqual(blob[:32],_word(32))
        self.assertEqual(blob[32:64],_word(1))
        self.assertEqual(blob[64:96],_word(32))
        self.assertEqual(blob[128:160],_word(160))

    def test_dynamic_tuple_data_is_padded(self):
        a=abi_encode_calls((Call(to=ADAPTER,data=b"\x01\x02"),))
        self.assertEqual(len(a),32+32+32+160+32+32)
        self.assertEqual(a[-64:-32],_word(2))
        self.assertEqual(a[-32:-30],b"\x01\x02")

    def test_two_element_offsets_include_prior_tail(self):
        a=encode_call_array((Call(to=ADAPTER,data=b"\x01"),Call(to=BUNDLER,data=b"")))
        self.assertEqual(a[:32],_word(2))
        self.assertEqual(a[32:64],_word(64))
        self.assertEqual(a[64:96],_word(64 + 160 + 32 + 32))

    def test_reentry_callback_matches_dynamic_arg(self):
        nested=(Call(to=MORPHO,data=b"\x01\x02"),)
        self.assertEqual(flashloan_callback_hash(nested),keccak(abi_encode_calls(nested)))
        self.assertNotEqual(flashloan_callback_hash(nested),keccak(encode_call_array(nested)))

    def test_flashloan_outer_contains_nested_hash(self):
        nested=(Call(to=MORPHO,data=b"\x01\x02"),)
        outer=encode_flashloan_top_call(ADAPTER,WETH,10**18,nested)
        self.assertEqual(outer.to,ADAPTER)
        self.assertEqual(outer.callback_hash,flashloan_callback_hash(nested))
        self.assertEqual(outer.data[:4],selector("morphoFlashLoan(address,uint256,bytes)"))
        self.assertTrue(multicall_calldata((outer,)).startswith(
            selector("multicall((address,bytes,uint256,bool,bytes32)[])")))

    def test_liquidate_data_empty_and_static_tuple(self):
        d=morpho_liquidate_no_callback(WETH,ADAPTER,MORPHO,BUNDLER,860000000000000000,BUNDLER,500)
        self.assertEqual(len(d),4+9*32+32)
        self.assertEqual(d[4+8*32:4+9*32],_word(288))
        self.assertEqual(d[-32:],_word(0))

    def test_disallow_skip_revert_true(self):
        with self.assertRaises(ValueError):
            multicall_calldata((Call(to=ADAPTER,data=b"",skip_revert=True),))

    def test_disallow_invalid_address(self):
        with self.assertRaises(ValueError):
            erc20_approve("0x00",1)
        with self.assertRaises(ValueError):
            erc20_approve("0x  "+"11"*19,1)

    def test_disallow_invalid_callback_hash(self):
        with self.assertRaises(ValueError):
            multicall_calldata((Call(to=ADAPTER,data=b"",callback_hash=b"\x00"),))

    def test_disallow_empty_bundle(self):
        with self.assertRaises(ValueError):
            multicall_calldata(tuple())

    def test_disallow_noninteger_amount(self):
        with self.assertRaises(ValueError):
            erc20_approve(MORPHO,True)
        with self.assertRaises(ValueError):
            erc20_approve(MORPHO,-1)

if __name__=="__main__":unittest.main()
