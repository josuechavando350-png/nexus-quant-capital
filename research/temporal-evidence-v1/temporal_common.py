"""Strict evidence IO and types shared by two independent replay traversals.

This is local prepared-witness validation, not chain acquisition or terminal
certification. No status string in a source can grant production authority.
"""
from __future__ import annotations
import hashlib, json, re, stat
from pathlib import Path

CLASSES = ('POSITION_MUTATIONS','PROTOCOL_CONFIG_MUTATIONS','ORACLE_PRICE_TRANSITIONS',
           'RATE_INDEX_SEGMENTS','INTEREST_ONLY_CROSSING_CANDIDATES',
           'LIQUIDATION_OUTCOMES','CANONICAL_CHAIN_REORG_AUTHORITY')
ACQUIRED = tuple(c for c in CLASSES if c != 'INTEREST_ONLY_CROSSING_CANDIDATES')
PHASES = {'PRE_TX':0,'LOG':1,'POST_TX':2,'END_BLOCK':3}
TERMINALS = {'CAPTURED','EXPIRED','RECOVERED','REORG_INVALIDATED'}
HEX = re.compile(r'^[0-9a-f]{64}$')
SCHEMA = 'nqc-temporal-source-bundle-v1'

class Invalid(ValueError): pass

def need(c, m):
    if not c: raise Invalid(m)

def integer(x, name, minimum=0):
    need(type(x) is int and x >= minimum, f'{name}: integer >= {minimum} required')
    return x

def boolean(x, name):
    need(type(x) is bool, f'{name}: boolean required')
    return x

def hash32(x, name='hash'):
    need(isinstance(x,str) and HEX.fullmatch(x) and x != '0'*64, f'{name}: nonzero lowercase SHA-256 required')
    return x

def sha(raw): return hashlib.sha256(raw).hexdigest()
def canonical(obj): return (json.dumps(obj,sort_keys=True,separators=(',',':'))+'\n').encode()
def digest(obj): return sha(canonical(obj))

def pairs(items):
    out={}
    for k,v in items:
        need(k not in out, f'duplicate JSON key: {k}')
        out[k]=v
    return out

def decode(raw):
    try: return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda x: (_ for _ in ()).throw(Invalid('nonfinite JSON')))
    except (UnicodeDecodeError,json.JSONDecodeError) as exc: raise Invalid(f'invalid JSON: {exc}') from exc

def exact(obj, required, optional=(), label='object'):
    need(type(obj) is dict, f'{label}: object required')
    missing=set(required)-set(obj); extra=set(obj)-set(required)-set(optional)
    need(not missing and not extra, f'{label}: missing={sorted(missing)} unknown={sorted(extra)}')

def text(x, name):
    need(isinstance(x,str) and bool(x.strip()), f'{name}: nonempty string required')
    return x

def unique(xs,name):
    need(isinstance(xs,list),f'{name}: array required')
    need(all(isinstance(x,str) and x for x in xs),f'{name}: nonempty string entries required')
    need(len(xs)==len(set(xs)),f'{name}: duplicates')
    return xs

def point(p):
    exact(p,('block','phase','transaction_index','log_index'),label='order')
    b=integer(p['block'],'block'); phase=p['phase']; need(phase in PHASES,'bad phase')
    if phase=='END_BLOCK':
        need(p['transaction_index'] is None and p['log_index'] is None,'END_BLOCK indices forbidden')
        return (b,2**63-1,3,2**63-1)
    t=integer(p['transaction_index'],'transaction_index')
    need(t<2**63-1,'transaction index exceeds END_BLOCK ordering domain')
    if phase=='LOG': l=integer(p['log_index'],'log_index')
    else:
        need(p['log_index'] is None,'non-LOG log_index forbidden'); l=-1
    need(l<2**63-1,'log index exceeds ordering domain')
    return (b,t,PHASES[phase],l)

def relative_path(relative):
    text(relative,'evidence path'); p=Path(relative)
    need(not p.is_absolute() and '..' not in p.parts and p.as_posix()==relative,'unsafe evidence path')
    need(p.parts and relative not in ('.',''),'empty evidence path')
    return p

def inventory_schema(inventory):
    need(isinstance(inventory,list),'evidence inventory required'); hashes=set(); paths=set()
    for e in inventory:
        exact(e,('path','sha256','bytes'),label='evidence entry')
        relative_path(e['path']); h=hash32(e['sha256']); integer(e['bytes'],'evidence bytes',1)
        need(h not in hashes and e['path'] not in paths,'duplicate evidence digest/path')
        hashes.add(h); paths.add(e['path'])

def safe_file(root, relative):
    p=relative_path(relative)
    root=root.resolve(); cur=root
    for part in p.parts:
        cur=cur/part
        need(not cur.is_symlink(),'evidence symlink forbidden')
    need(cur.is_file() and stat.S_ISREG(cur.stat().st_mode),'evidence file missing or nonregular: '+relative)
    need(cur.resolve().is_relative_to(root),'evidence escaped root')
    need(cur.stat().st_size <= 16*1024*1024,'individual evidence file exceeds local admission limit')
    return cur

class Store:
    def __init__(self, root, inventory):
        self.root=Path(root); self.raw={}; self.docs={}; self.paths={}
        inventory_schema(inventory)
        for e in inventory:
            exact(e,('path','sha256','bytes'),label='evidence entry')
            h=hash32(e['sha256']); n=integer(e['bytes'],'evidence bytes',1)
            need(h not in self.raw,'duplicate evidence digest')
            need(e['path'] not in self.paths.values(),'duplicate evidence path')
            raw=safe_file(self.root,e['path']).read_bytes()
            need(len(raw)==n and sha(raw)==h,'evidence byte/hash mismatch: '+e['path'])
            self.raw[h]=raw; self.docs[h]=decode(raw); self.paths[h]=e['path']
    def get(self,h,kind=None):
        hash32(h,'evidence reference'); need(h in self.docs,'missing evidence bytes: '+h)
        d=self.docs[h]; need(type(d) is dict,'evidence object required')
        if kind: need(d.get('kind')==kind,'wrong evidence kind: '+str(kind))
        return d

def envelope(doc):
    exact(doc,('schema','evidence_kind','scope','window','evidence','coverage_refs',
               'trigger_refs','state_refs','dispositions'),label='bundle')
    need(doc['schema']==SCHEMA,'unsupported bundle schema')
    need(doc['evidence_kind'] in ('SYNTHETIC_NON_EVIDENTIARY','REAL_PREPARED_WITNESSES'),'evidence kind')
    s=doc['scope']; exact(s,('scope_id','chain_id','market_ids','population_commitment'),label='scope')
    text(s['scope_id'],'scope_id'); integer(s['chain_id'],'chain_id',1)
    need(bool(unique(s['market_ids'],'market_ids')),'markets required')
    for x in s['market_ids']: text(x,'market_id')
    hash32(s['population_commitment'],'population commitment')
    w=doc['window']; exact(w,('start_block','end_block','start_hash','end_hash','start_order','end_order'),label='window')
    a=integer(w['start_block'],'start_block'); b=integer(w['end_block'],'end_block'); need(a<=b,'window reversed')
    hash32(w['start_hash'],'start_hash'); hash32(w['end_hash'],'end_hash')
    first,last=point(w['start_order']),point(w['end_order'])
    need(first[0]==a and last[0]==b and first<last,'exact temporal window order/boundary mismatch')
    inventory_schema(doc['evidence'])
    for k in ('coverage_refs','trigger_refs','state_refs'):
        for h in unique(doc[k],k): hash32(h,k)
    need(isinstance(doc['dispositions'],list),'dispositions array')
    return s,w

def trigger(store,h,scope,window):
    d=store.get(h,'TRIGGER_V1')
    exact(d,('kind','trigger_id','trigger_class','lineage_id','order','scope_id','source_ref'),label='trigger')
    text(d['trigger_id'],'trigger_id'); text(d['lineage_id'],'lineage_id')
    need(d['trigger_class'] in CLASSES,'unknown trigger class')
    need(d['scope_id']==scope['scope_id'],'trigger scope mismatch')
    q=point(d['order']); need(point(window['start_order'])<=q<=point(window['end_order']),'trigger outside exact window')
    derived=d['trigger_class']=='INTEREST_ONLY_CROSSING_CANDIDATES'
    source=store.get(d['source_ref'],'DERIVED_TRIGGER_SOURCE_V1' if derived else 'TRIGGER_SOURCE_V1')
    keys=('kind','scope_id','lineage_id','trigger_id','trigger_class','order','payload_ref')
    exact(source,keys+(('algorithm_ref','input_refs','equivalence_ref') if derived else ()),label='trigger source')
    need(all(source[k]==d[k] for k in ('scope_id','lineage_id','trigger_id','trigger_class','order')),'trigger source identity mismatch')
    store.get(source['payload_ref'])
    if derived:
        store.get(source['algorithm_ref']); store.get(source['equivalence_ref'])
        need(bool(unique(source['input_refs'],'derived causal inputs')),'derived cause lacks inputs')
        supplied=set()
        for ref in source['input_refs']:
            inp=store.get(ref,'CAUSAL_INPUT_WITNESS_V1')
            exact(inp,('kind','scope_id','trigger_class','order','source_ref'),label='causal input')
            need(inp['scope_id']==scope['scope_id'],'derived causal input scope mismatch')
            need(inp['trigger_class'] in ACQUIRED,'derived input must be an acquired state class')
            need(point(inp['order'])<=q,'derived causal input occurs after output')
            store.get(inp['source_ref']); supplied.add(inp['trigger_class'])
        need({'POSITION_MUTATIONS','PROTOCOL_CONFIG_MUTATIONS','ORACLE_PRICE_TRANSITIONS','RATE_INDEX_SEGMENTS'}<=supplied,
             'derived cause lacks position/config/oracle/rate inputs')
    no_future_evidence(store,d['source_ref'],d['order'])
    return d

def no_future_evidence(store,root,decision):
    """Reject known future order/block fields throughout a bound evidence graph.

    This checks typed/prepared evidence consistency, not arbitrary RPC semantics.
    A new raw response schema still requires a separately reviewed decoder.
    """
    limit=point(decision); seen=set()
    def visit(obj):
        if isinstance(obj,str) and obj in store.docs:
            if obj not in seen:
                seen.add(obj); visit(store.get(obj))
        elif isinstance(obj,list):
            for v in obj: visit(v)
        elif type(obj) is dict:
            for key,value in obj.items():
                if key in ('order','pre_state_order','max_evidence_order'):
                    need(point(value)<=limit,'underlying evidence uses future order')
                elif key in ('blockNumber','block_number'):
                    number=int(value,16) if isinstance(value,str) and value.startswith('0x') else value
                    need(integer(number,'source block')<=limit[0],'underlying evidence uses future block')
                visit(value)
            if obj.get('kind')=='HEADER_V1': need(obj['number']<=limit[0],'future header in economic evidence')
    visit(root)

def state_commitment(d):
    return digest({k:d[k] for k in ('scope_id','lineage_id','market_id','position_id','asset_pair','order','header_ref','state')})

def snapshot(store,h,scope,window):
    d=store.get(h,'STATE_SNAPSHOT_V1')
    exact(d,('kind','scope_id','lineage_id','market_id','position_id','asset_pair','order','header_ref',
             'state','trigger_ids','execution_ref','terminal','terminal_evidence_ref'),label='state snapshot')
    need(d['scope_id']==scope['scope_id'] and d['market_id'] in scope['market_ids'],'snapshot scope mismatch')
    for k in ('lineage_id','market_id','position_id'): text(d[k],k)
    need(type(d['asset_pair']) is list and len(d['asset_pair'])==2,'asset pair')
    for a in d['asset_pair']: text(a,'asset')
    q=point(d['order']); need(point(window['start_order'])<=q<=point(window['end_order']),'snapshot outside exact window')
    header=store.get(d['header_ref'],'HEADER_V1')
    exact(header,('kind','chain_id','number','hash','parent_hash','timestamp'),label='header')
    need(header['chain_id']==scope['chain_id'] and type(header['chain_id']) is int,'header chain mismatch')
    need(integer(header['number'],'header block')==q[0],'header number mismatch')
    hash32(header['hash']); hash32(header['parent_hash']); integer(header['timestamp'],'timestamp')
    if q[0]==window['start_block']: need(header['hash']==window['start_hash'],'start hash mismatch')
    if q[0]==window['end_block']: need(header['hash']==window['end_hash'],'end hash mismatch')
    st=d['state']; exact(st,('health_factor_wad','debt_units','protocol_action_enabled'),label='state')
    integer(st['health_factor_wad'],'health factor'); integer(st['debt_units'],'debt'); boolean(st['protocol_action_enabled'],'action enabled')
    unique(d['trigger_ids'],'snapshot triggers')
    for t in d['trigger_ids']: text(t,'trigger_id')
    if d['execution_ref'] is not None: execution(store,d['execution_ref'],d)
    need(d['terminal'] is None or d['terminal'] in TERMINALS,'terminal status invalid')
    if d['terminal'] is None: need(d['terminal_evidence_ref'] is None,'unexpected terminal evidence')
    else: store.get(d['terminal_evidence_ref'])
    return d,header['timestamp']

def actionable(d):
    s=d['state']; return s['debt_units']>0 and s['health_factor_wad']<10**18 and s['protocol_action_enabled']

def execution(store,h,state=None):
    e=store.get(h,'EXECUTION_ECONOMICS_V1')
    exact(e,('kind','prestate_commitment','pre_state_order','max_evidence_order','success_path_net_usd_wad',
             'costs_complete','cost_evidence_refs','execution_evidence_ref'),label='economics')
    hash32(e['prestate_commitment'],'prestate commitment')
    need(point(e['max_evidence_order'])<=point(e['pre_state_order']),'economics look-ahead')
    need(type(e['success_path_net_usd_wad']) is int,'integer net required')
    need(e['costs_complete'] is True,'incomplete economics')
    need(bool(unique(e['cost_evidence_refs'],'cost references')),'cost evidence required including zero costs')
    for h in e['cost_evidence_refs']: store.get(h)
    store.get(e['execution_evidence_ref'])
    for h in e['cost_evidence_refs']+[e['execution_evidence_ref']]: no_future_evidence(store,h,e['pre_state_order'])
    if state:
        need(e['prestate_commitment']==state_commitment(state),'economics state commitment mismatch')
        need(point(e['pre_state_order'])==point(state['order']),'economics must bind exact executable prestate')
        need(actionable(state),'execution attached to nonactionable state')
    return e

def population(doc, store):
    p=store.get(doc['scope']['population_commitment'],'POPULATION_V1')
    exact(p,('kind','scope_id','positions'),label='population')
    need(p['scope_id']==doc['scope']['scope_id'],'population scope mismatch')
    need(type(p['positions']) is list,'population positions array')
    rows={}
    for row in p['positions']:
        exact(row,('lineage_id','market_id','position_id','asset_pair'),label='population position')
        for k in ('lineage_id','market_id','position_id'): text(row[k],k)
        need(row['market_id'] in doc['scope']['market_ids'],'population market outside scope')
        need(type(row['asset_pair']) is list and len(row['asset_pair'])==2,'population asset pair')
        for a in row['asset_pair']: text(a,'population asset')
        need(row['lineage_id'] not in rows,'duplicate population lineage')
        rows[row['lineage_id']]=row
    if doc['evidence_kind']=='REAL_PREPARED_WITNESSES':
        need(not any(d.get('evidence_kind')=='SYNTHETIC_NON_EVIDENTIARY' for d in store.docs.values() if type(d) is dict),
             'synthetic evidence cannot be relabeled real')
    return rows

def rejection(store,row,triggers,scope,window,admitted_state_refs):
    exact(row,('trigger_id','category','reason','evidence_refs'),label='disposition')
    need(row['trigger_id'] in triggers,'disposition refers to unknown trigger')
    need(row['category'] in ('PROVEN_REJECTION','EVIDENCE_INSUFFICIENT','ACQUISITION_INCOMPLETE'),'unknown disposition category')
    text(row['reason'],'disposition reason'); unique(row['evidence_refs'],'disposition refs')
    for h in row['evidence_refs']: store.get(h)
    if row['category']!='PROVEN_REJECTION': return False
    # A free-text phrase never proves a negative. Only these local predicates
    # are supported; additional rejection semantics need an explicit adapter.
    need(len(row['evidence_refs'])==1,'one typed rejection witness required')
    p=store.get(row['evidence_refs'][0],'REJECTION_WITNESS_V1')
    exact(p,('kind','trigger_id','reason','witness_ref'),label='rejection proof')
    need(p['trigger_id']==row['trigger_id'] and p['reason']==row['reason'],'rejection binding mismatch')
    need(p['witness_ref'] in admitted_state_refs,'negative witness is not an admitted history state')
    state,_=snapshot(store,p['witness_ref'],scope,window)
    t=triggers[row['trigger_id']]
    need(state['lineage_id']==t['lineage_id'] and point(state['order'])==point(t['order']),
         'rejection must bind the same lineage and exact trigger order')
    if row['reason']=='NONPOSITIVE_SUCCESS_PATH_NET':
        need(state['execution_ref'] is not None,'nonpositive rejection requires exact execution economics')
        e=execution(store,state['execution_ref'],state); need(e['success_path_net_usd_wad']<=0,'positive economics cannot be rejected as nonpositive')
    elif row['reason'] in ('ZERO_DEBT','PROTOCOL_ACTION_DISABLED'):
        s=state['state']
        if row['reason']=='ZERO_DEBT': need(type(s['debt_units']) is int and s['debt_units']==0,'zero-debt predicate false')
        else: need(s['protocol_action_enabled'] is False,'disabled predicate false')
    else: raise Invalid('unsupported proven rejection; evidence-insufficient is not a negative: '+row['reason'])
    return True

def diagnose_existing(doc):
    """Read actual historical shapes without treating their flags as evidence."""
    if doc.get('schema')==SCHEMA: return None
    missing=[]; fmt='UNSUPPORTED_SOURCE'
    if doc.get('status','').startswith('BLOCKED_AWAITING_'):
        fmt='EXISTING_BLOCKED_STAGE_INPUT'
        missing.extend(doc.get('blocking_reasons',[]))
    elif 'candidate_account_count' in doc and 'episode_ledger_sha256' in doc:
        fmt='HISTORICAL_RMC015B_AGGREGATE'
        for k in ('episode_ledger_sha256','censored_ledger_sha256'):
            missing.append('MISSING_EXACT_RAW_BYTES '+k+'='+str(doc.get(k)))
        for k,v in doc.get('inputs',{}).items(): missing.append('MISSING_SOURCE_INPUT '+k+'='+str(v))
        missing += ['AGGREGATE_FLAGS_ARE_NOT_ROW_REPLAY','ALL_SEVEN_TRIGGER_SURFACES_NOT_SUPPLIED']
    elif 'authority' in doc and 'transaction_economics_sha256' in doc['authority']:
        fmt='HISTORICAL_RMC016_AGGREGATE'; a=doc['authority']
        missing += ['MISSING_EXACT_TRANSACTION_LEDGER '+a['transaction_economics_sha256'],
                    'MISSING_TEMPORAL_EPISODE_AND_DISPOSITION_ROWS','ZERO_LOWER_BOUND_DOES_NOT_PROVE_ECONOMIC_COMPLETENESS']
    elif 'trigger_universe' in doc and 'episodes' in doc:
        fmt='EXISTING_FOUNDATION_EPISODE_DOCUMENT'
        missing += ['MISSING_EVIDENCE_INVENTORY_AND_RAW_BYTES','MISSING_SCOPE_AND_WINDOW',
                    'MISSING_ALL_SEVEN_CLASS_COVERAGE','MISSING_IMMUTABLE_STATE_TRANSITIONS',
                    'FOUNDATION_EPISODES_CANNOT_PROVE_THEIR_OWN_PRESTATE']
    else: missing += ['UNSUPPORTED_SCHEMA_NO_ADMISSION_ADAPTER']
    return {'status':'BLOCKED_REAL_INPUT_INSUFFICIENT','source_format':fmt,'missing_requirements':missing,
            'terminal_authority':False,'real_market_census_closed':False}
