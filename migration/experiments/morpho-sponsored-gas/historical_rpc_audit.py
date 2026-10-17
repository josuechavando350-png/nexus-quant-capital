"""Offline cross-provider header/receipt checks, never a historical state replay.

RLP header hashing covers the Prague fields actually returned for these blocks.
Transaction/receipt tries, consensus finality and state transitions are NOT verified.
No network, signing, broadcasting, private keys or balances are modified.
"""
import gzip
import json
import re
from pathlib import Path

from evm_hash import keccak256

ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / 'evidence/2026-10-17-profitability'
HASH_A = '0x8691c49e741bb2432a31ef9fe708d18ad4f343c12f171c8ec1ae07510e3a3a09'
HASH_B = '0x5d499e63c5d119293a906036f369d8d75f9560618efec0ff916e4fefa33dfda8'
TX_A = '0x0a2f442acfb350d6d93002038b454ead40ffcf28a777b291cbaec1746d8aa2f1'
TX_B = '0x46300e9614c547118ecdd524bc7218208088cc4ae9e5bd534e62055d38f9925b'
PREFIX_B = '0x0c5ba40ae213874eb37df22686f53729371378171d81dc9899a599351d2759f0'


def load(name: str):
    p = EVIDENCE / name
    return json.loads(gzip.decompress(p.read_bytes()) if name.endswith('.gz') else p.read_bytes())


def quantity(value: str) -> int:
    if not isinstance(value, str) or not re.fullmatch(r'0x(?:0|[1-9a-fA-F][0-9a-fA-F]*)', value):
        raise ValueError('noncanonical RPC quantity')
    return int(value, 16)


def data(value: str, size=None) -> bytes:
    if not isinstance(value, str) or not re.fullmatch(r'0x(?:[0-9a-fA-F]{2})*', value):
        raise ValueError('invalid RPC data')
    decoded = bytes.fromhex(value[2:])
    if size is not None and len(decoded) != size:
        raise ValueError('incorrect RPC data length')
    return decoded


def rlp(value) -> bytes:
    if type(value) is int:
        if value < 0: raise ValueError('negative RLP integer')
        value = value.to_bytes((value.bit_length()+7)//8, 'big')
    if type(value) is bytes:
        if len(value) == 1 and value[0] < 128: return value
        payload, offset = value, 128
    elif type(value) is list:
        payload, offset = b''.join(rlp(item) for item in value), 192
    else:
        raise ValueError('unsupported RLP input')
    n = len(payload)
    if n < 56: return bytes([offset+n]) + payload
    length = n.to_bytes((n.bit_length()+7)//8, 'big')
    if len(length) > 8: raise ValueError('RLP length overflow')
    return bytes([offset+55+len(length)]) + length + payload


def verify_header(block: dict, expected_hash: str) -> str:
    # Fixed field order from EIPs 4895, 4844, 4788, 7685. Fail on missing fields.
    fields = [('parentHash',32),('sha3Uncles',32),('miner',20),('stateRoot',32),
              ('transactionsRoot',32),('receiptsRoot',32),('logsBloom',256),
              ('difficulty',None),('number',None),('gasLimit',None),('gasUsed',None),
              ('timestamp',None),('extraData',-1),('mixHash',32),('nonce',8),
              ('baseFeePerGas',None),('withdrawalsRoot',32),('blobGasUsed',None),
              ('excessBlobGas',None),('parentBeaconBlockRoot',32),('requestsHash',32)]
    encoded = [quantity(block[key]) if size is None else data(block[key], None if size == -1 else size)
               for key, size in fields]
    if len(data(block['extraData'])) > 32: raise ValueError('extraData length')
    computed = '0x'+keccak256(rlp(encoded)).hex()
    if computed != expected_hash or block['hash'] != expected_hash:
        raise ValueError('header hash mismatch')
    return computed


def verify_type2_hash(tx: dict, expected: str) -> str:
    if quantity(tx['type']) != 2: raise ValueError('only observed type-2 transactions supported')
    access = [[data(entry['address'],20), [data(k,32) for k in entry['storageKeys']]]
              for entry in tx['accessList']]
    values = [quantity(tx[k]) for k in ('chainId','nonce','maxPriorityFeePerGas','maxFeePerGas','gas')]
    values += [data(tx['to'],20) if tx['to'] else b'',quantity(tx['value']),data(tx['input']),access]
    values += [quantity(tx[k]) for k in ('yParity','r','s')]
    computed = '0x'+keccak256(b'\x02'+rlp(values)).hex()
    if computed != expected or tx['hash'] != expected: raise ValueError('transaction hash mismatch')
    return computed


def verify_case(block, receipt, indexer, block_hash, tx_hash, index) -> dict:
    verify_header(block, block_hash)
    tx = block['transactions'][index]
    verify_type2_hash(tx, tx_hash)
    if tx['blockHash'] != block_hash or quantity(tx['transactionIndex']) != index:
        raise ValueError('transaction order mismatch')
    if int(indexer['block_number']) != quantity(block['number']):
        raise ValueError('indexer block number mismatch')
    if tx['from'].lower() != indexer['from'].lower() or tx['to'].lower() != indexer['to'].lower():
        raise ValueError('participant mismatch')
    common = {'header_hash_checked': block_hash, 'transaction_hash_checked': tx_hash,
              'transaction_index': index, 'preceding_transactions': index,
              'post_block_state_root': block['stateRoot'], 'parent_hash': block['parentHash']}
    if receipt is None:
        return {**common,'cross_provider_receipt_available':False,'sender_gas_wei':None,
                'indexer_only_reported_sender_gas_wei':int(indexer['fee']['value'])}
    if receipt['transactionHash'] != tx_hash or receipt['blockHash'] != block_hash:
        raise ValueError('receipt identity mismatch')
    if quantity(receipt['transactionIndex']) != index or quantity(receipt['status']) != 1:
        raise ValueError('receipt index/status mismatch')
    if quantity(receipt['blockNumber']) != quantity(block['number']) or int(indexer['block_number']) != quantity(block['number']):
        raise ValueError('block number mismatch')
    gas, price = quantity(receipt['gasUsed']), quantity(receipt['effectiveGasPrice'])
    effective = min(quantity(tx['maxFeePerGas']),quantity(block['baseFeePerGas'])+quantity(tx['maxPriorityFeePerGas']))
    if price != effective or gas != int(indexer['gas_used']) or gas*price != int(indexer['fee']['value']):
        raise ValueError('gas accounting mismatch')
    return {**common,'cross_provider_receipt_available':True,
            'gas_used': gas, 'effective_gas_price_wei': price, 'sender_gas_wei': gas*price,
            'base_fee_burn_wei': gas*quantity(block['baseFeePerGas']),
            'priority_fee_wei': gas*(price-quantity(block['baseFeePerGas'])),
            'post_block_state_root': block['stateRoot'], 'parent_hash': block['parentHash']}


def verify_b_movements(receipt: dict) -> dict:
    transfer = '0x'+keccak256(b'Transfer(address,address,uint256)').hex()
    deposit = '0x'+keccak256(b'Deposit(address,uint256)').hex()
    withdrawal = '0x'+keccak256(b'Withdrawal(address,uint256)').hex()
    morpho='0xbbbbbbbbbb9cc5e90e3b3af64bdaf62c37eeffcb'
    executor='0x5ac9bc14376bf2727c6211960cf3cec1e2f295bd'
    venue='0x52aa899454998be5b000ad077a46bbe360f4e497'
    weth='0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2'
    ezeth='0xbf5495efe5db9ce00f80364c8b423567e58d2110'
    actual=[]; wrapping=[]
    for log in receipt['logs']:
        if log.get('removed',False) or log['transactionHash'] != TX_B or log['blockHash'] != HASH_B:
            raise ValueError('log identity mismatch')
        topics=log['topics']
        if topics[0] == transfer:
            if len(topics)!=3: raise ValueError('transfer topics')
            actual.append((log['address'], '0x'+data(topics[1],32)[12:].hex(),
                           '0x'+data(topics[2],32)[12:].hex(),int.from_bytes(data(log['data'],32),'big')))
        if log['address'] == weth and topics[0] in (deposit,withdrawal):
            if len(topics)!=2: raise ValueError('wrap topics')
            wrapping.append((topics[0],'0x'+data(topics[1],32)[12:].hex(),int.from_bytes(data(log['data'],32),'big')))
    expected=[(ezeth,morpho,executor,24343983926960874121),
              (ezeth,executor,venue,24343983926960874121),
              (weth,executor,morpho,26039738525656992415)]
    if actual != expected or wrapping != [(deposit,executor,26409680973611000000),
                                          (withdrawal,executor,368092735714237547)]:
        raise ValueError('receipt token flow mismatch')
    return {'direct_token_transfer_events_matched':3,'weth_deposit_wei':26409680973611000000,
            'weth_withdrawal_wei':368092735714237547,
            'coinbase_payment_source':'prior indexer call trace, not a native-transfer receipt event'}


def audit() -> dict:
    blocks={c:load(c+'-block.json.gz')['response']['result'] for c in ('a','b')}
    receipts={c:load(c+'-receipt.json')['response']['result'] for c in ('a','b')}
    indexers={c:json.loads((ROOT/('evidence/2026-10-17/case_'+c+'.json')).read_text())['data'] for c in ('a','b')}
    a=verify_case(blocks['a'],receipts['a'],indexers['a'],HASH_A,TX_A,226)
    b=verify_case(blocks['b'],receipts['b'],indexers['b'],HASH_B,TX_B,1)
    attempts=load('public-data-attempts.json')['reads']
    parent=json.loads(next(r['body'] for r in attempts if r['name']=='flashbots_read_only_parent_header'))['result']
    verify_header(parent,blocks['b']['parentHash'])
    if quantity(parent['number'])+1 != quantity(blocks['b']['number']): raise ValueError('parent height')
    prefix=blocks['b']['transactions'][0]; verify_type2_hash(prefix,PREFIX_B)
    prefix_receipt=load('prefix-b-receipt.json')['response']['result']
    if prefix_receipt is not None and (prefix_receipt['transactionHash']!=PREFIX_B or prefix_receipt['blockHash']!=HASH_B or quantity(prefix_receipt['transactionIndex'])!=0):
        raise ValueError('prefix receipt identity')
    overlap=sorted({l['address'] for l in prefix_receipt['logs']} & {l['address'] for l in receipts['b']['logs']}) if prefix_receipt else None
    selection=load('historical-selection.json')
    sample=load('morpho-selected-liquidations-detailed.json')['response']['data']['marketTransactions']['items']
    selected=[]
    for item in sample:
        if not selection['timestamp_gte'] <= int(item['timestamp']) <= selection['timestamp_lte'] or item['type']!='Liquidation':
            raise ValueError('sample selection mismatch')
        market=item['market']; amounts=item['data']
        selected.append({'tx_hash':item['txHash'],'block':int(item['blockNumber']),
                         'tx_index':item['txIndex'],'loan_token':market['loanAsset']['symbol'],
                         'loan_decimals':market['loanAsset']['decimals'],
                         'collateral_token':market['collateralAsset']['symbol'],
                         'collateral_decimals':market['collateralAsset']['decimals'],
                         'repaid_units':int(amounts['repaidAssets']),
                         'seized_units':int(amounts['seizedAssets']),
                         'net_result':None,'classification':'UNDETERMINED'})
    return {'classification':'RPC_INDEXER_CROSSCHECK_NOT_STATE_REPLAY','case_a':a,'case_b':b,
            'case_b_parent_state_root':parent['stateRoot'],
            'case_b_prefix':{'hash':PREFIX_B,'from':prefix['from'],'to':prefix['to'],
                             'receipt_status':quantity(prefix_receipt['status']) if prefix_receipt else None,
                             'shared_log_emitters_with_winner':overlap,
                             'state_changes_reconstructed':False},
            'case_b_movements':verify_b_movements(receipts['b']),
            'selection':{'api_observations':selected,'profit_filters_used':False,
                         'population_completeness_verified':False,'profitable_frequency':None,
                         'recent_window_observations':len(load('recent-selected-liquidations.json')['response']['data']['marketTransactions']['items'])},
            'state_root_witness_available':False,'transaction_and_receipt_trie_verified':False,
            'consensus_finality_verified':False,'fork_reproduced':False,'sponsor_accepted':False,
            'certified':False,'economically_admitted_operations':0}


if __name__ == '__main__':
    print(json.dumps(audit(),indent=2))
    raise SystemExit(2)
