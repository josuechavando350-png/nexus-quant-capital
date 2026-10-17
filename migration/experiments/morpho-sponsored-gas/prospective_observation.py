"""One finite, public read-only observation per invocation; no monitoring service.

REST heights and local receipt times remain separate. A matching header does not
prove REST state. Mixed heights, unknown accrual and missing DEX quotes block
economic admission. No eth_call retry, wallet, signing or submission interface.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import urllib.error
import urllib.request
from historical_prestate_probe import market_id
from historical_rpc_audit import data, quantity, verify_header
from monthly_census import integer

API = 'https://api.morpho.org'
RPC = 'https://rpc.flashbots.net/fast'


def now():
    return datetime.now(timezone.utc).isoformat()


def instant(value):
    result = datetime.fromisoformat(value)
    if result.utcoffset() is None: raise ValueError('timezone required')
    return result


def save(path, record):
    with path.open('x') as output: output.write(json.dumps(record,indent=2)+'\n')


def request(path, url, payload=None):
    if path.exists(): raise ValueError('evidence exists; no overwrite or retry')
    if payload is None:
        if not url.startswith(API+'/v0/'): raise ValueError('public Morpho GET only')
    elif (url != RPC or payload.get('method') != 'eth_getBlockByNumber'
          or payload.get('params',[None,None])[1] is not False):
        raise ValueError('only read-only header RPC is permitted')
    record = {'url':url, 'request':payload, 'started_at_utc':now()}
    try:
        req = urllib.request.Request(url,None if payload is None else json.dumps(payload).encode(),
                                     {'Accept':'application/json','Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=20) as response:
            record.update(http_status=response.status,response=json.load(response))
    except urllib.error.HTTPError as error:
        record.update(http_status=error.code,body=error.read().decode())
    except (urllib.error.URLError,TimeoutError,ValueError) as error:
        record['transport_error'] = str(error)
    record['received_at_utc'] = now()
    save(path,record)
    if record.get('http_status') != 200 or record.get('response',{}).get('error'):
        raise RuntimeError('read unavailable; response retained, no retry')
    return record


def selection_check(selection):
    data(selection['market_id'],32); data(selection['borrower'],20)
    if integer(selection['chain_id']) != 1 or not 1 <= integer(selection['max_snapshots']) <= 3:
        raise ValueError('bounded Ethereum selection required')
    instant(selection['saved_at_utc'])


def collect(directory, selection_path):
    selection = json.loads(selection_path.read_text()); selection_check(selection)
    directory.mkdir(parents=True,exist_ok=True)
    existing = sorted(directory.glob('sample-*'))
    if len(existing) >= selection['max_snapshots']: raise ValueError('session limit reached')
    if any(not (p/'report.json').exists() for p in existing):
        raise ValueError('previous sample incomplete; no automatic retry')
    sample = directory/f'sample-{len(existing):02}'; sample.mkdir()
    save(sample/'selection.json',selection)
    mid,borrower = selection['market_id'],selection['borrower']
    base = API+'/v0/blue/markets/1:'+mid
    config = request(sample/'config.json',base)['response']['data']
    data(config['oracle_address'],20)
    state = request(sample/'market.json',base+'/state')['response']['data']
    position = request(sample/'position.json',base+'/users/'+borrower+'/position')['response']['data']
    oracle = request(sample/'oracle.json',API+'/v0/oracles/1:'+config['oracle_address']+'/state')['response']['data']
    for height in sorted({integer(r['last_indexed_block']) for r in (state,position,oracle)}):
        request(sample/f'header-{height}.json',RPC,
                {'jsonrpc':'2.0','id':1,'method':'eth_getBlockByNumber','params':[hex(height),False]})
    result = analyze(sample); save(sample/'report.json',result)
    return result


def envelope(path):
    r = json.loads(path.read_text())
    if r.get('http_status') != 200 or r.get('response',{}).get('error'):
        raise ValueError('unavailable observation')
    if instant(r['received_at_utc']) < instant(r['started_at_utc']):
        raise ValueError('negative request interval')
    return r


def analyze(sample):
    selection = json.loads((sample/'selection.json').read_text()); selection_check(selection)
    mid,borrower = selection['market_id'],selection['borrower']
    records = {k:envelope(sample/(k+'.json')) for k in ('config','market','position','oracle')}
    config,market,position,oracle = (records[k]['response']['data'] for k in records)
    params = {'loan_token':config['loan_token'],'collateral_token':config['collateral_token'],
              'oracle':config['oracle_address'],'irm':config['irm_address'],'lltv':integer(config['lltv_wad'])}
    if market_id(params) != mid: raise ValueError('market parameters do not hash to selection')
    for row in (config,market,position):
        if integer(row['chain_id']) != 1 or row['market_id'].lower() != mid:
            raise ValueError('wrong observed market')
    if position['user_address'].lower() != borrower: raise ValueError('wrong observed position')
    if integer(oracle['chain_id']) != 1 or oracle['oracle_address'].lower() != params['oracle'].lower():
        raise ValueError('wrong oracle')
    base = API+'/v0/blue/markets/1:'+mid
    urls = {'config':base,'market':base+'/state','position':base+'/users/'+borrower+'/position',
            'oracle':API+'/v0/oracles/1:'+config['oracle_address']+'/state'}
    for key,r in records.items():
        if r['url'] != urls[key] or r['request'] is not None: raise ValueError('request identity mismatch')
        if instant(r['started_at_utc']) < instant(selection['saved_at_utc']):
            raise ValueError('selection must precede observation')
    observations = {}
    received_times = [r['received_at_utc'] for r in records.values()]
    for key,row in (('market',market),('position',position),('oracle',oracle)):
        height = integer(row['last_indexed_block']); h = envelope(sample/f'header-{height}.json')
        if h['url'] != RPC or h['request'] != {'jsonrpc':'2.0','id':1,'method':'eth_getBlockByNumber','params':[hex(height),False]}:
            raise ValueError('header request differs from reported height')
        block = h['response']['result']
        if block is None or quantity(block['number']) != height: raise ValueError('missing/mismatched header')
        verify_header(block,block['hash'])
        received_times.append(h['received_at_utc'])
        timestamp = quantity(block['timestamp']); received = instant(records[key]['received_at_utc'])
        delay = received-datetime.fromtimestamp(timestamp,timezone.utc)
        delay_us = (delay.days*86400+delay.seconds)*10**6+delay.microseconds
        if delay_us < 0: raise ValueError('state block lies after local receipt')
        observations[key] = {'indexed_block':height,'header_hash':block['hash'],'state_root':block['stateRoot'],
                             'block_timestamp':timestamp,'received_at_utc':records[key]['received_at_utc'],
                             'block_to_receipt_microseconds':delay_us}
    totals = {k:integer(market[k]) for k in ('total_supply_assets','total_supply_shares',
              'total_borrow_assets','total_borrow_shares','fee_wad','last_accrual_timestamp')}
    balances = {k:integer(position[k]) for k in ('collateral_assets','supply_shares','borrow_shares')}
    coherent = len({r['indexed_block'] for r in observations.values()}) == 1
    blockers = ['REST_STATE_NOT_PROVED_AGAINST_HEADER_ROOT','ASSET_TOTALS_ACCRUAL_SEMANTICS_UNVERIFIED',
                'IRM_RATE_AT_OBSERVATION_UNAVAILABLE','FLUID_STATE_AND_EXECUTABLE_QUOTE_UNAVAILABLE',
                'SPONSOR_AND_CAPTURE_UNPROVED']
    if not coherent: blockers.append('MIXED_INDEXED_BLOCKS')
    return {'status':'INDEXER_OBSERVATION_ONLY','market_id':mid,'borrower':borrower,
            'complete_data_received_at_utc':max(received_times,key=instant),
            'observations':observations,'same_reported_block':coherent,'market':totals,'position':balances,
            'oracle_price':integer(oracle['price']),'oracle_last_updated_at':oracle.get('last_updated_at'),
            'book_market_cash_difference':totals['total_supply_assets']-totals['total_borrow_assets'],
            'morpho_aggregate_flash_cash':None,'interest_accrued_to_observation':None,
            'liquidation_eligible':None,'net_profit':None,'blockers':blockers,
            'pretransaction_witness':False,'certified':False}


def temporal_order(sample_report,event_timestamp,event_block):
    """Necessary ordering only; neither opportunity visibility nor capture proof."""
    if not sample_report['observations']: raise ValueError('empty observations')
    event_dt = datetime.fromtimestamp(integer(event_timestamp),timezone.utc)
    return (instant(sample_report['complete_data_received_at_utc']) < event_dt
            and all(r['indexed_block'] < integer(event_block) and instant(r['received_at_utc']) < event_dt
                    for r in sample_report['observations'].values()))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--collect',type=Path); p.add_argument('--selection',type=Path); p.add_argument('--analyze',type=Path)
    args = p.parse_args()
    if args.collect and args.selection and not args.analyze: result = collect(args.collect,args.selection)
    elif args.analyze and not args.collect and not args.selection: result = analyze(args.analyze)
    else: p.error('use --collect DIRECTORY --selection FILE, or --analyze SAMPLE')
    print(json.dumps(result,indent=2))
    raise SystemExit(2)
