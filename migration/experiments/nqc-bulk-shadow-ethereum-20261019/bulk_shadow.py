"""NQC mass-market Morpho Blue Shadow: documented query; source-aware offline rollup.

The existing NQC055 kernel is the economic authority and NQC067 is the optional
pinned deeper snapshot parser. This module DOES NOT sign, quote, execute, predict
profit, or infer canonical state. A future network-enabled execution must be
explicitly approved; none occurs from module import or normal offline mode.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CHAIN_ID = 1
GRAPHQL_ENDPOINT = 'https://api.morpho.org/graphql'
MARKETS_ENDPOINT = 'https://api.morpho.org/v1/blue/markets'
PAGE_LIMIT = 1000
MARKET_PAGE_LIMIT = 1000
MAX_PAGES = 10
MAX_BODY_BYTES = 1_000_000
HF_CUTOFF = 1.02  # INDEXER screening only: NEVER onchain eligibility.
MARKET_ID = re.compile(r'0x[0-9a-fA-F]{64}\Z')
ADDRESS = re.compile(r'0x[0-9a-fA-F]{40}\Z')
DIGITS = re.compile(r'(?:0|[1-9][0-9]*)\Z')
NQC067_BLOB = 'dfb67d4783fa29a92d4da013d51d48ee80b7cc8e'

# Exact query design is transcribed from the PINNED official Morpho Blue
# liquidator's borrowers.ts. That upstream bot supports Base/Robinhood; this
# query is a chain-1 SCREEN ONLY and never inherits an executor certification.
AT_RISK_QUERY = '''query NQCMassShadow($chainIds: [Int!], $hfLte: Float!, $first: Int!, $skip: Int!) {
  marketPositions(
    where: { chainId_in: $chainIds, healthFactor_lte: $hfLte, marketListed: true }
    orderBy: HealthFactor
    orderDirection: Asc
    first: $first
    skip: $skip
  ) {
    pageInfo { count countTotal }
    items { market { marketId } user { address } }
  }
}'''


class EvidenceError(ValueError):
    pass


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(obj: object) -> bytes:
    return (json.dumps(obj, ensure_ascii=True, separators=(',', ':'), sort_keys=True) + '\n').encode('utf-8')


def from_json(raw: bytes):
    def no_duplicates(pairs):
        obj = {}
        for k, v in pairs:
            if k in obj:
                raise EvidenceError('duplicate JSON key: ' + k)
            obj[k] = v
        return obj
    try:
        return json.loads(raw, object_pairs_hook=no_duplicates,
                          parse_constant=lambda x: (_ for _ in ()).throw(EvidenceError(x)))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise EvidenceError('invalid UTF8 JSON') from e


def is_uint(x):
    return type(x) is int and x >= 0


def query_request(skip: int) -> dict:
    if not is_uint(skip) or skip % PAGE_LIMIT:
        raise EvidenceError('skip must be a nonnegative page multiple')
    return {'query': AT_RISK_QUERY, 'variables': {
        'chainIds': [CHAIN_ID], 'hfLte': HF_CUTOFF, 'first': PAGE_LIMIT, 'skip': skip}}


def parse_position_page(body: bytes, skip: int) -> dict:
    if len(body) > MAX_BODY_BYTES:
        raise EvidenceError('position page exceeds byte cap')
    query_request(skip)
    data = from_json(body)
    if not isinstance(data, dict) or data.get('errors'):
        raise EvidenceError('GraphQL errors, no partial success permitted')
    top = data.get('data')
    section = top.get('marketPositions') if isinstance(top, dict) else None
    if not isinstance(section, dict):
        raise EvidenceError('marketPositions missing')
    rows = section.get('items')
    if not isinstance(rows, list) or len(rows) > PAGE_LIMIT:
        raise EvidenceError('bad/oversized positions page')
    info = section.get('pageInfo')
    if not isinstance(info, dict):
        raise EvidenceError('missing pageInfo')
    count, total = info.get('count'), info.get('countTotal')
    if not is_uint(count) or count != len(rows):
        raise EvidenceError('pageInfo.count disagrees with items')
    if total is not None and not is_uint(total):
        raise EvidenceError('countTotal invalid')
    if total is not None and skip + count > total:
        raise EvidenceError('position page exceeds server countTotal')
    seen = set()
    pairs = []
    for entry in rows:
        if not isinstance(entry, dict):
            raise EvidenceError('malformed candidate row')
        market = entry.get('market')
        user = entry.get('user')
        m = market.get('marketId') if isinstance(market, dict) else None
        u = user.get('address') if isinstance(user, dict) else None
        if not isinstance(m, str) or not MARKET_ID.fullmatch(m) or not isinstance(u, str) or not ADDRESS.fullmatch(u):
            raise EvidenceError('bad market/borrower identity; cannot silently drop')
        key = (m.lower(), u.lower())
        if key in seen:
            raise EvidenceError('duplicate borrower in same page')
        seen.add(key)
        pairs.append({'market_id':key[0],'borrower':key[1],
                      'profit':None, 'eligible_onchain':None,
                      'indexer_health_factor_at_most':HF_CUTOFF})
    return {'skip':skip, 'count':count, 'count_total':total, 'pairs':pairs,
            'raw_sha256':sha256(body), 'raw_bytes':len(body)}


def parse_market_page(body: bytes, cursor: str | None) -> dict:
    if len(body) > MAX_BODY_BYTES:
        raise EvidenceError('market page exceeds byte cap')
    if cursor is not None and (not isinstance(cursor,str) or not 1 <= len(cursor) <= 4096):
        raise EvidenceError('invalid input cursor')
    data = from_json(body)
    if not isinstance(data, dict):
        raise EvidenceError('markets response not object')
    if 'cursor' not in data or not isinstance(data.get('data'), list):
        raise EvidenceError('must have {cursor,data} REST envelope')
    next_cursor = data['cursor']
    if next_cursor is not None and (not isinstance(next_cursor,str) or not 1 <= len(next_cursor) <= 4096):
        raise EvidenceError('invalid output cursor')
    rows = data['data']
    if len(rows) > MARKET_PAGE_LIMIT:
        raise EvidenceError('market page over selected limit')
    seen = set()
    out = []
    for x in rows:
        if not isinstance(x, dict):
            raise EvidenceError('bad market entry')
        mid = x.get('market_id')
        if type(x.get('chain_id')) is not int or x['chain_id'] != CHAIN_ID:
            raise EvidenceError('non-Ethereum market from chain filter')
        if not isinstance(mid,str) or not MARKET_ID.fullmatch(mid):
            raise EvidenceError('invalid market id')
        m=mid.lower()
        if m in seen:
            raise EvidenceError('duplicate market within page')
        seen.add(m)
        params = {}
        for k in ('loan_token','collateral_token','oracle_address','irm_address'):
            val = x.get(k)
            if not isinstance(val,str) or not ADDRESS.fullmatch(val):
                raise EvidenceError('missing/bad market parameter ' + k)
            params[k]=val.lower()
        lltv=x.get('lltv_wad')
        if not isinstance(lltv,str) or not DIGITS.fullmatch(lltv) or int(lltv)>10**18:
            raise EvidenceError('LLTV out of range')
        out.append({'chain_id':1,'market_id':m,'params':params,'lltv_wad':lltv})
    if next_cursor is not None and not rows:
        raise EvidenceError('no progress with remaining REST cursor')
    return {'input_cursor':cursor,'next_cursor':next_cursor,'markets':out,
            'count':len(out),'raw_sha256':sha256(body),'raw_bytes':len(body)}


def aggregate_positions(pages: list[tuple[int,bytes]], *, max_pages: int=MAX_PAGES) -> dict:
    if not pages:
        return {'source':'NOT_ACQUIRED','observed_page_count':0,'indexed_candidates':None,
                'distinct_markets_with_candidates':None,'coverage_complete':False,
                'commercial_admission':False,'NQC_realized_profit':None}
    if not 1<=max_pages<=MAX_PAGES or len(pages)>max_pages:
        raise EvidenceError('page cap invalid/exceeded')
    seen, markets, ledger = set(),defaultdict(int),[]
    expected_skip=0
    totals=[]
    duplicates=0
    stopped=False
    for ix,(skip,body) in enumerate(pages):
        if stopped or skip!=expected_skip:
            raise EvidenceError('unexpected page offset or pages after terminal')
        p=parse_position_page(body,skip)
        if ix>0 and p['count']==0 and (p['count_total'] is None or p['count_total']>skip):
            raise EvidenceError('zero progress before announced total')
        expected_skip+=p['count']
        if p['count_total'] is not None:
            totals.append(p['count_total'])
        for q in p['pairs']:
            key=(q['market_id'],q['borrower'])
            if key in seen:
                duplicates+=1
                continue
            seen.add(key)
            markets[q['market_id']]+=1
        ledger.append({k:p[k] for k in ('skip','count','count_total','raw_sha256','raw_bytes')})
        stopped=p['count']<PAGE_LIMIT or (p['count_total'] is not None and expected_skip>=p['count_total'])
    totals_consistent=not totals or len(set(totals))==1
    # If countTotal is absent, count-based terminal page is our sole indexer signal.
    if totals and totals_consistent and stopped and expected_skip!=totals[0]:
        totals_consistent=False
    if duplicates:
        totals_consistent=False  # moving offset pagination can omit other rows
    cap_hit=not stopped
    # A source-window can move during pagination; API-complete != same-block canonical.
    return {'schema':'nqc_bulk_indexer_candidates_v1','source':'OFFLINE_GRAPHQL_SHAPED_INPUT_NOT_AUTHENTICATED',
        'chain_id':CHAIN_ID,'health_factor_filter_lte':HF_CUTOFF,
        'listed_markets_only':True,'observed_page_count':len(pages),
        'raw_position_rows':expected_skip,'indexed_candidates':len(seen),
        'distinct_markets_with_candidates':len(markets),
        'per_market_candidate_counts':dict(sorted(markets.items())),
        'duplicate_pairs_across_pages':duplicates,
        'total_count_reported':totals[0] if totals and totals_consistent else None,
        'truncated_by_cap':cap_hit,
        'pagination_consistent':totals_consistent,
        'indexer_filtered_scan_reached_end':bool(stopped and totals_consistent),
        'coverage_complete':False,
        'onchain_eligibility_verified':False,
        'sale_quoted':False,'gas_and_inclusion_verified':False,
        'financier_committed':False,'NQC_realized_profit':None,
        'commercial_admission':False,'pages':ledger,
        'warning':'Only listed Ethereum markets indexer-matching HF<=1.02. No real-time chain proof or viable P&L.'}


def aggregate_markets(pages: list[tuple[str | None, bytes]], *, max_pages: int=MAX_PAGES) -> dict:
    if not pages:
        return {'source':'NOT_ACQUIRED','market_count':None,
                'indexer_pagination_exhausted':False,'canonical_universe_complete':False}
    if not 1<=max_pages<=MAX_PAGES or len(pages)>max_pages:
        raise EvidenceError('REST page cap')
    seen,set_cursors=set(),set()
    expected=None
    ledger=[]
    stopped=False
    for index,(cursor,body) in enumerate(pages):
        if stopped or cursor!=expected:
            raise EvidenceError('out of order / extra REST page')
        p=parse_market_page(body,cursor)
        if p['next_cursor'] and p['next_cursor'] in set_cursors:
            raise EvidenceError('cursor cycle')
        for row in p['markets']:
            if row['market_id'] in seen:
                raise EvidenceError('duplicate market across REST pages')
            seen.add(row['market_id'])
        if p['next_cursor']:
            set_cursors.add(p['next_cursor'])
        expected=p['next_cursor']
        stopped=expected is None
        ledger.append({k:p[k] for k in ('input_cursor','next_cursor','count','raw_sha256','raw_bytes')})
    return {'schema':'nqc_bulk_indexer_market_directory_v1','source':'OFFLINE_REST_SHAPED_INPUT_NOT_AUTHENTICATED',
        'chain_id':CHAIN_ID,'market_count':len(seen),'market_ids':sorted(seen),
        'indexer_pagination_exhausted':stopped,'truncated_by_cap':not stopped,
        'canonical_universe_complete':False,'pages':ledger}


def reference_scope(summary: dict) -> dict:
    # Reuse pinned OUTPUT of NQC055, do not rerun its original source import.
    if summary.get('schema')!='nqc055-radar-v1':
        raise EvidenceError('unrecognized NQC055 reference summary')
    ev=summary['evaluation']
    if ev['dossiers']!=142 or sum(ev['status_counts'].values())!=142:
        raise EvidenceError('unexpected archival scope')
    return {'source':'ARCHIVED_NQC055_NOT_CURRENT',
            'historical_dossiers':142,
            'historical_distinct_markets':summary['shared_market_groups'],
            'historical_asset_pairs':summary['shared_asset_pair_groups'],
            'economically_rankable':ev['economically_rankable_alternatives'],
            'not_evaluable':ev['status_counts']['NO_PUEDE_EVALUARSE_CON_DATOS_ACTUALES'],
            'require_evidence':ev['status_counts']['REQUIERE_EVIDENCIA_ESPECIFICA'],
            'NQC_realized_profit':None}


def import_nqc067_pinned_parser(path:Path|None=None):
    if path is None:
        path=Path(__file__).resolve().parents[1]/'nqc-067-shadow-blue-public-indexer'/'shadow.py'
    raw=path.read_bytes()
    actual=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\x00'+raw).hexdigest()
    if actual!=NQC067_BLOB:
        raise EvidenceError('NQC067 source blob mismatch, no compatibility bypass')
    spec=importlib.util.spec_from_file_location('pinned_nqc067_shadow',path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def refine_with_pinned_nqc067(body:bytes, selected_market_ids:list[str], observed_at_utc:str,
                              *, candidate_market_ids:set[str]|None=None) -> dict:
    """Reuse NQC067 normalization only on selected markets with richer input.

    A market ID from the fast bulk screen is NOT yet an onchain-eligible position.
    A full GraphQL snapshot for <=3 candidates must be supplied independently.
    """
    if not 1 <= len(selected_market_ids) <= 3:
        raise EvidenceError('NQC067 deeper review accepts 1-3 markets only')
    if any(not isinstance(m,str) or not MARKET_ID.fullmatch(m) for m in selected_market_ids):
        raise EvidenceError('invalid selected market')
    if candidate_market_ids is not None and any(m.lower() not in candidate_market_ids for m in selected_market_ids):
        raise EvidenceError('deep review market absent from discovered set')
    parser=import_nqc067_pinned_parser()
    result=parser.normalize(from_json(body),selected_market_ids,observed_at_utc,sha256(body))
    if result['commercial_admission'] or result['actual_NQC_profit'] is not None:
        raise EvidenceError('NQC067 source changed economic boundary')
    return result


def save_new(path:Path, data:bytes):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'wb') as f:
        f.write(data)
        f.flush();os.fsync(f.fileno())


def offline_evaluate(positions_dir:Path|None, markets_dir:Path|None,
                     archive_summary:Path|None) -> dict:
    pp=[]
    if positions_dir is not None:
        for path in sorted(positions_dir.glob('positions_skip_*.raw.json')):
            mat=re.fullmatch(r'positions_skip_([0-9]{6})\.raw\.json',path.name)
            if not mat:
                raise EvidenceError('invalid position archive filename')
            pp.append((int(mat.group(1)),path.read_bytes()))
    mm=[]
    if markets_dir is not None:
        manifest=from_json((markets_dir/'manifest.json').read_bytes())
        refs=manifest.get('ordered_pages')
        if not isinstance(refs,list):
            raise EvidenceError('market archive manifest missing ordered_pages')
        for row in refs:
            if not isinstance(row,dict) or set(row)!={'file','input_cursor'}:
                raise EvidenceError('market manifest row invalid')
            name=row['file']
            if not isinstance(name,str) or not re.fullmatch(r'markets_[0-9]{6}\.raw\.json',name):
                raise EvidenceError('market manifest filename invalid')
            mm.append((row['input_cursor'],(markets_dir/name).read_bytes()))
    prior=reference_scope(from_json(archive_summary.read_bytes())) if archive_summary else None
    positions=aggregate_positions(pp)
    markets=aggregate_markets(mm)
    if positions.get('indexed_candidates') is not None and markets.get('market_count') is not None:
        if any(mid not in markets['market_ids'] for mid in positions['per_market_candidate_counts']):
            raise EvidenceError('candidate market not in enumerated market list')
    return {'schema':'nqc_bulk_commercial_shadow_v1','kind':'OFFLINE_ROLLUP',
       'legacy':prior,'markets':markets,'risk_screen':positions,
       'market_count_from_input':markets.get('market_count'),
       'risk_candidate_count_from_input':positions.get('indexed_candidates'),
       'authenticated_live_market_count':None,
       'authenticated_live_candidate_count':None,
       'capture_frequency':None,'economic_net_USD':None,
       'route_executable_count':None,'sponsor_nonrecourse_accepted':False,
       'NQC_actual_profit':None,'commercial_admission':False,
       'coverage_complete':False,
       'warning':'Only source files actually provided are processed. Missing pages or DNS do not imply zero activity.'}


def api_fetch(request:Request) -> bytes:
    try:
        with urlopen(request,timeout=8) as response:
            if response.status!=200:
                raise EvidenceError('public provider HTTP status !=200; no retry')
            b=response.read(MAX_BODY_BYTES+1)
            if len(b)>MAX_BODY_BYTES:
                raise EvidenceError('provider response too large')
            return b
    except HTTPError as e:
        raise EvidenceError(f'HTTP {e.code}: stop and manual review, no retry') from e
    except (URLError,TimeoutError,OSError) as e:
        raise EvidenceError('public provider inaccessible: no retry') from e


def fetch_candidate_pages_bounded(out:Path, *, approval:bool=False, max_pages:int=MAX_PAGES) -> dict:
    """Finite READ-only GraphQL session. Never call automatically or after source failure.

    Unlike a `while True` bot, all operations are bounded and their request body
    known. The output directory is one-shot and exclusive, no resumption after
    ambiguous network response and no fallback to an alternative provider.
    """
    if not approval:
        raise EvidenceError('explicit public-read approval required')
    if not 1<=max_pages<=MAX_PAGES:
        raise EvidenceError('max pages invalid')
    if out.exists():
        raise EvidenceError('one-shot evidence directory already exists; no auto-retry')
    out.mkdir(parents=True,exist_ok=False)
    save_new(out/'ATTEMPTED.lock',b'one attempt only\n')
    pages=[]
    try:
        for page in range(max_pages):
            skip=page*PAGE_LIMIT
            req=Request(GRAPHQL_ENDPOINT,data=canonical(query_request(skip)),method='POST',
                headers={'Content-Type':'application/json','Accept':'application/json',
                         'User-Agent':'NQC-MassShadow-ReadOnly/0.1'})
            body=api_fetch(req)
            p=parse_position_page(body,skip)
            save_new(out/f'positions_skip_{skip:06d}.raw.json',body)
            pages.append((skip,body))
            if p['count']<PAGE_LIMIT or (p['count_total'] is not None and skip+p['count']>=p['count_total']):
                break
        result=aggregate_positions(pages,max_pages=max_pages)
        save_new(out/'RISK_SCREEN.json',canonical(result))
        return result
    except Exception as exc:
        save_new(out/'MANUAL_REVIEW_REQUIRED',str(exc).encode())
        raise


def fetch_market_directory_bounded(out:Path, *, approval:bool=False, max_pages:int=MAX_PAGES) -> dict:
    """Finite REST market enumeration, one-shot, cannot silently skip cursor pages."""
    if not approval:
        raise EvidenceError('explicit public-read approval required')
    if not 1<=max_pages<=MAX_PAGES:
        raise EvidenceError('invalid market page cap')
    if out.exists():
        raise EvidenceError('market evidence directory exists; no retries or overwrite')
    out.mkdir(parents=True,exist_ok=False)
    save_new(out/'ATTEMPTED.lock',b'one attempt only\n')
    pages=[]
    manifest=[]
    cursor=None
    try:
        for index in range(max_pages):
            query={'chain_id':1,'limit':MARKET_PAGE_LIMIT}
            if cursor is not None:
                query['cursor']=cursor
            url=MARKETS_ENDPOINT+'?'+urlencode(query)
            request=Request(url,headers={'Accept':'application/json',
                           'User-Agent':'NQC-MassShadow-ReadOnly/0.1'})
            body=api_fetch(request)
            parsed=parse_market_page(body,cursor)
            file=f'markets_{index:06d}.raw.json'
            save_new(out/file,body)
            pages.append((cursor,body))
            manifest.append({'file':file,'input_cursor':cursor})
            cursor=parsed['next_cursor']
            if cursor is None:
                break
        save_new(out/'manifest.json',canonical({'schema':'nqc_bulk_market_pages_v1',
            'origin':MARKETS_ENDPOINT,'query_filter':{'chain_id':1},'ordered_pages':manifest}))
        result=aggregate_markets(pages,max_pages=max_pages)
        save_new(out/'MARKETS_RESULT.json',canonical(result))
        return result
    except Exception as exc:
        save_new(out/'MANUAL_REVIEW_REQUIRED',str(exc).encode())
        raise


def main(argv:list[str]|None=None) -> int:
    pa=argparse.ArgumentParser(description='NQC cross-market bounded Shadow; no trading')
    mode=pa.add_mutually_exclusive_group(required=True)
    mode.add_argument('--print-query',action='store_true')
    mode.add_argument('--offline-rollup',action='store_true')
    mode.add_argument('--fetch-public-bounded',action='store_true')
    mode.add_argument('--fetch-market-directory',action='store_true')
    pa.add_argument('--positions-pages',type=Path)
    pa.add_argument('--markets-pages',type=Path)
    pa.add_argument('--nqc055-summary',type=Path)
    pa.add_argument('--out',type=Path,default=Path('batch_shadow_output'))
    pa.add_argument('--explicit-public-read-approval',action='store_true')
    pa.add_argument('--max-pages',type=int,default=MAX_PAGES)
    args=pa.parse_args(argv)
    try:
        if args.print_query:
            print(json.dumps(query_request(0),indent=2));return 0
        if args.offline_rollup:
            result=offline_evaluate(args.positions_pages,args.markets_pages,args.nqc055_summary)
            save_new(args.out/'BATCH_REPORT.json',canonical(result))
            print(json.dumps(result,indent=2));return 0
        if args.fetch_market_directory:
            result=fetch_market_directory_bounded(args.out,approval=args.explicit_public_read_approval,max_pages=args.max_pages)
            print(json.dumps({'markets_enumerated':result['market_count'],
                 'market_directory_exhausted':result['indexer_pagination_exhausted'],
                 'commercial_admission':False}));return 0
        result=fetch_candidate_pages_bounded(args.out,approval=args.explicit_public_read_approval,max_pages=args.max_pages)
        print(json.dumps({'real_indexer_pages':result['observed_page_count'],
                          'indexed_candidates':result['indexed_candidates'],
                          'commercial_admission':False}));return 0
    except (EvidenceError,OSError,KeyError,TypeError) as e:
        print('NQC BATCH CLOSED: '+str(e),file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())
