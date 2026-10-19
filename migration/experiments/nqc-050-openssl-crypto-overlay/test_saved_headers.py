"""NQC050 regression against the *already-captured* NQC037 parent/target.

These values were transcribed from two pinned GitHub files, so matching hashes
shows only captured-header self-consistency and parent linkage, NOT finality.
"""
import unittest
from parent_header_rehash import H as PARENT, header_hash

TARGET = dict(PARENT)
TARGET.update({
 'parentHash':'0x53f9d3bedcdd3554f7447343ca03f9c9a5a7b61c692057f431d9225e04e1a917',
 'stateRoot':'0x0b5c085594eeeabdbc165b0904a7a280951f4dd8d40c979fd51b1668985d85ba',
 'transactionsRoot':'0x0d48255688f8c8464b47af113fc105ba82bdbaa697fb39ce12e19cc5833550ac',
 'receiptsRoot':'0x0c78ba7487d19a65239cdff1df6639f06498269cba875bc3bdf2a7dc1d381ac7',
 'logsBloom':'0x002000800000000000000008800a0900000004003000180000000000000000000100400400010010094008000040004000008800000008000000800060a060000010000000000100000001080020002000000000000000000880010840000000000008000a4000010000000101000800400302000000000002000050000420000140000000400000400008000000048004040000100000080000104000880100420900000000000000000000000000000400040200200000000800400000004001000002002c00080280000000800080200000000000001000000000000020000010004800000400100a00001007000000004010004000100000000000002000',
 'number':'0x3fa6f62',
 'gasUsed':'0x3c26bd',
 'timestamp':'0x6aadfab0',
 'baseFeePerGas':'0x4062e90',
 'hash':'0x8e702487ffdd8f2ff97528407ba671f1a1d1d6f16a812e85fb5cb6625b6886d7',
})

class HistoricalHeaderObservations(unittest.TestCase):
    def test_captured_parent_header_hash(self):
        self.assertEqual(header_hash(PARENT), PARENT['hash'])

    def test_captured_target_header_hash(self):
        self.assertEqual(header_hash(TARGET), TARGET['hash'])

    def test_child_parent_link_and_heights(self):
        self.assertEqual(TARGET['parentHash'], PARENT['hash'])
        self.assertEqual(int(TARGET['number'],16), int(PARENT['number'],16)+1)

    def test_mutated_header_rejected(self):
        corrupt=dict(TARGET)
        corrupt['gasUsed']=hex(int(TARGET['gasUsed'],16)+1)
        self.assertNotEqual(header_hash(corrupt), TARGET['hash'])

if __name__=='__main__':
    unittest.main(verbosity=2)
