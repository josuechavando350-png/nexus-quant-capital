"""Verify recovered blob content and its binding to a captured L2 tx root.

No execution, consensus verification, signing, transmission or economic admission.
"""
import base64
import hashlib
import json
import platform
from importlib.metadata import version
import ckzg
import rlp
from trie import HexaryTrie
from decode_batch import ROOT, decode, k256, require, rlp_one

TARGET_TX = '0xf9e0d2e116d99e2eb8ef2cf236f7cd7f06225e92a6dfd9162f98c7d8e1974842'
PREFIX_TX = '0x3824f876e4f5f677850701f41b990f6971c631ff8ebbce08a904072c17488fe8'
TARGET_HASH = '0x8e702487ffdd8f2ff97528407ba671f1a1d1d6f16a812e85fb5cb6625b6886d7'
BLOB_HASHES = [
    '0x01094c90acd3d00563f75a4176be9d24b8d182f5ac7eaf1c206a3df2e76b1190',
    '0x014cb4ba0af7fda2ad841a2920c2824d92432fa10b247d58bf7836c6e168da63',
    '0x0172366acd2c0f6414a560fbcb9b717592d032432468342135fefe57c1712fab',
]

def unhex(value):
    require(isinstance(value,str) and value.startswith('0x'), 'expected hex')
    return bytes.fromhex(value[2:])

def read(path):
    return json.loads((ROOT/path).read_text())

def versioned_hash(commitment):
    return '0x01'+hashlib.sha256(commitment).hexdigest()[2:]

def verify_blob(blob, metadata, expected_hash, setup):
    require(len(blob)==131072, 'blob length')
    commitment = ckzg.blob_to_kzg_commitment(blob, setup)
    require(commitment == unhex(metadata['commitment']), 'blob commitment mismatch')
    require(versioned_hash(commitment) == expected_hash == metadata['versionedHash'], 'blob hash/order mismatch')
    # Verify content-addressed retrieval independently of metadata file integrity.
    refs = [r for r in metadata['dataStorageReferences'] if r['storage']=='ipfs']
    require(len(refs)==1, 'unexpected IPFS reference count')
    cid = refs[0]['url'].rsplit('/',1)[-1]
    require(cid.startswith('b'), 'unsupported CID multibase')
    decoded = base64.b32decode(cid[1:].upper()+'='*((-len(cid[1:]))%8))
    require(decoded[:4] == b'\x01\x55\x12\x20', 'expected raw/SHA256 CIDv1')
    require(decoded[4:] == hashlib.sha256(blob).digest(), 'IPFS CID mismatch')
    provided_valid = ckzg.verify_blob_kzg_proof(blob, commitment, unhex(metadata['proof']), setup)
    derived = ckzg.compute_blob_kzg_proof(blob, commitment, setup)
    require(ckzg.verify_blob_kzg_proof(blob, commitment, derived, setup), 'local KZG consistency failure')
    return {'bytes':len(blob),'sha256':hashlib.sha256(blob).hexdigest(),
            'versioned_hash':expected_hash,'recomputed_commitment_matches':True,
            'ipfs_cid_matches':True,'provider_blob_proof_valid':provided_valid,
            'local_blob_proof':'0x'+derived.hex(),'local_blob_proof_valid':True}

def header_hash(header):
    byte_fields = ['parentHash','sha3Uncles','miner','stateRoot','transactionsRoot','receiptsRoot','logsBloom']
    numeric = ['difficulty','number','gasLimit','gasUsed','timestamp']
    fields = [unhex(header[k]) for k in byte_fields]+[int(header[k],16) for k in numeric]
    fields += [unhex(header[k]) for k in ['extraData','mixHash','nonce']]
    fields += [int(header['baseFeePerGas'],16)]
    return '0x'+k256(rlp.encode(fields)).hex()

def prefix_transaction(header, parent, l1block, timestamp):
    require(timestamp == int(header['timestamp'],16), 'derived timestamp mismatch')
    require(timestamp >= int(parent['timestamp'],16), 'negative timePassed')
    selector = k256(b'startBlock(uint256,uint64,uint64,uint64)')[:4]
    args = [0, l1block, int(header['number'],16), timestamp-int(parent['timestamp'],16)]
    data = selector+b''.join(v.to_bytes(32,'big') for v in args)
    return b'\x6a'+rlp.encode([4663,data]), data

def transaction_root(raw_txs):
    trie = HexaryTrie(db={})
    for index,tx in enumerate(raw_txs):
        trie[rlp.encode(index)] = tx
    return '0x'+trie.root_hash.hex()

def audit():
    target = read('inputs/05-block.json')['result']
    parent = read('inputs/06-parent.json')['result']
    require(header_hash(target)==target['hash']==TARGET_HASH, 'captured target header mismatch')
    require(header_hash(parent)==parent['hash']==target['parentHash'], 'captured parent header mismatch')
    l1 = read('evidence/blockscout-l1-tx.json')['structuredContent']['data']
    batch = read('evidence/blockscout-batch.json')['structuredContent']['data']
    config = read('vendor/official-chain-info.json')[0]
    inbox = config['rollup']['sequencer-inbox'].lower()
    require(config['chain-id']==4663 and config['parent-chain-id']==1, 'chain config identity')
    require(l1['to'].lower()==inbox and l1['status']=='ok' and l1['type']==3, 'L1 transaction identity')
    require(l1['blob_versioned_hashes']==BLOB_HASHES, 'L1 blob list mismatch')
    calldata = unhex(l1['raw_input'])
    require(len(calldata)==164 and calldata[:4]==k256(b'addSequencerL2BatchFromBlobs(uint256,uint256,address,uint256,uint256)')[:4], 'L1 calldata')
    words = [int.from_bytes(calldata[i:i+32],'big') for i in range(4,len(calldata),32)]
    sequence, delayed, refunder, first_message, after_messages = words
    require(words==[258761,297757,0,66743956,66744188], 'L1 calldata values')
    logs = read('evidence/blockscout-l1-logs.json')['structuredContent']['data']
    signature = k256(b'SequencerBatchDelivered(uint256,bytes32,bytes32,bytes32,uint256,(uint64,uint64,uint64,uint64),uint8)')
    events = [v for v in logs if v['address'].lower()==inbox and unhex(v['topics'][0])==signature]
    require(len(events)==1, 'batch event ambiguity')
    event = events[0]
    require(int(event['topics'][1],16)==sequence and event['block_number']==26008734, 'batch log scope')
    data = unhex(event['data']); require(len(data)==224, 'truncated batch event')
    fields = [int.from_bytes(data[i:i+32],'big') for i in range(0,len(data),32)]
    delayed_acc = data[:32]
    require(fields[1]==delayed and fields[6]==3, 'batch delayed count/data location')
    min_time,max_time,min_l1,max_l1 = fields[2:6]
    seq_header = b''.join(v.to_bytes(8,'big') for v in [min_time,max_time,min_l1,max_l1,delayed])
    sequencer_data_hash = k256(seq_header+b'\x50'+b''.join(unhex(h) for h in BLOB_HASHES))
    accumulated = k256(unhex(event['topics'][2])+sequencer_data_hash+delayed_acc)
    require('0x'+accumulated.hex()==event['topics'][3]==batch['after_acc_hash'], 'sequencer accumulator mismatch')
    setup = ckzg.load_trusted_setup(str(ROOT/'vendor/trusted_setup.txt'),0)
    blobs = [(ROOT/f'evidence/blob-{i}-payload.response').read_bytes() for i in range(3)]
    verified = [verify_blob(b,read(f'evidence/blob-{i}-metadata.json'),BLOB_HASHES[i],setup) for i,b in enumerate(blobs)]
    decoded = decode(blobs)
    require(len(decoded['messages'])==after_messages-first_message, 'batch message count mismatch')
    matches = [m for m in decoded['messages'] if TARGET_TX in m['tx_hashes']]
    require(len(matches)==1, 'target occurrence ambiguity')
    m = matches[0]
    require(m['tx_hashes']==target['transactions'][1:], 'target transaction sequence mismatch')
    require(first_message+m['ordinal']==int(target['number'],16), 'message/block mapping mismatch')
    timestamp = min(max(m['timestamp_before_l1_bounds'],min_time),max_time)
    l1block = min(max(m['l1block_before_l1_bounds'],min_l1),max_l1)
    require(l1block==int(target['l1BlockNumber'],16), 'derived L1 origin mismatch')
    prefix, prefix_data = prefix_transaction(target,parent,l1block,timestamp)
    require('0x'+k256(prefix).hex()==PREFIX_TX==target['transactions'][0], 'prefix transaction hash mismatch')
    observed_prefix = read('evidence/blockscout-prefix-tx.json')['structuredContent']['data']
    require(unhex(observed_prefix['raw_input'])==prefix_data, 'prefix explorer disagreement')
    full_txs = [prefix]+m['raw_transactions']
    root = transaction_root(full_txs)
    require(root==target['transactionsRoot'], 'full transaction root mismatch')
    return {
        'status':'PASS_WITH_UNCLOSED_STATE_AND_CONSENSUS_GATES',
        'blobs':verified,
        'sequencer_data_hash':'0x'+sequencer_data_hash.hex(),
        'sequencer_after_accumulator':'0x'+accumulated.hex(),
        'accumulator_matches_observed_l1_event':True,
        **{k:v for k,v in decoded.items() if k!='messages'},
        'message_count':len(decoded['messages']),
        'signed_transaction_count':sum(len(v['tx_hashes']) for v in decoded['messages']),
        'target_message_ordinal':m['ordinal'],'target_segment_index':m['segment_index'],
        'target_signed_transactions':len(m['raw_transactions']),
        'derived_timestamp':timestamp,'derived_l1_block_number':l1block,
        'derived_prefix_hash':PREFIX_TX,'derived_prefix_raw':'0x'+prefix.hex(),
        'full_transaction_root':root,'full_transaction_root_matches_captured_header':True,
        'captured_header_hash_verified':TARGET_HASH,
        'observed_l1_receipt_consensus_proof_verified':False,
        'canonical_l2_header_authenticated':False,
        'historical_nitro_binary_authenticated':False,
        'historical_fork_schedule_authenticated':False,
        'full_l2_header_derived_by_execution':False,
        'parent_state_witness_complete':False,
        'prefix_state_transition_executed':False,
        'exact_prestate_root':None,'authenticated_priority_slots':0,
        'nitro_replayed':False,'economic_replay_completed':False,
        'funding_terms_accepted':False,'commercial_admission':False,
        'commercial_readiness_judgment_out_of_10':2.5,'realized_pnl_usd':'0',
        'runtime':{'python':platform.python_version(),**{p:version(p) for p in ['ckzg','Brotli','pycryptodome','trie','rlp']}},
        'trusted_setup_sha256':hashlib.sha256((ROOT/'vendor/trusted_setup.txt').read_bytes()).hexdigest(),
    }

if __name__=='__main__':
    result = audit()
    (ROOT/'evidence/RESULTS.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('blobs','derived_prefix_raw')},indent=2))
