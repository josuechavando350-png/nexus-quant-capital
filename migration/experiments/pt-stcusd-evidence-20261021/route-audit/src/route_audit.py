"""Offline audit of the indexed event route, NOT an EVM replay or profit proof.

No network clients, signing, transaction building or broadcasting. Input is a
normalized transcription of connector fields. Hash checks establish consistency,
not consensus authenticity. All monetary arithmetic uses integer base units.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from keccak_reference import keccak256, topic

ROOT = Path(__file__).resolve().parents[1]
TX = '0x87de0f52c1c8c2dac00671a8dba7058ccf20301107a7450471edec6a0f6f3bc2'
BLOCK = 25666958
SHAPES = {'RATE':(1,2),'ACCRUE':(1,3),'LIQUIDATE':(3,5),'TRANSFER':(2,1),
 'APPROVAL':(2,1),'INDEX':(1,0),'PY_BURN':(2,2),'VAULT_WITHDRAW':(3,2),
 'VAULT_ACCRUE':(0,4),'MORPHO_WITHDRAW':(3,3),'DEALLOCATE_MARKET':(1,2),
 'DEALLOCATE_VAULT':(2,7),'DEBT_UPDATE':(1,2),'DIVESTED':(1,1),
 'CUSD_BURN':(2,4),'SY_REDEEM':(3,2),'PY_REDEEM':(3,4),'SWAP':(2,5),
 'WETH_WITHDRAW':(1,1),'BUILDER_PAID':(1,1),'PROFIT_SWEPT':(1,1)}


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def word(value: str, aliases: dict[str,str]) -> str:
    check(isinstance(value, str), 'word must be text')
    v = aliases.get(value, value)
    if v.startswith('0x'):
        v = v[2:]
    check(bool(re.fullmatch('[0-9a-f]{1,64}', v)), 'invalid hex word')
    return v.zfill(64)


def signed256(w: str) -> int:
    n = int(w, 16)
    return n - (1 << 256) if n >= 1 << 255 else n


def expand(e: dict[str,Any], aliases: dict[str,str], kinds: dict) -> dict:
    check(set(e) == {'index','emitter','event','indexed','words'}, 'event fields')
    check(type(e['index']) is int and 0 <= e['index'] < 53, 'event index')
    check(e['emitter'] in aliases and len(aliases[e['emitter']]) == 42, 'emitter')
    check(e['event'] in SHAPES and e['event'] in kinds, 'event signature unknown')
    check((len(e['indexed']),len(e['words'])) == SHAPES[e['event']], 'event shape')
    sig, observed_hash = kinds[e['event']]
    check(topic(sig) == observed_hash, 'signature hash mismatch: '+e['event'])
    return {'index':e['index'],'address':aliases[e['emitter']],
      'topics':[observed_hash]+['0x'+word(t,aliases) for t in e['indexed']],
      'data':'0x'+''.join(word(w,aliases) for w in e['words'])}


def market_id(m: dict) -> str:
    addresses = [m['loanAsset']['address'],m['collateralAsset']['address'],m['oracle']['address'],m['irmAddress']]
    raw = b''
    for addr in addresses:
        check(isinstance(addr,str) and bool(re.fullmatch('0x[0-9a-fA-F]{40}',addr)), 'market address')
        raw += bytes.fromhex(addr[2:]).rjust(32,b'\0')
    lltv = m['lltv']
    check(isinstance(lltv,(str,int)) and not isinstance(lltv,bool), 'lltv type')
    check(0 <= int(lltv) < 1 << 256, 'lltv range')
    return '0x'+keccak256(raw+int(lltv).to_bytes(32,'big')).hex()


def usdc(n: int) -> str:
    return ('-' if n < 0 else '') + str(abs(n)//10**6)+'.'+str(abs(n)%10**6).zfill(6)


def analyze(c: dict, original: dict) -> dict:
    check(c['schema']=='nqc-normalized-event-fields-v1', 'schema')
    check(c['chain_id']==1 and c['block_number']==BLOCK and c['transaction_hash']==TX,'case identity')
    check(c['pagination_final'] is None,'pagination incomplete')
    check(len(c['pages'])==6,'page count')
    for p,i in zip(c['pages'],range(0,53,10)):
        check(p=={'first_index':i,'last_index':min(i+9,52),'next_index':i+9 if i<50 else None},'page coverage')
    A=c['addresses']; events=c['events']
    check([e['index'] for e in events]==list(range(53)), 'missing, duplicate or reordered event')
    raw=[expand(e,A,c['event_signatures']) for e in events]
    check(original['transactionHash'].lower()==TX and int(original['blockNumber'],16)==BLOCK,'archive case')
    check(int(original['transactionIndex'],16)==0 and original['removed'] is False,'archive tx index or removed')
    check(original['blockHash'].lower()==c['block_hash_from_prior_upload'],'prior block hash')
    check(raw[2]['address']==original['address'].lower() and raw[2]['topics']==[t.lower() for t in original['topics']] and raw[2]['data']==original['data'].lower(),'Liquidate differs from supplied RPC log')
    for k in ('LIQUIDATION_MARKET','WITHDRAWAL_MARKET'):
        m=c['market_catalog'][A[k]]
        check(market_id(m)==A[k],'market hash')
        check(m['loanAsset']['address'].lower()==A['USDC'] and m['loanAsset']['decimals']==6,'loan asset')
    check(A['LIQUIDATION_MARKET']!=A['WITHDRAWAL_MARKET'],'market conflation')
    def e(i: int, kind: str, emitter: str, indexed: list[str]) -> list[int]:
        ev=events[i]
        check(ev['event']==kind and ev['emitter']==emitter and ev['indexed']==indexed,'wrong economic leg '+str(i))
        return [int(word(w,A),16) for w in ev['words']]
    debt,shares,pt,bad_debt,bad_shares=e(2,'LIQUIDATE','MORPHO',['LIQUIDATION_MARKET','EXECUTOR','BORROWER'])
    check(bad_debt==bad_shares==0,'bad debt outside case scope')
    withdraw=e(19,'MORPHO_WITHDRAW','MORPHO',['WITHDRAWAL_MARKET','ADAPTER','ADAPTER'])
    check(withdraw[0]==int(A['ADAPTER'],16),'withdraw caller')
    redeemed=withdraw[1]
    route=['MORPHO','ADAPTER','VAULT','STRATEGY','RESERVE','CUSD','SY','EXECUTOR']
    indices=[20,22,25,28,32,35,37]
    for i,fr,to in zip(indices,route,route[1:]):
        check(e(i,'TRANSFER','USDC',[fr,to])==[redeemed],'broken USDC path '+str(i))
    check(e(42,'TRANSFER','USDC',['EXECUTOR','MORPHO'])==[debt],'repayment')
    swap_in=e(46,'TRANSFER','USDC',['EXECUTOR','POOL'])[0]
    payout=e(51,'TRANSFER','USDC',['EXECUTOR','PAYOUT'])[0]
    check(redeemed-debt==swap_in+payout,'USDC conservation')
    check(e(10,'PY_BURN','YT',['ROUTER','SY'])[0]==pt,'PT amount')
    sy=e(10,'PY_BURN','YT',['ROUTER','SY'])[1]
    st_assets,st_shares=e(14,'VAULT_WITHDRAW','STCUSD',['SY','BURNER','SY'])
    check(st_shares==sy,'stcUSD shares')
    for idx,token,fr,to,amount in [(3,'PT','MORPHO','EXECUTOR',pt),(6,'PT','EXECUTOR','YT',pt),
      (7,'PT','YT','ZERO',pt),(9,'SY','YT','SY',sy),(11,'SY','SY','ZERO',sy),
      (12,'STCUSD','SY','ZERO',sy),(13,'CUSD','STCUSD','BURNER',st_assets),(15,'CUSD','BURNER','ZERO',st_assets)]:
        check(e(idx,'TRANSFER',token,[fr,to])==[amount],'redemption asset leg '+str(idx))
    check(e(38,'SY_REDEEM','SY',['ROUTER','EXECUTOR','USDC'])==[sy,redeemed],'SY redeem')
    check(e(39,'PY_REDEEM','ROUTER',['EXECUTOR','USDC','YT'])==[int(A['EXECUTOR'],16),pt,redeemed,sy],'router redeem')
    check(e(34,'DIVESTED','CUSD',['USDC'])==[redeemed],'reserve divestment')
    for idx,emitter,caller in [(26,'VAULT','STRATEGY'),(29,'STRATEGY','RESERVE'),(33,'RESERVE','CUSD')]:
        check(e(idx,'VAULT_WITHDRAW',emitter,[caller]*3)[0]==redeemed,'vault withdrawal')
    change=e(30,'DEBT_UPDATE','RESERVE',['STRATEGY'])
    check(change[0]-change[1]==redeemed,'strategy debt change')
    weth=e(45,'TRANSFER','WETH',['POOL','EXECUTOR'])[0]
    swap=e(47,'SWAP','POOL',['SWAP_ROUTER','EXECUTOR'])
    check(swap[0]==swap_in and signed256(word(events[47]['words'][1],A))==-weth,'swap leg sign/amount')
    check(swap[2] < 1<<160 and swap[3] < 1<<128 and swap[4] < 1<<23,'swap field widths')
    unwrap=e(49,'WETH_WITHDRAW','WETH',['EXECUTOR'])[0]
    check(e(50,'BUILDER_PAID','EXECUTOR',['BUILDER'])==[unwrap],'declared builder event vs withdrawal')
    check(weth>=unwrap,'withdrawal exceeds observed new WETH')
    # Event names/argument labels are not evidence of recipient identity.
    check(e(52,'PROFIT_SWEPT','EXECUTOR',['USDC'])==[payout],'swept event amount')
    check(A['USDC']!=A['PAYOUT'],'token mistaken for payout address')
    # Prefix bookkeeping uses all retrieved USDC Transfer events, not just endpoints.
    net=defaultdict(int); low=defaultdict(int); seen=[]
    for ev in events:
        if ev['event']=='TRANSFER' and ev['emitter']=='USDC':
            fr,to=ev['indexed']; amount=int(word(ev['words'][0],A),16)
            check(fr!=to and fr!='ZERO' and to!='ZERO','unexpected mint/self transfer')
            net[fr]-=amount;low[fr]=min(low[fr],net[fr])
            net[to]+=amount;low[to]=min(low[to],net[to]);seen.append(ev['index'])
    check(seen==indices+[42,46,51],'additional USDC transfers outside modeled path')
    check(net['MORPHO']==-(redeemed-debt) and net['EXECUTOR']==0,'terminal USDC ledger')
    check(all(net[n]==0 for n in route[1:-1]),'intermediary residual')
    check(-low['MORPHO']==redeemed and low['EXECUTOR']==0,'prefix liquidity')
    return {'status':'INDEXED_ROUTE_RECONCILED_EVM_PENDING','transaction_hash':TX,'block':BLOCK,
      'events_observed':53,'pages':6,'primary_market':A['LIQUIDATION_MARKET'],'redemption_funding_market':A['WITHDRAWAL_MARKET'],
      'funding_market_label_from_prior_catalog':'cbBTC/USDC','path':route,'path_transfer_indices':indices,
      'usdc_redemption':usdc(redeemed),'usdc_debt':usdc(debt),'usdc_after_debt':usdc(redeemed-debt),
      'usdc_conversion_to_weth':usdc(swap_in),'usdc_payout':usdc(payout),
      'observed_transfer_prefix_initial_usdc_requirement':{k:usdc(-v) for k,v in low.items() if v<0},
      'interpretation_of_prefix':'Necessary arithmetic balance under the retrieved transfer sequence; not measured prestate balance, complete solvency proof, or sufficient condition for withdrawal.',
      'usdc_net_by_node':{k:usdc(v) for k,v in sorted(net.items())},
      'weth_increment_wei':str(weth-unwrap),'builder_paid_event_wei':str(unwrap),
      'asset_redemption_not_generic_pt_dex_sale':True,
      'requires_withdrawal_market_liquidity_and_vault_state':True,
      'liquidation_event_index':2,'actual_debt_transfer_index':42,
      'sweep_event_indexed_field_is_token_not_payout':True,
      'state_proof_verified':False,'runtime_code_identity_verified':False,'full_call_trace_available':False,
      'original_evm_replay_executed':False,'nqc_evm_replay_executed':False,'titan_sponsorship_confirmed':False,
      'nqc_net_profit':None,'live_executable':False,
      'next_required_inputs':['Full original transaction calldata/serialized bytes and raw receipt','Historical parent accounts, bytecode and storage, including both Morpho markets and all redemption dependencies','Exact target block context and applicable system transitions','Local EVM toolchain; original receipt parity before any NQC variant']}


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=ROOT)
    args=p.parse_args();r=args.root
    c=json.loads((r/'inputs/route_evidence.json').read_text())
    original=json.loads((r/'reference/selected_log.json').read_text())
    result=analyze(c,original)
    print(json.dumps(result,indent=2,ensure_ascii=False))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
