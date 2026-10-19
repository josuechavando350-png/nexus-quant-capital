"""Offline Morpho evidence sufficiency and economic decision. Never an EVM replay.

Reads immutable Git objects only. Missing accounts, code, storage, financing and
capture terms stay unknown. No RPC transport or transaction construction exists.
"""
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path
import gzip
import hashlib
import json
import subprocess
from Crypto.Hash import keccak

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SOURCE = '0f26557c1f83e12efcf364ece6cebd8505d2e2c2'
BASE = '014850d71b45d8a18eedfcc14b922fa51efb7512'
PREFIX = 'migration/experiments/morpho-sponsored-gas/'
TX = '0x46300e9614c547118ecdd524bc7218208088cc4ae9e5bd534e62055d38f9925b'
TX0 = '0x0c5ba40ae213874eb37df22686f53729371378171d81dc9899a599351d2759f0'
BLOCK = '0x5d499e63c5d119293a906036f369d8d75f9560618efec0ff916e4fefa33dfda8'
PARENT = '0xf57a30121eac97b983cad86fcb3107787a9d400ca4d69d5a96a4b1b618ac65dc'
MORPHO = '0xbbbbbbbbbb9cc5e90e3b3af64bdaf62c37eeffcb'
WETH = '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2'
EZETH = '0xbf5495efe5db9ce00f80364c8b423567e58d2110'
EXECUTOR = '0x5ac9bc14376bf2727c6211960cf3cec1e2f295bd'
LIQUIDITY = '0x52aa899454998be5b000ad077a46bbe360f4e497'
POOL = '0xdd72157a021804141817d46d9852a97addfb9f59'
INSUFFICIENT = 'EVIDENCIA_INSUFICIENTE'
DISCARDED = 'ECONOMICAMENTE_DESCARTADO'


def require(ok, why):
    if not ok:
        raise ValueError(why)


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def parse(raw):
    return json.loads(raw, object_pairs_hook=pairs)


def uint(value):
    if type(value) is str and value.isascii() and value.isdigit() and str(int(value)) == value:
        value = int(value)
    require(type(value) is int and 0 <= value < 2**256, 'exact uint256 required')
    return value


def words(data):
    require(type(data) is str and data.startswith('0x') and len(data[2:]) % 64 == 0, 'ABI word boundary')
    return [int(data[i:i+64],16) for i in range(2,len(data),64)]


def addr(value):
    require(0 <= value < 2**160, 'address overflow')
    return '0x'+value.to_bytes(20,'big').hex()


def kh(raw):
    h = keccak.new(digest_bits=256); h.update(raw); return h.digest()


def mapping_slot(key, slot):
    return int.from_bytes(kh(uint(key).to_bytes(32,'big')+uint(slot).to_bytes(32,'big')),'big')


class Sources:
    def __init__(self):
        self.manifest = parse((HERE/'SOURCE_MANIFEST.json').read_bytes())
        self.cache = {}
        self.used = set()

    def raw(self, name):
        if name not in self.cache:
            pin = self.manifest['files'][name]
            raw = subprocess.check_output(['git','-C',str(REPO),'show',pin['commit']+':'+pin['path']])
            require(hashlib.sha256(raw).hexdigest() == pin['sha256'], 'source SHA256: '+name)
            blob = hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
            require(blob == pin['git_blob_sha1'], 'source blob: '+name)
            self.cache[name] = raw
        self.used.add(name)
        return self.cache[name]

    def json(self, name):
        raw = self.raw(name)
        return parse(gzip.decompress(raw) if name.endswith('.gz') else raw)


def trace_contexts(envelope):
    require(envelope['pagination'] is None, 'incomplete trace pages')
    require(envelope['request']['chain_id'] == '1' and TX in envelope['request']['endpoint_path'], 'trace identity')
    tree = {}
    for row in envelope['data']['items']:
        p = tuple(row['traceAddress'])
        require(all(type(x) is int and x >= 0 for x in p) and p not in tree, 'invalid trace path')
        require(row['type'] == 'call' and not row.get('error') and 'result' in row, 'unsupported trace')
        tree[p] = row
    require(() in tree, 'missing root')
    contexts = {}
    for p, row in sorted(tree.items(),key=lambda item:(len(item[0]),item[0])):
        children = {q[-1] for q in tree if len(q)==len(p)+1 and q[:-1]==p}
        require(children == set(range(row['subtraces'])), 'incomplete child calls')
        action = row['action']; typ = action['callType']
        require(typ in ('call','staticcall','delegatecall'), 'unsupported call type')
        if p:
            require(p[:-1] in contexts and action['from'].lower() == contexts[p[:-1]], 'caller context conflict')
        require(p or typ == 'call', 'root must be CALL')
        contexts[p] = contexts[p[:-1]] if typ == 'delegatecall' else action['to'].lower()
    return tree, contexts


def derive_morpho_slots(market_id, borrower, market_words, position_words, params):
    require(len(market_words)==6 and len(position_words)==3 and len(params)==5, 'word membership')
    require(all(0 <= v < 2**128 for v in market_words+position_words[1:]), 'packed uint128 overflow')
    market_base = mapping_slot(int(market_id,16),3)
    position_base = mapping_slot(int(borrower,16),mapping_slot(int(market_id,16),2))
    params_base = mapping_slot(int(market_id,16),8)
    rows=[]
    for offset, label in enumerate(('totalSupplyAssets/totalSupplyShares','totalBorrowAssets/totalBorrowShares','lastUpdate/fee')):
        rows.append((market_base+offset,label,market_words[2*offset]+(market_words[2*offset+1]<<128),'IRM calldata before accrual'))
    rows += [(position_base,'borrower.supplyShares',position_words[0],'position getter inside B'),
             (position_base+1,'borrower.borrowShares/collateral',position_words[1]+(position_words[2]<<128),'position getter inside B')]
    rows += [(params_base+i,'marketParams.'+label,params[i],'liquidate calldata; not a storage read')
             for i,label in enumerate(('loanToken','collateralToken','oracle','irm','lltv'))]
    return [{'account':MORPHO,'slot':'0x'+uint(slot).to_bytes(32,'big').hex(),'meaning':label,
             'observed_or_expected_word':'0x'+uint(value).to_bytes(32,'big').hex(),'observation_scope':scope,
             'authenticated_parent_value':None,'authenticated_pre_tx1_value':None,
             'proof':None,'layout_runtime_binding_verified':False} for slot,label,value,scope in rows]


def witness_boundary(s):
    trace=s.json('evidence/2026-10-17/case_b_trace.json'); tree, contexts=trace_contexts(trace)
    block=s.json('evidence/2026-10-17-profitability/b-block.json.gz')['response']['result']
    receipt=s.json('evidence/2026-10-17-profitability/b-receipt.json')['response']['result']
    order=s.json('evidence/2026-10-17-prospective-recovered/transaction-order.json')
    require(block['hash']==BLOCK and block['parentHash']==PARENT and int(block['number'],16)==26190955,'block identity')
    require(order['block_hash']==BLOCK and order['target_transaction_hash']==TX and
            order['transactions_root_verified']==block['transactionsRoot'],'inherited order binding')
    tx0, tx1=block['transactions'][:2]
    require(tx0['hash']==TX0 and tx1['hash']==TX and int(tx1['transactionIndex'],16)==1,'prefix order')
    require(int(tx0['chainId'],16)==int(tx1['chainId'],16)==1,'wrong chain')
    require(receipt['transactionHash']==TX and receipt['blockHash']==BLOCK and int(receipt['transactionIndex'],16)==1
            and receipt['status']=='0x1','receipt identity')
    require(tree[()]['action']['input']==tx1['input'],'full execution input conflict')
    require(tree[()]['action']['from']==tx1['from'] and tree[()]['action']['to']==tx1['to'],'root actors')
    liq=tree[(0,1,3)]; params_and_args=words('0x'+liq['action']['input'][10:10+9*64])
    require(liq['action']['to']==MORPHO and liq['action']['input'][:10]=='0xd8eabcb8','liquidate identity')
    params=params_and_args[:5]
    market_id='0x'+kh(b''.join(v.to_bytes(32,'big') for v in params)).hex()
    borrower=addr(params_and_args[5])
    config=parse(s.json('evidence/2026-10-17-profitability/public-data-attempts.json')['reads'][0]['body'])['data']
    require(config['market_id']==market_id and config['chain_id']==1,'independent configuration identity')
    addresses=[addr(x) for x in params[:4]]
    require(addresses==[config[k].lower() for k in ('loan_token','collateral_token','oracle_address','irm_address')]
            and params[4]==int(config['lltv_wad']),'market parameter conflict')
    require(addresses[:2]==[WETH,EZETH],'asset identity')
    irm=tree[(0,1,3,0)]; oracle=tree[(0,1,3,1)]
    require(irm['action']['to']==addresses[3] and oracle['action']['to']==addresses[2],'oracle/IRM identity')
    irm_words=words('0x'+irm['action']['input'][10:])
    require(irm_words[:5]==params,'IRM parameters conflict')
    position=tree[(0,0)]
    require(position['action']['to']==MORPHO and
            position['action']['input'][:10]=='0x'+kh(b'position(bytes32,address)')[:4].hex() and
            words('0x'+position['action']['input'][10:])==[int(market_id,16),int(borrower,16)],'position identity')
    mwords=irm_words[5:]
    pwords=words(tree[(0,0)]['result']['output'])
    # Stored upstream layout is evidence of derivation only, not historical runtime.
    s.raw('@MorphoStorageLib.sol');s.raw('@IMorpho.sol');s.raw('@Morpho.sol')
    slots=derive_morpho_slots(market_id,borrower,mwords,pwords,params)
    ref=s.json('fixtures/fluid_case_b_reference.json');cfg=ref['constructor_args'][0]
    require(ref['address'].lower()==POOL and cfg['liquidity'].lower()==LIQUIDITY,'Fluid identity')
    for path,row in sorted(tree.items()):
        action=row['action']
        if action['to']==LIQUIDITY and action['input'].startswith('0xb5c736e4'):
            slot='0x'+action['input'][10:]
            names=[k for k,v in cfg.items() if k.endswith('Slot') and v.lower()==slot]
            require(len(names)==1 and len(words(row['result']['output']))==1,'Fluid slot identity')
            slots.append({'account':LIQUIDITY,'slot':slot,'meaning':names[0],
                'observed_or_expected_word':row['result']['output'],'trace_path':list(path),
                'observation_scope':'inside B before Fluid operate; not parent/pre-tx1 witness',
                'authenticated_parent_value':None,'authenticated_pre_tx1_value':None,'proof':None,
                'layout_runtime_binding_verified':False})
    roles={MORPHO:'Morpho',WETH:'loan token',EZETH:'collateral token',EXECUTOR:'external executor',
           LIQUIDITY:'Fluid Liquidity',POOL:'Fluid pool',addresses[2]:'oracle',addresses[3]:'IRM',
           block['miner']:'coinbase recipient; code absence not proved'}
    accounts=sorted({a for row in tree.values() for a in (row['action']['from'].lower(),row['action']['to'].lower())}
                    |{tx0['from'],tx0['to']})
    targets={row['action']['to'].lower() for row in tree.values()}
    storage_accounts=set(contexts.values())
    account_rows=[]
    for account in accounts:
        paths=[list(p) for p,row in sorted(tree.items()) if row['action']['to'].lower()==account]
        account_rows.append({'address':account,'role':roles.get(account,'prefix actor' if account in (tx0['from'],tx0['to']) else 'observed execution dependency'),
            'B_code_destination':account in targets,'B_storage_context':account in storage_accounts,
            'code_call_paths':paths,'account_proof_at_parent':None,'code_or_empty_code_proof_at_parent':None,
            'authenticated_balance_nonce_storage_root_code_hash':None,
            'known_slot_keys_in_this_inventory':[r['slot'] for r in slots if r['account']==account],
            'other_storage_keys':'NOT_ENUMERABLE_FROM_CALL_TRACE; need opcode/state witness and runtime/layout' if account in storage_accounts else 'PREFIX_EFFECTS_UNKNOWN' if account in (tx0['from'],tx0['to']) else None})
    parent_reads=s.json('evidence/2026-10-17-profitability/public-data-attempts.json')['reads']
    parent=parse(next(r['body'] for r in parent_reads if r['name']=='flashbots_read_only_parent_header'))['result']
    require(parent['hash']==PARENT and int(parent['number'],16)==26190954,'parent identity')
    prefix_receipt=s.json('evidence/2026-10-17-profitability/prefix-b-receipt.json')
    require(prefix_receipt['request']['params']==[TX0] and prefix_receipt['response']['result'] is None,'prefix receipt availability')
    prefix_gas=int(receipt['cumulativeGasUsed'],16)-int(receipt['gasUsed'],16)
    require(0 <= prefix_gas <= int(tx0['gas'],16),'inconsistent cumulative gas')
    prestate_attempt=s.json('evidence/2026-10-17-profitability/b-prestate.json')
    code_attempt=s.json('evidence/2026-10-17-profitability/parent-executor-code.json')
    require(prestate_attempt['request']['params'][0]==TX and prestate_attempt['http_status']==403,'archived prestate refusal')
    require(code_attempt['request']['params']==[EXECUTOR,{'blockHash':PARENT,'requireCanonical':True}]
            and code_attempt['response']['error']['code']==-32603,'archived parent code failure')
    direct_reads=[{'trace_path':list(p),'code_address':row['action']['to'],'storage_account':contexts[p],
                  'selector':row['action']['input'][:10],'input':row['action']['input'],'output':row['result']['output'],
                  'scope':'INTRATRANSACTION_OBSERVATION_NOT_STORAGE_PROOF'}
                 for p,row in sorted(tree.items()) if row['action']['callType']=='staticcall']
    return {'classification':INSUFFICIENT,'chain_id':1,'market_id':market_id,'borrower':borrower,
        'contracts':dict(zip(('loan_token','collateral_token','oracle','irm'),addresses)),'lltv':str(params[4]),
        'parent_block':26190954,'parent_hash':PARENT,'parent_state_root':parent['stateRoot'],
        'block':26190955,'block_hash':BLOCK,'target_tx':TX,'target_index':1,
        'inherited_order_proof':'transaction-order.json; hash-pinned prior verifier result; not rerun',
        'prefix':[{'index':0,'hash':TX0,'from':tx0['from'],'to':tx0['to'],
            'input_selector':tx0['input'][:10],'input_bytes':(len(tx0['input'])-2)//2,
            'gas_limit':int(tx0['gas'],16),'inferred_gas_from_B_receipt':prefix_gas,
            'inference_limit':'receipt observation, not prefix status/logs/state/receipt-trie proof',
            'receipt':None,'call_trace':None,'state_diff':None,'executed':False}],
        'B_trace_calls':len(tree),'B_distinct_code_destinations':len(targets),
        'B_distinct_storage_contexts':len(storage_accounts),'account_inventory':account_rows,
        'delegate_contexts':[{'trace_path':list(p),'code_address':row['action']['to'],'storage_account':contexts[p]}
            for p,row in sorted(tree.items()) if row['action']['callType']=='delegatecall'],
        'exact_known_slot_requirements':slots,'static_call_observations':direct_reads,
        'complete_storage_access_set_known':False,
        'archived_access_results':{'prestate_tracer':{'http_status':403,
            'error':parse(prestate_attempt['body'])['error'],'observed_at':prestate_attempt['observed_at_utc']},
            'executor_parent_code':{'request':code_attempt['request'],
            'error':code_attempt['response']['error'],'observed_at':code_attempt['observed_at_utc']},
            'interpretation':'Historical failures only. Provider error text is preserved, not corrected to match requested parent.',
            'new_requests_or_retries':0},
        'missing_global_evidence':['authenticated parent account/storage witness and code or code-absence proofs',
            'fork/chain configuration applicable to timestamp 1791983495 and its pre-transaction system transitions',
            'tx0 execution state/access witness and any dependencies absent from B call trace',
            'derived exact pre-tx1 state; parent or end-of-block roots are not substitutes',
            'runtime binding including proxies, delegate implementations and oracle dependencies',
            'receipt/state parity and independent canonical/finality anchor'],
        'historical_replay_attempted':False,'reason_no_replay':'MISSING_MANDATORY_STATE; no zero-filled or poststate reconstruction',
        'commercial_admission':False}


def classify_upper_bound(value):
    return DISCARDED if value <= 0 else INSUFFICIENT


def fee_ceiling(debt,bps):
    require(type(debt) is int and debt>=0 and Fraction(bps)>=0,'negative cost')
    value=Fraction(debt)*Fraction(bps)/10000
    return -(-value.numerator//value.denominator)


def economics(s):
    prior=s.json('@nqc053-economics.json')['case_b']
    require(prior['tx_hash']==TX and prior['chain_id']==1 and not prior['commercial_admission'],'prior case scope')
    sale,debt,bid,gas=[prior[k] for k in ('sale_output_eth_wei','repaid_debt_weth_wei','coinbase_transfer_wei','gas_cost_wei')]
    residual=sale-debt-bid-gas
    require(residual==prior['residual_upper_bound_before_unknown_obligations_wei'],'economic identity')
    tx=s.json('evidence/2026-10-17-profitability/b-block.json.gz')['response']['result']['transactions'][1]
    trace=s.json('evidence/2026-10-17/case_b_trace.json');tree,_=trace_contexts(trace)
    allowance=tree[(0,1,1)];before=tree[(0,1,0)]
    require(allowance['action']['input'][:10]=='0xdd62ed3e' and before['action']['input'][:10]=='0x70a08231','warm executor reads')
    require(allowance['action']['to']==before['action']['to']==WETH and
            words('0x'+allowance['action']['input'][10:])==[int(EXECUTOR,16),int(MORPHO,16)] and
            words('0x'+before['action']['input'][10:])==[int(EXECUTOR,16)],'executor funding read identity')
    scenarios=[]
    for bps in (Fraction(0),Fraction(1,2),Fraction(1)):
        fee=fee_ceiling(debt,bps);zero_gas_upper=sale-debt-bid-fee
        scenarios.append({'id':'B_full_debt_fee_'+str(bps),'scope':'same sale and full observed coinbase transfer; nonnegative remaining costs',
            'hypothetical_fee_bps':str(bps),'fee_wei':fee,'upper_bound_even_if_gas_zero_wei':zero_gas_upper,
            'observed_gas_residual_before_unknown_costs_wei':zero_gas_upper-gas,
            'decision':classify_upper_bound(zero_gas_upper),
            'real_financing_offer_evidenced':False,'all_Morpho_liquidations_discarded':False})
    s.raw('@sponsorship-gaps.md')
    return {'case_B_decision':INSUFFICIENT,'historical_external_residual_upper_bound_wei':residual,
        'inherited_reconciled_ledger':{'source':'@nqc053-economics.json; immutable inputs, original reconciliation not rerun',
            'seized_ezETH_raw':prior['seized_ezeth_wei'],'repaid_WETH_raw':debt,
            'observed_sale_ETH_wei':sale,'sale_minus_debt_ETH_wei':sale-debt,
            'coinbase_ETH_wei':bid,'gas_ETH_wei':gas,'obligations_not_evidenced':None},
        'same_sale_same_bid_zero_gas_upper_bound_wei':sale-debt-bid,
        'absolute_max_gain_from_removing_all_observed_gas_wei':gas,
        'max_gain_fraction_of_observed_residual':str(Fraction(gas,residual)),
        'full_debt_fee_break_even_even_at_zero_gas_bps':str(Fraction((sale-debt-bid)*10000,debt)),
        'scenarios':scenarios,
        'competition_boundary':{'observed_coinbase_transfer_wei':bid,
            'max_coinbase_for_positive_at_observed_sale_gas_before_other_costs_wei':sale-debt-gas-1,
            'additional_bid_tolerance_for_strict_positive_wei':residual-1,
            'bid_needed_for_double_observed_residual_if_everything_else_same_wei':bid-residual,
            'required_bid_reduction_for_double_residual_wei':residual,
            'acceptance_of_lower_bid':None,'competitor_bids':None,'capture_probability':None,
            'interpretation':'Lower bid creates an arithmetic gain but has no demonstrated inclusion or competition support'},
        'funding':{'B_sender':tx['from'],'B_executor':tx['to'],'B_sender_nonce':int(tx['nonce'],16),
            'gas_limit':int(tx['gas'],16),'max_fee_per_gas_wei':int(tx['maxFeePerGas'],16),
            'nominal_gas_limit_times_max_fee_wei':int(tx['gas'],16)*int(tx['maxFeePerGas'],16),
            'historical_sender_balance':None,'observed_gas_expenditure_wei':gas,
            'executor_prior_WETH_observed':str(words(before['result']['output'])[0]),
            'executor_prior_allowance_to_Morpho_observed':str(words(allowance['result']['output'])[0]),
            'allowance_scope':'inside B; not an authenticated prestate word',
            'gas_sponsor_commitment':None,'sponsor_premium':None,'failure_liability':None,
            'new_executor_setup_gas':None,'new_executor_capture_advantage':None,
            'collateral_first_callback':'supported by source and observed call order; no full-debt loan needed for that route',
            'zero_initial_operator_capital_demonstrated':False,
            'principal_advance_is_income':False},
        'sale':{'pool':POOL,'liquidity_contract':LIQUIDITY,'output_wei':sale,
            'historical_fill_observed':True,'ex_ante_executable_quote':None,
            'authentic_prestate_reserves_or_limits':None,'counterfactual_liquidity':None,
            'venue_costs':'already embedded in observed output; not subtracted twice'},
        'stop_rule':'Stop speculative optimization of full-debt financing >=1bp under same sale/bid; even zero gas cannot save it.',
        'candidate_acceptance':'Collateral-first case remains insufficient, not globally rejected.',
        'monthly_forecast_usd':None,'commercial_admission':False}


def candidate_triage(s):
    grouped=defaultdict(list)
    for i in range(2):
        page=s.json(f'evidence/2026-10-17-monthly/page-{i:03}.json')
        for r in page['response']['data']['marketTransactions']['items']:
            require(r['chain']['id']==1 and r['type']=='Liquidation','candidate chain/type')
            grouped[r['txHash'].lower()].append(r)
    require(sum(map(len,grouped.values()))==143 and len(grouped)==141,'sample identity')
    selection=s.json('evidence/2026-10-17-monthly/receipt-selection.json')['transactions']
    availability={TX:'AVAILABLE'}
    for i,row in enumerate(selection):
        if row['tx_hash']==TX:continue
        reply=s.json(f'evidence/2026-10-17-monthly/receipt-{i:02}.json')
        require(reply['request']['params']==[row['tx_hash']] and reply['response']['result'] is None,'receipt selection changed')
        availability[row['tx_hash']]='OBSERVED_NULL'
    detailed=s.json('evidence/2026-10-17-profitability/morpho-selected-liquidations-detailed.json')['response']['data']['marketTransactions']['items']
    c=next(r for r in detailed if r['txHash']!=TX)
    require(s.json('evidence/2026-10-17-profitability/c-receipt.json')['response']['result'] is None,'C receipt availability')
    availability[c['txHash']]='OBSERVED_NULL'
    rows=[]
    for tx,events in sorted(grouped.items(),key=lambda x:(x[1][0]['blockNumber'],x[1][0]['txIndex'])):
        require(len({r['logIndex'] for r in events})==len(events),'duplicate candidate event')
        rows.append({'tx_hash':tx,'chain_id':1,'block':events[0]['blockNumber'],'tx_index':events[0]['txIndex'],
            'event_count':len(events),'market_ids':sorted({r['market']['marketId'] for r in events}),
            'debt_and_collateral':[{'loan_token':r['market']['loanAsset']['address'].lower(),
                'collateral_token':r['market']['collateralAsset']['address'].lower(),
                'debt_repaid_raw':str(uint(r['data']['repaidAssets'])),
                'collateral_seized_raw':str(uint(r['data']['seizedAssets'])),
                'bad_debt_raw':str(uint(r['data']['badDebtAssets']))} for r in events],
            'receipt_status':availability.get(tx,'NO_ARCHIVED_RECEIPT_IDENTIFIED'),
            'evidence_rank':1 if tx==TX else 3,'net_margin':None,'decision':INSUFFICIENT,
            'blocker':'exact state, funding and capture' if tx==TX else 'no complete sale/gas/bid/funding ledger or authenticated state'})
    a=s.json('observations/ethereum_morpho_2026-06-26_seed.json')
    acfg=s.json('observations/ethereum_morpho_2026-06-26_market_params.json')
    ablock=s.json('evidence/2026-10-17-profitability/a-block.json.gz')['response']['result']
    require(ablock['transactions'][226]['hash']==a['transaction_hash'] and acfg['transaction_hash']==a['transaction_hash'],'A identity')
    require(s.json('evidence/2026-10-17-profitability/a-receipt.json')['response']['result'] is None,'A receipt availability')
    arow={'label':'A','chain_id':1,'tx_hash':a['transaction_hash'],'block':a['block_number'],'tx_index':226,
        'prefix_transactions_required':226,'morpho':acfg['morpho_contract'].lower(),
        'market_id':acfg['market_id'],'borrower':acfg['borrower'].lower(),
        'loan_token':a['loan_token'].lower(),'collateral_token':a['collateral_token'].lower(),
        'repaid_loan_raw':a['repaid_loan_raw'],'seized_collateral_raw':a['seized_collateral_raw'],
        'callback_data':a['callback_data'],'gas_cost_indexer_only_wei':a['actual_fee_wei'],
        'evidence_rank':2,'decision':INSUFFICIENT,'net_margin':None,
        'missing':['sale route and liquidity','repayment financing; original callback empty','authenticated receipt/prestate/prefix','competitive inclusion and sponsor obligations']}
    mixed={k:int(s.json('evidence/2026-10-17-prospective-recovered/sample-00/'+k+'.json')['response']['data']['last_indexed_block']) for k in ('market','position','oracle')}
    partial=s.json('@partial-other-block.json')
    return {'scope':'all 141 monthly transactions plus earlier case A; C is already in monthly sample',
        'monthly_transactions':rows,'older_case_A':arow,
        'case_C':{'tx_hash':c['txHash'],'block':c['blockNumber'],'tx_index':c['txIndex'],
            'debt_USDT_raw':str(uint(c['data']['repaidAssets'])),'collateral_wstETH_raw':str(uint(c['data']['seizedAssets'])),
            'decision':INSUFFICIENT,'net_margin':None,'reason':'small debt is not evidence of negative net; sale/gas/bid/financing absent'},
        'monthly_receipt_coverage':dict(Counter(r['receipt_status'] for r in rows)),
        'potential_margin_ranking':'UNAVAILABLE; no cross-token price, sale or net evidence for alternatives',
        'priority_by_evidence':['B: full receipt and call trace; blocked prestate/funding/capture',
                                'A: full block and indexer transaction; no sale ledger, 226-prefix burden',
                                'C and other monthly rows: event observations only; no economic admission'],
        'excluded_state_sources':[{'source':'prospective REST sample','indexed_blocks':mixed,
            'reason':'mixed later blocks, not historical B prestate'},
            {'source':'partial Morpho witness','block':partial['block_number_claim'],
             'market_id':partial['market_id'],'borrower':partial['borrower'],'state_root':partial['state_root_claim'],
             'reason':'different block/market/borrower, unauthenticated source root; not a candidate or B witness'}],
        'viable_candidates_with_delimited_evidence':0,'commercial_admission':False}


def inventory(s):
    markers=[]; files=0
    interesting={'accountProof','storageProof','structLogs','prestate'}
    def visit(value,path,source):
        if isinstance(value,dict):
            for k,v in value.items():
                if k in interesting:markers.append({'source':source,'path':path+'/'+k,'type':type(v).__name__})
                visit(v,path+'/'+k,source)
        elif isinstance(value,list):
            for i,v in enumerate(value):visit(v,path+'/'+str(i),source)
    for name,pin in s.manifest['files'].items():
        if pin['commit']==SOURCE and (name.endswith('.json') or name.endswith('.json.gz')):
            visit(s.json(name),'',name);files+=1
    return {'scope':'JSON and compressed JSON files in pinned Morpho experiment; not an account-wide archive search',
        'files_scanned':files,'proof_or_opcode_marker_hits':markers,
        'limitation':'marker scan is inventory only, not a proof verifier or exhaustive storage-access analysis'}


def analyze(s=None):
    s=s or Sources()
    reports={'prestate':witness_boundary(s),'economics':economics(s),'candidates':candidate_triage(s),'archive_inventory':inventory(s)}
    reports['monthly_evidence']={'demonstrated_NQC_net_per_capture':None,'hypothetical_net_is_not_admitted':True,
        'observed_monthly_events':143,'observed_monthly_transactions':141,'demonstrated_capturable_frequency':None,
        'targets_usd':[5000,15000,45000],'forecast_usd':None,
        'required_captures_relation':'ceil((target + monthly recurring and failed-attempt costs) / positive net USD per capture); denominator and costs unmeasured',
        'required_for_each_target':['coherent pre-trade state and deterministic execution parity',
            'real financing availability, advance/repayment and failure liabilities',
            'net asset ledger per capture with historical USD conversion and all costs',
            'observed eligible opportunities and capture/failure denominators over multiple windows',
            'competitive inclusion evidence; deployment, top-up, operating and failed-attempt costs',
            'liquidity/capital concurrency limits and sponsor capacity without initial owner principal'],
        '5000_gate':'first prove positive financed capturable net and repeatable volume',
        '15000_45000_gate':'only after 5000 evidence; measure marginal liquidity, competition and financing constraints',
        'commercial_admission':False}
    reports['sources_verified']=sorted(s.used)
    reports['status']={'case_B':INSUFFICIENT,'full_debt_financing_at_least_1bp_same_sale_bid':DISCARDED,
        'live_replay':False,'RPC_requests':0,'triport_used_this_experiment':0,'triport_total_known':0,
        'triport_lifetime_budget':8,'new_budget_created':False,'commercial_admission':False}
    return reports


if __name__=='__main__':
    print(json.dumps(analyze(),indent=2,sort_keys=True))
