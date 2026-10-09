"""Independent adversarial synthetic probes. No network or chain authority."""
import copy, hashlib, json, os, sys, tempfile
from pathlib import Path

IMPL=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).parent/'baseline'
sys.path.insert(0,str(IMPL)); sys.dont_write_bytecode=True
from temporal_common import canonical, decode, sha, Invalid, state_commitment, Store
from synthetic_fixture import make
import build_temporal_package as builder
import verify_temporal_package as verifier

def remap_bundle(src, mutate):
    doc=decode(src.read_bytes())
    docs={e['sha256']:decode((src.parent/e['path']).read_bytes()) for e in doc['evidence']}
    mutate(doc,docs)
    done={}; newdocs={}
    def remap(obj):
        if isinstance(obj,str) and obj in docs:
            if obj not in done:
                replacement=remap(docs[obj]); h=sha(canonical(replacement)); done[obj]=h; newdocs[h]=replacement
            return done[obj]
        if isinstance(obj,list): return [remap(v) for v in obj]
        if isinstance(obj,dict): return {k:remap(v) for k,v in obj.items()}
        return obj
    for h in docs: remap(h)
    doc={k:remap(v) for k,v in doc.items() if k!='evidence'}
    doc['evidence']=[]
    for h,obj in sorted(newdocs.items()):
        raw=canonical(obj); (src.parent/h).write_bytes(raw)
        doc['evidence'].append({'path':h,'sha256':h,'bytes':len(raw)})
    src.write_bytes(canonical(doc)); return doc

def kind(docs,k): return [o for o in docs.values() if o.get('kind')==k]
def state_by_block(doc,docs,b): return next(docs[h] for h in doc['state_refs'] if docs[h]['order']['block']==b)
def rejection_state(doc,docs):
    row=doc['dispositions'][0]; proof=docs[row['evidence_refs'][0]]; return docs[proof['witness_ref']]

def detached_rejection(doc,docs):
    proof=docs[doc['dispositions'][0]['evidence_refs'][0]]
    k=sha(b'REVIEW_DETACHED_STATE_KEY')
    docs[k]=copy.deepcopy(docs[proof['witness_ref']]); proof['witness_ref']=k
    return docs[k]

def rejection_detached_position(d,ds): detached_rejection(d,ds)['position_id']='UNRELATED_POSITION'
def rejection_contradicts_history(d,ds):
    detached_rejection(d,ds)
    for h in d['state_refs']: ds[h]['state']['debt_units']=10
def rejection_healthy_tail_missing(d,ds):
    d['state_refs']=[h for h in d['state_refs'] if ds[h]['order']['block']!=103]

def reject_foreign_scope(d,ds): rejection_state(d,ds)['scope_id']='UNRELATED_SCOPE'
def reject_foreign_lineage(d,ds): rejection_state(d,ds)['lineage_id']='UNRELATED_LINEAGE'
def reject_foreign_position(d,ds): rejection_state(d,ds)['position_id']='UNRELATED_POSITION'
def reject_future_state(d,ds): rejection_state(d,ds)['order']['block']=1000000
def reject_null_header(d,ds): rejection_state(d,ds)['header_ref']=None
def reject_untyped_state(d,ds):
    proof=rejection_state(d,ds); proof.clear(); proof.update(kind='STATE_SNAPSHOT_V1',state={'debt_units':0})

def erase_population(d,ds):
    d['state_refs']=[]; d['trigger_refs']=[]
    for s in kind(ds,'COVERAGE_SEGMENT_V1'): s['trigger_refs']=[]
    for s in kind(ds,'SYNTHETIC_RANGE_RESPONSE'):
        if 'trigger_refs' in s: s['trigger_refs']=[]
def untriggered_observed_birth(d,ds):
    refs=list(d['state_refs']); erase_population(d,ds); d['state_refs']=refs
    for h in refs: ds[h]['trigger_ids']=[]
def erase_future_tail(d,ds):
    d['state_refs']=[h for h in d['state_refs'] if ds[h]['order']['block']!=103]
    state_by_block(d,ds,101)['state']['health_factor_wad']=11*10**17
    state_by_block(d,ds,101)['execution_ref']=None
def trigger_on_unrelated_source(d,ds):
    t=kind(ds,'TRIGGER_V1')[0]
    t['source_ref']=next(h for h,s in ds.items() if s.get('kind')=='SYNTHETIC_DETERMINISTIC_ALGORITHM')
def wrong_response_class(d,ds):
    for s in kind(ds,'SYNTHETIC_RANGE_RESPONSE'): s['class']='UNRELATED_CLASS'
def response_float_start(d,ds):
    for s in kind(ds,'SYNTHETIC_RANGE_RESPONSE'):
        if 'start_block' in s: s['start_block']=float(s['start_block'])
def response_integer_capped(d,ds):
    for s in kind(ds,'SYNTHETIC_RANGE_RESPONSE'):
        if 'result_capped' in s: s['result_capped']=0
def response_null_evidence_kind(d,ds):
    for s in kind(ds,'SYNTHETIC_RANGE_RESPONSE'): s['evidence_kind']=None
def response_empty_payload(d,ds):
    for s in kind(ds,'SYNTHETIC_RANGE_RESPONSE'):
        s.clear(); s.update(provider_id='synthetic-provider-1',operator_id='synthetic-operator-1')
def header_wrong_parent(d,ds):
    new=sha(b'UNRELATED_START_BLOCK')
    d['window']['start_hash']=new
    for s in kind(ds,'HEADER_V1'):
        if s['number']==100: s['hash']=new
def real_relabel(d,ds): d['evidence_kind']='REAL_PREPARED_WITNESSES'
def coverage_wrong_population(d,ds): d['scope']['population_commitment']=sha(b'UNRELATED_POPULATION')
def costs_future(d,ds):
    key=sha(b'REVIEW_FUTURE_COST_SOURCE')
    ds[key]={'kind':'SYNTHETIC_RAW_COST','order':{'block':999999,'phase':'END_BLOCK','transaction_index':None,'log_index':None},'evidence_kind':'SYNTHETIC_NON_EVIDENTIARY'}
    for s in kind(ds,'EXECUTION_ECONOMICS_V1'): s['cost_evidence_refs']=[key]
def no_causes(d,ds):
    # One existing trigger is still consumed, but a second actionable birth is
    # added to the sequence without any causal trigger or acquisition witness.
    st=state_by_block(d,ds,103); st['trigger_ids']=[]
def state_order_extreme(d,ds):
    st=state_by_block(d,ds,103); st['order']={'block':103,'phase':'PRE_TX','transaction_index':2**100,'log_index':None}
def premature_final_phase(d,ds):
    state_by_block(d,ds,103)['order']={'block':103,'phase':'PRE_TX','transaction_index':0,'log_index':None}
def noop(d,ds): pass
def delayed_trigger(d,ds):
    state_by_block(d,ds,101)['trigger_ids']=[]
    state_by_block(d,ds,103)['trigger_ids']=['synthetic-trigger']
def derived_omits_successor_inputs(d,ds):
    additions=[]
    for h in list(d['coverage_refs']):
        s=ds[h]
        if s['trigger_class']=='INTEREST_ONLY_CROSSING_CANDIDATES': continue
        tail=copy.deepcopy(s); tail['start_block']=102
        tail['trigger_refs']=[r for r in s['trigger_refs'] if ds[r]['order']['block']>=102]
        s['trigger_refs']=[r for r in s['trigger_refs'] if ds[r]['order']['block']<=101]
        s['end_block']=101
        raw=ds[s['raw_response_ref']]
        if 'start_block' in raw:
            rawtail=copy.deepcopy(raw); rawtail['start_block']=102; rawtail['trigger_refs']=list(tail['trigger_refs'])
            raw['end_block']=101; raw['trigger_refs']=list(s['trigger_refs'])
            rawkey=sha(('TAIL_RESPONSE_'+h).encode()); ds[rawkey]=rawtail; tail['raw_response_ref']=rawkey
        key=sha(('TAIL_'+h).encode()); ds[key]=tail; additions.append(key)
    d['coverage_refs']+=additions
def arbitrary_terminal_source(d,ds):
    s=state_by_block(d,ds,101)
    algorithm=next(h for h,o in ds.items() if o.get('kind')=='SYNTHETIC_DETERMINISTIC_ALGORITHM')
    key=sha(b'REVIEW_TERMINAL')
    ds[key]={'kind':'TERMINAL_EVENT_V1','scope_id':d['scope']['scope_id'],'lineage_id':s['lineage_id'],'status':'CAPTURED','order':copy.deepcopy(s['order']),'source_ref':algorithm}
    s['terminal']='CAPTURED'; s['terminal_evidence_ref']=key
def generic_interest_cause(d,ds):
    h=next(h for h in d['trigger_refs'] if ds[h]['trigger_id']=='synthetic-trigger')
    t=ds[h]; t['trigger_class']='INTEREST_ONLY_CROSSING_CANDIDATES'
    if ds[t['source_ref']].get('kind')=='TRIGGER_SOURCE_V1': ds[t['source_ref']]['trigger_class']=t['trigger_class']
    for s in kind(ds,'COVERAGE_SEGMENT_V1'):
        s['trigger_refs']=[r for r in s['trigger_refs'] if r!=h]
        if s['trigger_class']==t['trigger_class']: s['trigger_refs'].append(h)
    for s in kind(ds,'SYNTHETIC_RANGE_RESPONSE'):
        if 'trigger_refs' in s: s['trigger_refs']=[r for r in s['trigger_refs'] if r!=h]

PROBES=[
 ('rejection_foreign_scope',{'disposition':'PROVEN_REJECTION'},reject_foreign_scope),
 ('rejection_foreign_lineage',{'disposition':'PROVEN_REJECTION'},reject_foreign_lineage),
 ('rejection_foreign_position',{'disposition':'PROVEN_REJECTION'},reject_foreign_position),
 ('rejection_future_state',{'disposition':'PROVEN_REJECTION'},reject_future_state),
 ('rejection_null_header',{'disposition':'PROVEN_REJECTION'},reject_null_header),
 ('rejection_untyped_stub',{'disposition':'PROVEN_REJECTION'},reject_untyped_state),
 ('rejection_detached_foreign_position',{'disposition':'PROVEN_REJECTION'},rejection_detached_position),
 ('rejection_contradicts_exact_history',{'disposition':'PROVEN_REJECTION'},rejection_contradicts_history),
 ('rejection_healthy_tail_missing',{'disposition':'PROVEN_REJECTION'},rejection_healthy_tail_missing),
 ('population_erased',{},erase_population),
 ('observed_episode_birth_without_any_causal_trigger',{},untriggered_observed_birth),
 ('nonactive_tail_missing',{},erase_future_tail),
 ('recovered_before_missing_window_tail',{'acquisition_hole':True},noop),
 ('trigger_unrelated_source',{},trigger_on_unrelated_source),
 ('raw_response_wrong_class',{},wrong_response_class),
 ('raw_response_float_block',{},response_float_start),
 ('raw_response_integer_boolean',{},response_integer_capped),
 ('raw_response_null_evidence_kind',{},response_null_evidence_kind),
 ('canonical_parent_mismatch',{},header_wrong_parent),
 ('synthetic_relabel_real',{},real_relabel),
 ('unrelated_population_commitment',{},coverage_wrong_population),
 ('underlying_economics_future_source',{},costs_future),
 ('transaction_index_exceeds_end_block_sentinel',{},state_order_extreme),
 ('right_censor_at_start_of_final_block',{'right':True},premature_final_phase),
 ('healthy_final_state_before_end_of_final_block',{},premature_final_phase),
 ('trigger_not_consumed_until_future_recovery',{},delayed_trigger),
 ('derived_full_window_using_prefix_inputs_only',{},derived_omits_successor_inputs),
 ('terminal_claim_backed_by_algorithm_doc',{},arbitrary_terminal_source),
 ('generic_interest_cause_without_bound_derivation',{},generic_interest_cause),
]

results=[]
for name,kwargs,mutate in PROBES:
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp); src=make(root/'src',**kwargs)
        try:
            remap_bundle(src,mutate)
            r=builder.build(src,src.parent,root/'pkg'); v=verifier.verify(root/'pkg')
            results.append({'probe':name,'outcome':'ACCEPTED' if r['material_unknown_count']==0 else 'BLOCKED',
                            'builder_status':r['status'],'verifier_status':v['status'],'unknowns':r['material_unknown_count'],
                            'blockers':r['blockers'],'terminal_authority':v['terminal_authority']})
        except Exception as e: results.append({'probe':name,'outcome':'REJECTED','error':str(e),'type':type(e).__name__})
        try:
            d=decode(src.read_bytes()); reconstructed=verifier.reconstruct(d,Store(src.parent,d['evidence']))
            r=reconstructed['report']
            results[-1]['independent_source_check']={'outcome':'BLOCKED' if r['material_unknown_count'] else 'ACCEPTED','blockers':r['blockers']}
        except Exception as e:
            results[-1]['independent_source_check']={'outcome':'REJECTED','error':str(e),'type':type(e).__name__}
print(json.dumps({'implementation':str(IMPL),'source_sha256':{p.name:sha(p.read_bytes()) for p in sorted(IMPL.glob('*.py'))},'results':results},indent=2))
if '--require-fail-closed' in sys.argv:
    assert all(r['outcome']=='BLOCKED' or (r['outcome']=='REJECTED' and r['type']=='Invalid') for r in results), 'Adversarial source admission remains open; inspect results.'
    assert all(r['independent_source_check']['outcome']=='BLOCKED' or (r['independent_source_check']['outcome']=='REJECTED' and r['independent_source_check']['type']=='Invalid') for r in results), 'Independent source reconstruction remains open; inspect results.'
