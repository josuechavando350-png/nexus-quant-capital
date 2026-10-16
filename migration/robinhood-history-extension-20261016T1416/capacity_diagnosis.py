"""Explain the observed local capacity stop offline, without changing limits."""
import hashlib,json
from pathlib import Path
from continue_history import HERE,engine

def counts(state):
    events=[e for segment in state['segments'] for e in segment['events']]
    return {'logs':len(events),'event_blocks':len({e['block'] for e in events}),
            'borrowers':len({e['borrower'] for e in events})}

def diagnose(folder):
    folder=Path(folder);policy=json.loads((HERE/'policy.json').read_text())
    original={name:(folder/name).read_bytes() for name in ('source-registry.json','older-registry.json','registry.json')}
    source=engine.registry.load(folder/'source-registry.json',policy)
    older=engine.registry.load(folder/'older-registry.json',policy)
    assert original['registry.json']==original['source-registry.json']
    assert older['through_block']+1==source['from_block']
    assert older['checkpoint']==source['segments'][0]['start']
    union={'segments':older['segments']+source['segments']}
    limits={'logs':policy['max_logs'],'event_blocks':policy['max_event_blocks'],'borrowers':policy['max_borrowers']}
    combined_counts=counts(union)
    old_accounts={e['borrower'] for s in source['segments'] for e in s['events']}
    new_accounts={e['borrower'] for s in older['segments'] for e in s['events']}-old_accounts
    prefix=older;failure=None
    for segment in source['segments']:
        proposed={'segments':prefix['segments']+[segment]}
        try:
            prefix=engine.registry.append(prefix,segment['first'],segment['start'],segment['end'],
                                          segment['raw_logs'],segment['event_headers'],policy)
        except ValueError as error:
            assert str(error)=='REGISTRY_CAPACITY_NO_TRIMMING'
            failure={'source_segment_first':segment['first'],'source_segment_last':segment['end']['number'],
                     'counts_before':counts(prefix),'proposed_counts':counts(proposed),'reason':str(error)}
            break
    assert failure is not None
    result={'offline_only':True,'rpc_calls':0,'limits_changed':False,'source_counts':counts(source),
            'history_counts':counts(older),'union_counts_not_persisted':combined_counts,'limits':limits,
            'violated_limits':[name for name,value in combined_counts.items() if value>limits[name]],
            'new_accounts_in_unmerged_history':sorted(new_accounts),'first_merge_rejection':failure,
            'files_sha256':{name:hashlib.sha256(raw).hexdigest() for name,raw in original.items()},
            'history_window_complete':older['through_block']-older['from_block']+1==400000,
            'merged_registry_persisted':(folder/'merged-before-catchup.json').exists(),
            'cohort_frozen':(folder/'cohort.json').exists(),
            'current_coverage_measured':False,'current_candidates_measured':False}
    assert all((folder/name).read_bytes()==raw for name,raw in original.items())
    return result

if __name__=='__main__':
    result=diagnose(HERE/'evidence/pilot')
    (HERE/'evidence/capacity-diagnosis.json').write_bytes(engine.canonical(result))
    print(json.dumps(result,indent=2))
