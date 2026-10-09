#!/usr/bin/env python3
"""Independent package traversal: never calls the builder or trusts its flags."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.dont_write_bytecode=True
from temporal_common import *


def independent_coverage(doc,store,triggers):
    scope,w=envelope(doc); issues=[]; rows=[]
    classes={c:[] for c in CLASSES}; universe={c:{h for h,t in triggers.items() if t['trigger_class']==c} for c in CLASSES}
    for ref in doc['coverage_refs']:
        r=store.get(ref,'COVERAGE_SEGMENT_V1')
        exact(r,('kind','scope_id','trigger_class','start_block','end_block','provider_id','operator_id',
                 'complete','acquisition_error','result_capped','trigger_refs','raw_response_ref',
                 'algorithm_ref','input_refs','equivalence_ref'),label='coverage')
        c=r['trigger_class']; need(c in classes,'unknown class'); need(r['scope_id']==scope['scope_id'],'coverage scope')
        lo=integer(r['start_block'],'start'); hi=integer(r['end_block'],'end'); need(w['start_block']<=lo<=hi<=w['end_block'],'range outside window')
        boolean(r['complete'],'complete'); boolean(r['result_capped'],'capped')
        unique(r['trigger_refs'],'segment refs')
        for h in r['trigger_refs']: need(h in universe[c] and lo<=point(triggers[h]['order'])[0]<=hi,'class/range trigger mismatch')
        if c in ACQUIRED:
            text(r['provider_id'],'provider'); text(r['operator_id'],'operator')
            z=store.get(r['raw_response_ref'])
            exact(z,('kind','provider_id','operator_id','scope_id','class','start_block','end_block','trigger_refs',
                     'result_capped','acquisition_error','source_ref','evidence_kind'),label='source range response')
            need(z['kind'] in ('SYNTHETIC_RANGE_RESPONSE','PREPARED_RANGE_RESPONSE_V1'),'range response type')
            need(z['evidence_kind']==doc['evidence_kind'] and
                 (z['kind']=='SYNTHETIC_RANGE_RESPONSE')==(z['evidence_kind']=='SYNTHETIC_NON_EVIDENTIARY'),
                 'range response evidence-kind mismatch')
            integer(z['start_block'],'response start'); integer(z['end_block'],'response end'); boolean(z['result_capped'],'response capped')
            need(z['class']==c and (z['scope_id'],z['start_block'],z['end_block'],z['trigger_refs'])==
                 (r['scope_id'],lo,hi,r['trigger_refs']),'source range/class/trigger coverage differs')
            need((z['provider_id'],z['operator_id'],z['result_capped'],z['acquisition_error'])==
                 (r['provider_id'],r['operator_id'],r['result_capped'],r['acquisition_error']),'response provider/error binding')
            store.get(z['source_ref'])
            need(r['algorithm_ref'] is None and r['equivalence_ref'] is None and r['input_refs']==[],'acquired/derived confusion')
        else:
            need(r['provider_id'] is None and r['operator_id'] is None and r['raw_response_ref'] is None,'derived provider fabrication')
            store.get(r['algorithm_ref']); store.get(r['equivalence_ref']); unique(r['input_refs'],'inputs')
            for event_hash in r['trigger_refs']:
                cause=store.get(triggers[event_hash]['source_ref'],'DERIVED_TRIGGER_SOURCE_V1')
                need((cause['algorithm_ref'],cause['equivalence_ref'])==(r['algorithm_ref'],r['equivalence_ref']),
                     'derived cause algorithm/equivalence differs from coverage')
            need(set(r['input_refs'])<=set(doc['coverage_refs']),'unadmitted derived input')
            need(set(ACQUIRED)<={store.get(h).get('trigger_class') for h in r['input_refs']},'missing derived input surface')
            for required_class in ACQUIRED:
                fragments={}
                for input_ref in r['input_refs']:
                    z=store.get(input_ref,'COVERAGE_SEGMENT_V1')
                    if z['trigger_class']==required_class:
                        need(z['complete'] is True and z['acquisition_error'] is None and z['result_capped'] is False,'bad derived input coverage')
                        fragments.setdefault((z['provider_id'],z['operator_id']),[]).append((max(lo,z['start_block']),min(hi,z['end_block'])))
                admitted=[]
                for identity,spans in fragments.items():
                    spans=sorted((a,b) for a,b in spans if a<=b)
                    if not spans or spans[0][0]!=lo: continue
                    edge=spans[0][1]
                    for a,b in spans[1:]:
                        if a>edge+1: break
                        edge=max(edge,b)
                    if edge==hi: admitted.append(identity)
                if len({a for a,b in admitted})<2 or len({b for a,b in admitted})<2:
                    issues.append({'code':'DERIVED_INPUT_COVERAGE_INCOMPLETE','class':required_class,'range':[lo,hi],'source':ref})
        if r['complete'] is not True or r['acquisition_error'] is not None or r['result_capped']:
            issues.append({'code':'ACQUISITION_INCOMPLETE','class':c,'range':[lo,hi],'source':ref})
        else: classes[c].append(r)
    for c,parts in classes.items():
        if not parts:
            issues.append({'code':'MISSING_TRIGGER_CLASS','class':c,'range':[w['start_block'],w['end_block']]}); continue
        provider_keys={r['provider_id'] if c in ACQUIRED else 'DERIVED' for r in parts}
        ops={r['operator_id'] for r in parts}
        sets=[]
        for provider in sorted(provider_keys):
            selected=[r for r in parts if (r['provider_id'] if c in ACQUIRED else 'DERIVED')==provider]
            need(c not in ACQUIRED or len({r['operator_id'] for r in selected})==1,'provider has conflicting operator')
            intervals=sorted((r['start_block'],r['end_block']) for r in selected)
            # Compute complement using interval boundaries, independently of the
            # builder's row cursor and reported coverage flags.
            boundaries=[(w['start_block']-1,w['start_block']-1)]+intervals+[(w['end_block']+1,w['end_block']+1)]
            for left,right in zip(boundaries,boundaries[1:]):
                need(left[1]<right[0],'overlapping or duplicate coverage')
                if right[0]>left[1]+1: issues.append({'code':'ACQUISITION_INCOMPLETE','class':c,'provider':provider,'range':[left[1]+1,right[0]-1]})
            listed=[h for r in selected for h in r['trigger_refs']]; need(len(listed)==len(set(listed)),'repeated covered trigger')
            s=set(listed); sets.append(s)
            if s!=universe[c]: issues.append({'code':'TRIGGER_SOURCE_COVERAGE_MISMATCH','class':c,'provider':provider})
        if c in ACQUIRED and (len(provider_keys)<2 or len(ops)<2): issues.append({'code':'DUAL_OPERATOR_AUTHORITY_MISSING','class':c})
        if any(s!=sets[0] for s in sets): issues.append({'code':'PROVIDER_TRIGGER_DISAGREEMENT','class':c})
    return issues


def independent_rejection(row,store,byid,scope,window,admitted_state_refs):
    exact(row,('trigger_id','category','reason','evidence_refs'),label='disposition')
    need(row['trigger_id'] in byid,'unknown disposition trigger'); text(row['reason'],'reason'); unique(row['evidence_refs'],'refs')
    for h in row['evidence_refs']: store.get(h)
    category=row['category']; need(category in ('PROVEN_REJECTION','EVIDENCE_INSUFFICIENT','ACQUISITION_INCOMPLETE'),'disposition category')
    if category!='PROVEN_REJECTION': return {'code':category,'trigger_id':row['trigger_id'],'reason':row['reason']}
    need(len(row['evidence_refs'])==1,'typed negative witness required')
    e=store.get(row['evidence_refs'][0],'REJECTION_WITNESS_V1'); exact(e,('kind','trigger_id','reason','witness_ref'))
    need((e['trigger_id'],e['reason'])==(row['trigger_id'],row['reason']),'negative proof binding')
    need(e['witness_ref'] in admitted_state_refs,'negative proof detached from admitted state history')
    state,_=snapshot(store,e['witness_ref'],scope,window)
    t=byid[row['trigger_id']]
    need((state['lineage_id'],point(state['order']))==(t['lineage_id'],point(t['order'])),
         'negative witness not at exact lineage/trigger prestate')
    reason=row['reason']
    if reason=='NONPOSITIVE_SUCCESS_PATH_NET':
        need(state['execution_ref'] is not None,'missing economic prestate witness')
        value=execution(store,state['execution_ref'],state)['success_path_net_usd_wad']; need(value<=0,'nonpositive predicate false')
    elif reason in ('ZERO_DEBT','PROTOCOL_ACTION_DISABLED'):
        st=state['state']
        need((type(st['debt_units']) is int and st['debt_units']==0) if reason=='ZERO_DEBT' else st['protocol_action_enabled'] is False,'negative state predicate false')
    else: raise Invalid('unrecognized proven-negative semantics: '+reason)
    return None


def reconstruct(doc,store):
    scope,w=envelope(doc); pop=population(doc,store); ts={h:trigger(store,h,scope,w) for h in doc['trigger_refs']}
    byid={t['trigger_id']:t for t in ts.values()}; need(len(byid)==len(ts),'duplicate trigger identity')
    need(all(t['lineage_id'] in pop for t in ts.values()),'trigger not in source population')
    issues=independent_coverage(doc,store,ts); histories={}; used={}
    for h in doc['state_refs']:
        s,time=snapshot(store,h,scope,w); histories.setdefault(s['lineage_id'],[]).append({'s':s,'hash':h,'time':time})
        need(s['lineage_id'] in pop and {k:s[k] for k in ('lineage_id','market_id','position_id','asset_pair')}==pop[s['lineage_id']],
             'state population binding')
        for tid in s['trigger_ids']:
            need(tid in byid,'unknown state trigger'); t=byid[tid]
            tq,sq=point(t['order']),point(s['order'])
            direct=tq==sq or (t['order']['block']==s['order']['block'] and t['order']['transaction_index']==s['order']['transaction_index']
                             and t['order']['phase'] in ('PRE_TX','LOG') and s['order']['phase']=='POST_TX')
            need(t['lineage_id']==s['lineage_id'] and direct,'causal trigger mismatch or unsupported delayed state')
            need(tid not in used or used[tid]==s['lineage_id'],'cross-lineage consumption'); used[tid]=s['lineage_id']
    seen_headers={}
    for history in histories.values():
        for r in history:
            hd=store.get(r['s']['header_ref']); n=hd['number']
            need(n not in seen_headers or seen_headers[n]==hd,'header collision')
            seen_headers[n]=hd
    for a,b in zip(sorted(seen_headers),sorted(seen_headers)[1:]):
        if b==a+1: need(seen_headers[a]['hash']==seen_headers[b]['parent_hash'],'header parent chain mismatch')
    expected=[]
    issues += [{'code':'UNACCOUNTED_POPULATION_LINEAGE','lineage':x} for x in sorted(set(pop)-set(histories))]
    for lineage,hist in sorted(histories.items()):
        hist.sort(key=lambda r:point(r['s']['order']))
        need(len({point(r['s']['order']) for r in hist})==len(hist),'duplicate state position')
        need(len({(r['s']['market_id'],r['s']['position_id'],tuple(r['s']['asset_pair'])) for r in hist})==1,'lineage identity change')
        need(all(a['time']<=b['time'] for a,b in zip(hist,hist[1:])),'nonmonotonic header time')
        if point(hist[0]['s']['order'])!=point(w['start_order']): issues.append({'code':'ACQUISITION_INCOMPLETE','lineage':lineage,'reason':'INITIAL_STATE_NOT_AT_WINDOW_START'})
        if point(hist[-1]['s']['order'])!=point(w['end_order']): issues.append({'code':'ACQUISITION_INCOMPLETE','lineage':lineage,'reason':'FINAL_STATE_NOT_AT_WINDOW_END'})
        i=0; sequence=0
        while i<len(hist):
            first=hist[i]; state=first['s']
            if not actionable(state):
                need(state['terminal'] is None,'terminal without active interval'); i+=1; continue
            left=(i==0 and point(state['order'])==point(w['start_order']))
            earlier_healthy=i>0 and not actionable(hist[i-1]['s'])
            if not left and not earlier_healthy:
                issues.append({'code':'EVIDENCE_INSUFFICIENT','lineage':lineage,'reason':'BIRTH_NOT_OBSERVED'}); i+=1; continue
            sequence+=1; end=None; status=None
            for j in range(i,len(hist)):
                s=hist[j]['s']
                if s['terminal']:
                    ev=store.get(s['terminal_evidence_ref'],'TERMINAL_EVENT_V1')
                    exact(ev,('kind','scope_id','lineage_id','status','order','source_ref'),label='terminal event')
                    need(ev['scope_id']==scope['scope_id'] and ev['lineage_id']==lineage and ev['order']==s['order'] and ev['status']==s['terminal'],'terminal source binding')
                    terminal_source=store.get(ev['source_ref'],'TERMINAL_SOURCE_V1')
                    exact(terminal_source,('kind','scope_id','lineage_id','status','order','payload_ref'),label='terminal source')
                    need(all(terminal_source[k]==ev[k] for k in ('scope_id','lineage_id','status','order')),'terminal status/order identity mismatch')
                    store.get(terminal_source['payload_ref']); no_future_evidence(store,s['terminal_evidence_ref'],s['order'])
                    end=j; status=s['terminal']; break
                if not actionable(s):
                    status='RECOVERED' if s['state']['debt_units']==0 or s['state']['health_factor_wad']>=10**18 else 'EXPIRED'; end=j; break
            end_index=len(hist)-1 if end is None else end; interval=hist[i:end_index+1]
            exe=next((r for r in interval if actionable(r['s']) and r['s']['execution_ref']),None)
            boundary=end is None and point(hist[-1]['s']['order'])==point(w['end_order'])
            hole=end is None and not boundary
            eid=digest({'scope':scope['scope_id'],'lineage':lineage,'first_state':first['hash'],'sequence':sequence})
            if not left and not state['trigger_ids']:
                issues.append({'code':'EVIDENCE_INSUFFICIENT','episode_id':eid,'reason':'OBSERVED_BIRTH_HAS_NO_ADMITTED_CAUSAL_TRIGGER'})
            if end is not None and not hist[end]['s']['trigger_ids']:
                issues.append({'code':'EVIDENCE_INSUFFICIENT','episode_id':eid,'reason':'TERMINAL_TRANSITION_HAS_NO_ADMITTED_CAUSAL_TRIGGER'})
            row={'episode_id':eid,'lineage_id':lineage,'market_id':state['market_id'],'position_id':state['position_id'],'asset_pair':state['asset_pair'],
                 'left_censored':left,'right_censored':boundary,'birth':None if left else state['order'],
                 'first_actionable':state['order'],'first_executable':None if exe is None else exe['s']['order'],
                 'execution_economics_ref':None if exe is None else exe['s']['execution_ref'],
                 'terminal':{'status':'EVIDENCE_INSUFFICIENT' if hole else 'RIGHT_CENSORED' if boundary else status,'order':None if end is None else hist[end]['s']['order']},
                 'lifetime_seconds':None if left or end is None else hist[end]['time']-first['time'],
                 'observed_duration_seconds':None if end is None else hist[end]['time']-first['time'],
                 'state_refs':sorted({r['hash'] for r in interval}),
                 'trigger_ids':sorted({t for r in interval for t in r['s']['trigger_ids']}),
                 'time_to_first_competitor_arrival_ms':None,'competitor_arrival_observability':'NOT_OBSERVED'}
            if not hole and exe is None: issues.append({'code':'EVIDENCE_INSUFFICIENT','episode_id':eid,'reason':'HISTORICAL_EXECUTION_ECONOMICS_NOT_SUPPLIED'})
            expected.append(row); i=end_index+1
    rejected=set()
    for r in doc['dispositions']:
        tid=r['trigger_id']; need(tid not in rejected and tid not in used,'double-counted trigger disposition')
        problem=independent_rejection(r,store,byid,scope,w,set(doc['state_refs'])); rejected.add(tid)
        if problem: issues.append(problem)
    issues += [{'code':'UNACCOUNTED_TRIGGER','trigger_id':tid} for tid in sorted(set(byid)-set(used)-rejected)]
    episode_triggers={t for row in expected for t in row['trigger_ids']}
    issues += [{'code':'TRIGGER_NOT_LINKED_TO_EPISODE_OR_REJECTION','trigger_id':tid} for tid in sorted(set(used)-episode_triggers)]
    report={'schema':'nqc-temporal-local-report-v1','status':'LOCAL_PACKAGE_CANDIDATE_COMPLETE_NOT_CERTIFIED' if not issues else 'LOCAL_PACKAGE_BLOCKED',
            'evidence_kind':doc['evidence_kind'],'terminal_authority':False,'real_market_census_closed':False,
            'chain_semantic_replay_certified':False,'independent_provider_identity_certified':False,
            'execution_economics_semantically_verified':False,
            'terminal_outcome_semantically_verified':False,
            'coverage_complete_for_supplied_scope':not issues,'material_unknown_count':len(issues),
            'blockers':sorted(issues,key=canonical),'scope':scope,'window':w,'trigger_count':len(byid),
            'population_lineage_count':len(pop),'observed_population_lineage_count':len(histories),
            'consumed_trigger_count':len(used),'disposition_count':len(rejected),'episode_count':len(expected),
            'observability_limited_competitor_arrival_count':len(expected)}
    return {'report':report,'episodes':sorted(expected,key=lambda x:x['episode_id']),
            'dispositions':sorted(doc['dispositions'],key=lambda x:x['trigger_id'])}


def verify(root):
    root=Path(root); raw=safe_file(root,'manifest.json').read_bytes(); m=decode(raw)
    exact(m,('schema','evidence_kind','terminal_authority','real_market_census_closed','source_sha256','files'))
    need(m['schema']=='nqc-temporal-local-package-v1','package schema'); need(m['terminal_authority'] is False and m['real_market_census_closed'] is False,'unauthorized terminal marker')
    need(type(m['files']) is dict,'file inventory')
    actual=set()
    for path in root.rglob('*'):
        need(not path.is_symlink(),'symlink in package')
        if path.is_file(): actual.add(path.relative_to(root).as_posix())
    need(actual==set(m['files'])|{'manifest.json'},'package file membership mismatch')
    for rel,ref in m['files'].items():
        exact(ref,('sha256','bytes')); hash32(ref['sha256']); integer(ref['bytes'],'file bytes')
        b=safe_file(root,rel).read_bytes(); need(sha(b)==ref['sha256'] and len(b)==ref['bytes'],'package digest mismatch: '+rel)
    source=safe_file(root,'raw-source.json').read_bytes(); need(sha(source)==m['source_sha256'],'source hash mismatch')
    doc=decode(source); scope,w=envelope(doc); need(m['evidence_kind']==doc['evidence_kind'],'evidence kind substitution')
    inventory=[{'path':e['sha256'],'sha256':e['sha256'],'bytes':e['bytes']} for e in doc['evidence']]
    store=Store(root/'evidence',inventory)
    # Original locators remain bound by raw-source.json; package storage is CAS.
    need(set(m['files'])=={'raw-source.json','report.json','episodes.jsonl','dispositions.jsonl'}|{'evidence/'+e['sha256'] for e in doc['evidence']},'unexpected payload')
    expected=reconstruct(doc,store)
    for name in ('episodes','dispositions'):
        data=safe_file(root,name+'.jsonl').read_bytes(); got=[decode(line) for line in data.splitlines()]
        need(data==b''.join(canonical(row) for row in expected[name]),'independent '+name+' reconstruction mismatch')
        need(data==b''.join(canonical(row) for row in got),'noncanonical output ledger')
    report_raw=safe_file(root,'report.json').read_bytes(); report=decode(report_raw)
    need(report_raw==canonical(expected['report']),'independent report/count/coverage mismatch')
    return {'status':'LOCAL_PACKAGE_INDEPENDENTLY_VERIFIED_NOT_CERTIFIED','source_status':report['status'],
            'evidence_kind':doc['evidence_kind'],'terminal_authority':False,'real_market_census_closed':False,
            'source_sha256':sha(source),'episode_count':report['episode_count'],'material_unknown_count':report['material_unknown_count']}


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--package',required=True,type=Path); a=p.parse_args()
    try: r=verify(a.package)
    except (Invalid,OSError,KeyError,TypeError) as exc:
        print(json.dumps({'status':'PACKAGE_REJECTED','error':str(exc),'terminal_authority':False,'real_market_census_closed':False})); return 2
    print(json.dumps(r,sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
