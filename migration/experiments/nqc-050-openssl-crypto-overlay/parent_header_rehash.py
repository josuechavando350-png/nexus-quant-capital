"""NQC050 self-check against EXISTING parent-header bytes observed in NQC037.

This is an internal header self-consistency check, NOT independent canonicality.
The fields below are copied exactly from the pinned GitHub input identified
by blob SHA d8576f0e73000d4ab993d69134ff0713ef70ca16.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / 'compat'))
import rlp
from Crypto.Hash import keccak

H = {
 'parentHash':'0x6739b5957a5835216d6a8eb6c74a0a40807f34fc07e66622daae58598ad4e86f',
 'sha3Uncles':'0x1dcc4de8dec75d7aab85b567b6ccd41ad312451b948a7413f0a142fd40d49347',
 'miner':'0xa4b000000000000000000073657175656e636572',
 'stateRoot':'0xc07bf301da73475b44460226757ddfd1c2ee60a6d7346e3749de6953f78bae4a',
 'transactionsRoot':'0x01f55581f9b0276374caf430c4c26ca8706474b74210d4e79bbfede609e1faa0',
 'receiptsRoot':'0x5018c7374518d0ccc97bab0c4ad331ba550d2c2d883856cc9c0f21cabfc3a9c4',
 'logsBloom':'0x000000a09000000000000052120a10000000000010000800000e0000002000c00288004010000000002000010802020000020000040020000000120000202210000000000000404804040208002001802040080091001024000000020402020010008000020c00400200b000090808000000810000024000a208085404480000018200016000000100000004000000000008000111100002800000050080000006301002008000008044002008000000000001000884000000000200100080000000042a04800040400301802020400010000000802000090c10000000082000081000104004000004440000012020200000000000004000080400001a0c0040',
 'difficulty':'0x1', 'number':'0x3fa6f61','gasLimit':'0x4000000000000','gasUsed':'0x442d97','timestamp':'0x6aadfaaf',
 'extraData':'0xa2368ad058f0612fc03cc014fc0fca5ff4e974244980a7b9c08e4ec73f34d269',
 'mixHash':'0x0000000000000a0000000000018cdc9b000000000000003d0000000000000000',
 'nonce':'0x0000000000048b1d','baseFeePerGas':'0x403adf0',
 'hash':'0x53f9d3bedcdd3554f7447343ca03f9c9a5a7b61c692057f431d9225e04e1a917',
}

def header_hash(header):
    widths={'parentHash':32,'sha3Uncles':32,'miner':20,'stateRoot':32,'transactionsRoot':32,'receiptsRoot':32,'logsBloom':256}
    fields=[bytes.fromhex(header[k][2:]) for k in widths]
    for k,n in zip(widths, widths.values()): assert len(bytes.fromhex(header[k][2:]))==n,k
    fields.extend(int(header[k],16) for k in ['difficulty','number','gasLimit','gasUsed','timestamp'])
    fields.extend([bytes.fromhex(header[k][2:]) for k in ['extraData','mixHash','nonce']])
    fields.append(int(header['baseFeePerGas'],16))
    assert len(fields)==16
    return '0x'+keccak.new(digest_bits=256,data=rlp.encode(fields)).hexdigest()

if __name__=='__main__':
    actual=header_hash(H)
    print('parent_number:',int(H['number'],16))
    print('parent_state_root:',H['stateRoot'])
    print('parent_hash_calculated:',actual)
    print('parent_hash_captured:',H['hash'])
    print('internal_header_self_consistency:',actual==H['hash'])
    assert actual==H['hash'], 'Header mismatch'
