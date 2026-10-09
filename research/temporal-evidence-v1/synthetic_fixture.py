"""Small explicitly synthetic, non-evidentiary witnesses for regression only."""
from pathlib import Path
from temporal_common import *


def make(root, *, left=False, right=False, acquisition_hole=False, coverage_gap=False,
         same_operator=False, no_execution=False, invalid_execution_hash=False,
         future_economics=False, disposition=None, false_negative=False, derived_cause=False):
    root=Path(root); root.mkdir(parents=True,exist_ok=True); inventory=[]; saved={}
    def put(obj):
        raw=canonical(obj); h=sha(raw)
        if h not in saved:
            (root/h).write_bytes(raw); inventory.append({'path':h,'sha256':h,'bytes':len(raw)}); saved[h]=obj
        return h
    def pt(b): return {'block':b,'phase':'END_BLOCK','transaction_index':None,'log_index':None}
    def block(b): return sha(('SYNTHETIC_BLOCK_'+str(b)).encode())
    pop=put({'kind':'POPULATION_V1','scope_id':'SYNTHETIC_SCOPE_ONLY','positions':[
        {'lineage_id':'synthetic-lineage','market_id':'SYNTHETIC_AAVE_MARKET','position_id':'synthetic-position','asset_pair':['TOKEN_A','TOKEN_B']}]})
    scope={'scope_id':'SYNTHETIC_SCOPE_ONLY','chain_id':1,'market_ids':['SYNTHETIC_AAVE_MARKET'],'population_commitment':pop}
    window={'start_block':100,'end_block':103,'start_hash':block(100),'end_hash':block(103),'start_order':pt(100),'end_order':pt(103)}
    origin=put({'kind':'SYNTHETIC_RAW_EVENT','evidence_kind':'SYNTHETIC_NON_EVIDENTIARY','no_chain_authority':True})
    algo=put({'kind':'SYNTHETIC_DETERMINISTIC_ALGORITHM','evidence_kind':'SYNTHETIC_NON_EVIDENTIARY'})
    tblock=100 if left else 101
    trigger_class='INTEREST_ONLY_CROSSING_CANDIDATES' if derived_cause else 'POSITION_MUTATIONS'
    cause={'kind':'DERIVED_TRIGGER_SOURCE_V1' if derived_cause else 'TRIGGER_SOURCE_V1','scope_id':scope['scope_id'],'lineage_id':'synthetic-lineage',
           'trigger_id':'synthetic-trigger','trigger_class':trigger_class,'order':pt(tblock),'payload_ref':origin}
    if derived_cause:
        inputs=[put({'kind':'CAUSAL_INPUT_WITNESS_V1','scope_id':scope['scope_id'],'trigger_class':c,'order':pt(tblock),'source_ref':origin})
                for c in ('POSITION_MUTATIONS','PROTOCOL_CONFIG_MUTATIONS','ORACLE_PRICE_TRANSITIONS','RATE_INDEX_SEGMENTS')]
        cause.update(algorithm_ref=algo,input_refs=inputs,equivalence_ref=algo)
    trigger_source=put(cause)
    t=put({'kind':'TRIGGER_V1','trigger_id':'synthetic-trigger','trigger_class':trigger_class,
           'lineage_id':'synthetic-lineage','order':pt(tblock),'scope_id':scope['scope_id'],'source_ref':trigger_source})
    trigger_refs=[t]; trigger_at={tblock:['synthetic-trigger']}
    if not right and disposition is None:
        recovery_block=102 if acquisition_hole else 103
        recovery_source=put({'kind':'TRIGGER_SOURCE_V1','scope_id':scope['scope_id'],'lineage_id':'synthetic-lineage',
                            'trigger_id':'synthetic-recovery','trigger_class':'POSITION_MUTATIONS','order':pt(recovery_block),'payload_ref':origin})
        recovery=put({'kind':'TRIGGER_V1','trigger_id':'synthetic-recovery','trigger_class':'POSITION_MUTATIONS',
                      'lineage_id':'synthetic-lineage','order':pt(recovery_block),'scope_id':scope['scope_id'],'source_ref':recovery_source})
        trigger_refs.append(recovery); trigger_at[recovery_block]=['synthetic-recovery']
    states=[]
    for b,healthy in [(100,not left),(101,False),(102 if acquisition_hole else 103,not right)]:
        header=put({'kind':'HEADER_V1','chain_id':1,'number':b,'hash':block(b),'parent_hash':block(b-1),'timestamp':b*12})
        state={'kind':'STATE_SNAPSHOT_V1','scope_id':scope['scope_id'],'lineage_id':'synthetic-lineage',
               'market_id':scope['market_ids'][0],'position_id':'synthetic-position','asset_pair':['TOKEN_A','TOKEN_B'],
               'order':pt(b),'header_ref':header,'state':{'health_factor_wad':11*10**17 if healthy else 9*10**17,'debt_units':10,'protocol_action_enabled':True},
               'trigger_ids':trigger_at.get(b,[]) if disposition is None else [],
               'execution_ref':None,'terminal':None,'terminal_evidence_ref':None}
        if not healthy and b==tblock and not no_execution:
            e={'kind':'EXECUTION_ECONOMICS_V1','prestate_commitment':state_commitment(state),'pre_state_order':pt(b),
               'max_evidence_order':pt(b+1 if future_economics else b),'success_path_net_usd_wad':5,
               'costs_complete':True,'cost_evidence_refs':[origin],'execution_evidence_ref':origin}
            state['execution_ref']='not-a-hash' if invalid_execution_hash else put(e)
        states.append(put(state))
    cov=[]
    for c in ACQUIRED:
        for j in (1,2):
            provider='synthetic-provider-'+str(j); operator='synthetic-operator-'+str(1 if same_operator else j)
            covered=[h for h in trigger_refs if saved[h]['trigger_class']==c and saved[h]['order']['block'] <= (101 if coverage_gap else 103)]
            raw=put({'kind':'SYNTHETIC_RANGE_RESPONSE','provider_id':provider,'operator_id':operator,'class':c,'evidence_kind':'SYNTHETIC_NON_EVIDENTIARY',
                     'scope_id':scope['scope_id'],'start_block':100,'end_block':101 if coverage_gap else 103,
                     'trigger_refs':covered,'result_capped':False,'acquisition_error':None,'source_ref':origin})
            cov.append(put({'kind':'COVERAGE_SEGMENT_V1','scope_id':scope['scope_id'],'trigger_class':c,
                            'start_block':100,'end_block':101 if coverage_gap else 103,'provider_id':provider,'operator_id':operator,
                            'complete':True,'acquisition_error':None,'result_capped':False,
                            'trigger_refs':covered,'raw_response_ref':raw,
                            'algorithm_ref':None,'input_refs':[],'equivalence_ref':None}))
    cov.append(put({'kind':'COVERAGE_SEGMENT_V1','scope_id':scope['scope_id'],'trigger_class':'INTEREST_ONLY_CROSSING_CANDIDATES',
                    'start_block':100,'end_block':103,'provider_id':None,'operator_id':None,'complete':True,'acquisition_error':None,
                    'result_capped':False,'trigger_refs':[t] if derived_cause else [],'raw_response_ref':None,'algorithm_ref':algo,'input_refs':list(cov),'equivalence_ref':algo}))
    dispositions=[]
    if disposition:
        row={'trigger_id':'synthetic-trigger','category':disposition,'reason':'MISSING_RAW_STATE','evidence_refs':[]}
        if disposition=='PROVEN_REJECTION':
            row['reason']='ZERO_DEBT'
            rewritten=[]
            for ref in states:
                s=decode((root/ref).read_bytes()); s['execution_ref']=None
                s['state']['debt_units']=10 if false_negative else 0
                s['state']['health_factor_wad']=11*10**17
                rewritten.append(put(s))
            states=rewritten; proofref=states[1]
            row['evidence_refs']=[put({'kind':'REJECTION_WITNESS_V1','trigger_id':'synthetic-trigger','reason':'ZERO_DEBT','witness_ref':proofref})]
        dispositions=[row]
        if disposition!='PROVEN_REJECTION': states=[]
    source={'schema':SCHEMA,'evidence_kind':'SYNTHETIC_NON_EVIDENTIARY','scope':scope,'window':window,
            'evidence':sorted(inventory,key=lambda e:e['path']),'coverage_refs':cov,'trigger_refs':trigger_refs,
            'state_refs':states,'dispositions':dispositions}
    path=root/'source.json'; path.write_bytes(canonical(source)); return path


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',required=True,type=Path)
    a=p.parse_args()
    need(not a.out.exists(),'fixture destination must not exist')
    print(make(a.out))
