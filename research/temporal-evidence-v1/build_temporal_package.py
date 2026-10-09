#!/usr/bin/env python3
"""Build deterministic local episode packages from immutable prepared witnesses."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.dont_write_bytecode=True
from temporal_common import *


def coverage(doc,store,triggers):
    _,w=envelope(doc); groups={c:{} for c in CLASSES}; blockers=[]; normalized=[]
    reference_sets={c:{h for h,t in triggers.items() if t['trigger_class']==c} for c in CLASSES}
    for ref in doc['coverage_refs']:
        x=store.get(ref,'COVERAGE_SEGMENT_V1')
        exact(x,('kind','scope_id','trigger_class','start_block','end_block','provider_id','operator_id',
                 'complete','acquisition_error','result_capped','trigger_refs','raw_response_ref',
                 'algorithm_ref','input_refs','equivalence_ref'),label='coverage')
        c=x['trigger_class']; need(c in CLASSES,'coverage class')
        need(x['scope_id']==doc['scope']['scope_id'],'coverage scope mismatch')
        a=integer(x['start_block'],'segment start'); b=integer(x['end_block'],'segment end')
        need(w['start_block']<=a<=b<=w['end_block'],'segment outside declared window')
        boolean(x['complete'],'complete'); boolean(x['result_capped'],'result_capped')
        unique(x['trigger_refs'],'segment triggers')
        for h in x['trigger_refs']:
            need(h in reference_sets[c],'segment trigger does not belong to declared class/universe')
            need(a<=point(triggers[h]['order'])[0]<=b,'trigger outside its segment')
        if c in ACQUIRED:
            text(x['provider_id'],'provider id'); text(x['operator_id'],'operator id')
            need(x['algorithm_ref'] is None and x['equivalence_ref'] is None and x['input_refs']==[],'acquired surface cannot invent derivation')
            raw=store.get(x['raw_response_ref'])
            exact(raw,('kind','provider_id','operator_id','scope_id','class','start_block','end_block','trigger_refs',
                       'result_capped','acquisition_error','source_ref','evidence_kind'),label='prepared range response')
            need(raw['kind'] in ('SYNTHETIC_RANGE_RESPONSE','PREPARED_RANGE_RESPONSE_V1'),'unsupported range response kind')
            need(raw['evidence_kind']==doc['evidence_kind'] and
                 (raw['kind']=='SYNTHETIC_RANGE_RESPONSE')==(raw['evidence_kind']=='SYNTHETIC_NON_EVIDENTIARY'),
                 'range response evidence kind is invalid or inconsistent')
            integer(raw['start_block'],'response start'); integer(raw['end_block'],'response end'); boolean(raw['result_capped'],'response capped')
            need(all(raw[k]==x[k] for k in ('provider_id','operator_id','scope_id','start_block','end_block','trigger_refs','result_capped','acquisition_error'))
                 and raw['class']==c,'raw response scope/range/class/records mismatch')
            store.get(raw['source_ref'])
            key=x['provider_id']
        else:
            need(x['provider_id'] is None and x['operator_id'] is None and x['raw_response_ref'] is None,'derived crossing cannot invent provider independence')
            store.get(x['algorithm_ref']); store.get(x['equivalence_ref'])
            for trigger_ref in x['trigger_refs']:
                derivation=store.get(triggers[trigger_ref]['source_ref'],'DERIVED_TRIGGER_SOURCE_V1')
                need(derivation['algorithm_ref']==x['algorithm_ref'] and derivation['equivalence_ref']==x['equivalence_ref'],
                     'derived trigger is not bound to its admitted algorithm/equivalence')
            need(bool(unique(x['input_refs'],'derived inputs')),'derived inputs absent')
            for h in x['input_refs']: store.get(h)
            input_classes={store.get(h).get('trigger_class') for h in x['input_refs']}
            need(set(ACQUIRED)<=input_classes,'crossings lack authenticated input classes')
            need(set(x['input_refs'])<=set(doc['coverage_refs']),'derived inputs not coverage witnesses')
            for input_class in ACQUIRED:
                supporting={}
                for h in x['input_refs']:
                    z=store.get(h,'COVERAGE_SEGMENT_V1')
                    if z['trigger_class']!=input_class: continue
                    need(z['complete'] is True and z['result_capped'] is False and z['acquisition_error'] is None,'incomplete derived input segment')
                    supporting.setdefault((z['provider_id'],z['operator_id']),[]).append((z['start_block'],z['end_block']))
                covering=[]
                for identity,intervals in supporting.items():
                    cursor=a
                    for lo,hi in sorted(intervals):
                        if hi<cursor: continue
                        if lo>cursor: break
                        cursor=max(cursor,hi+1)
                    if cursor>b: covering.append(identity)
                if len({p for p,o in covering})<2 or len({o for p,o in covering})<2:
                    blockers.append({'code':'DERIVED_INPUT_COVERAGE_INCOMPLETE','class':input_class,'range':[a,b],'source':ref})
            key='DERIVED'
        if not x['complete'] or x['acquisition_error'] is not None or x['result_capped']:
            blockers.append({'code':'ACQUISITION_INCOMPLETE','class':c,'range':[a,b],'source':ref})
            continue
        groups[c].setdefault(key,[]).append((a,b,x,ref)); normalized.append(ref)
    for c,providers in groups.items():
        operators={}; allsets=[]
        if not providers:
            blockers.append({'code':'MISSING_TRIGGER_CLASS','class':c,'range':[w['start_block'],w['end_block']]}); continue
        for provider,segments in sorted(providers.items()):
            segments.sort(key=lambda t:(t[0],t[1],t[3])); cursor=w['start_block']; seen=set()
            for a,b,x,h in segments:
                need(a>=cursor,'overlapping coverage segments')
                if a>cursor: blockers.append({'code':'ACQUISITION_INCOMPLETE','class':c,'provider':provider,'range':[cursor,a-1]})
                cursor=b+1
                need(not (seen&set(x['trigger_refs'])),'trigger duplicated across coverage segments')
                seen.update(x['trigger_refs'])
                if c in ACQUIRED:
                    old=operators.setdefault(provider,x['operator_id']); need(old==x['operator_id'],'provider operator changed')
            if cursor<=w['end_block']: blockers.append({'code':'ACQUISITION_INCOMPLETE','class':c,'provider':provider,'range':[cursor,w['end_block']]})
            if seen != reference_sets[c]: blockers.append({'code':'TRIGGER_SOURCE_COVERAGE_MISMATCH','class':c,'provider':provider})
            allsets.append(seen)
        if c in ACQUIRED and (len(providers)<2 or len(set(operators.values()))<2):
            blockers.append({'code':'DUAL_OPERATOR_AUTHORITY_MISSING','class':c})
        if allsets and any(x!=allsets[0] for x in allsets): blockers.append({'code':'PROVIDER_TRIGGER_DISAGREEMENT','class':c})
    return sorted(blockers,key=lambda x:canonical(x)),sorted(normalized)


def compile_bundle(doc,store):
    scope,w=envelope(doc); pop=population(doc,store); triggers={}; byid={}
    for h in doc['trigger_refs']:
        t=trigger(store,h,scope,w); need(t['trigger_id'] not in byid,'duplicate trigger id')
        need(t['lineage_id'] in pop,'trigger outside declared population')
        triggers[h]=t; byid[t['trigger_id']]=t
    blockers,covrefs=coverage(doc,store,triggers)
    lineages={}; consumed={}
    headers={}
    for h in doc['state_refs']:
        state,ts=snapshot(store,h,scope,w)
        need(state['lineage_id'] in pop,'snapshot outside population')
        need({k:state[k] for k in ('lineage_id','market_id','position_id','asset_pair')}==pop[state['lineage_id']],
             'snapshot population identity mismatch')
        header=store.get(state['header_ref']); number=header['number']
        need(number not in headers or headers[number]==header,'conflicting header at one height')
        headers[number]=header
        for tid in state['trigger_ids']:
            need(tid in byid,'state references unknown trigger')
            t=byid[tid]; need(t['lineage_id']==state['lineage_id'],'trigger crosses lineage')
            tq,sq=point(t['order']),point(state['order'])
            immediate=tq==sq or (tq[0:2]==sq[0:2] and t['order']['phase'] in ('PRE_TX','LOG') and state['order']['phase']=='POST_TX')
            need(immediate,'trigger not linked to its exact or immediate post-transaction state')
            old=consumed.setdefault(tid,state['lineage_id']); need(old==state['lineage_id'],'trigger duplicated across lineages')
        lineages.setdefault(state['lineage_id'],[]).append((point(state['order']),h,state,ts))
    for number,header in headers.items():
        if number-1 in headers: need(header['parent_hash']==headers[number-1]['hash'],'consecutive canonical header parent mismatch')
    episodes=[]
    for lineage in sorted(set(pop)-set(lineages)):
        blockers.append({'code':'UNACCOUNTED_POPULATION_LINEAGE','lineage':lineage})
    for lineage,rows in sorted(lineages.items()):
        rows.sort(); need(len({r[0] for r in rows})==len(rows),'duplicate state order')
        identity={(r[2]['market_id'],r[2]['position_id'],tuple(r[2]['asset_pair'])) for r in rows}; need(len(identity)==1,'lineage identity changed')
        need(all(rows[i][3]<=rows[i+1][3] for i in range(len(rows)-1)),'timestamp reversal')
        if rows[0][0]!=point(w['start_order']): blockers.append({'code':'ACQUISITION_INCOMPLETE','lineage':lineage,'reason':'INITIAL_STATE_NOT_AT_WINDOW_START'})
        if rows[-1][0]!=point(w['end_order']): blockers.append({'code':'ACQUISITION_INCOMPLETE','lineage':lineage,'reason':'FINAL_STATE_NOT_AT_WINDOW_END'})
        active=None; previous=None; seq=0
        def finish(terminal,state_row=None):
            nonlocal active
            if active is None: return
            if terminal=='RIGHT_CENSORED':
                active.update(right_censored=True,terminal={'status':terminal,'order':None},lifetime_seconds=None,observed_duration_seconds=None)
            else:
                _,h,s,ts=state_row
                if not s['trigger_ids']:
                    blockers.append({'code':'EVIDENCE_INSUFFICIENT','episode_id':active['episode_id'],'reason':'TERMINAL_TRANSITION_HAS_NO_ADMITTED_CAUSAL_TRIGGER'})
                active.update(right_censored=False,terminal={'status':terminal,'order':s['order']},
                              lifetime_seconds=None if active['left_censored'] else ts-active.pop('_birth_timestamp'),
                              observed_duration_seconds=ts-active['_first_timestamp'])
            active.pop('_birth_timestamp',None); active.pop('_first_timestamp',None)
            active['state_refs']=sorted(set(active['state_refs'])); active['trigger_ids']=sorted(set(active['trigger_ids']))
            if active['first_executable'] is None: blockers.append({'code':'EVIDENCE_INSUFFICIENT','episode_id':active['episode_id'],'reason':'HISTORICAL_EXECUTION_ECONOMICS_NOT_SUPPLIED'})
            episodes.append(active); active=None
        for index,row in enumerate(rows):
            order,h,s,ts=row; a=actionable(s)
            if active is None and a:
                known_start = index==0 and order==point(w['start_order'])
                known_birth = previous is not None and not actionable(previous[2])
                if not known_start and not known_birth:
                    blockers.append({'code':'EVIDENCE_INSUFFICIENT','lineage':lineage,'reason':'BIRTH_NOT_OBSERVED'}); previous=row; continue
                seq+=1
                active={'episode_id':digest({'scope':scope['scope_id'],'lineage':lineage,'first_state':h,'sequence':seq}),
                        'lineage_id':lineage,'market_id':s['market_id'],'position_id':s['position_id'],'asset_pair':s['asset_pair'],
                        'left_censored':known_start,'birth':None if known_start else s['order'],
                        'first_actionable':s['order'],'first_executable':None,'execution_economics_ref':None,
                        'state_refs':[],'trigger_ids':[],'time_to_first_competitor_arrival_ms':None,
                        'competitor_arrival_observability':'NOT_OBSERVED','_birth_timestamp':ts,'_first_timestamp':ts}
                if not known_start and not s['trigger_ids']:
                    blockers.append({'code':'EVIDENCE_INSUFFICIENT','episode_id':active['episode_id'],'reason':'OBSERVED_BIRTH_HAS_NO_ADMITTED_CAUSAL_TRIGGER'})
            if active is not None:
                active['state_refs'].append(h); active['trigger_ids']+=s['trigger_ids']
                if a and s['execution_ref'] and active['first_executable'] is None:
                    active['first_executable']=s['order']; active['execution_economics_ref']=s['execution_ref']
                if s['terminal'] is not None:
                    p=store.get(s['terminal_evidence_ref'],'TERMINAL_EVENT_V1')
                    exact(p,('kind','scope_id','lineage_id','status','order','source_ref'),label='terminal event')
                    need(p['scope_id']==scope['scope_id'] and p['lineage_id']==lineage and p['status']==s['terminal'] and p['order']==s['order'],'terminal witness mismatch')
                    proof=store.get(p['source_ref'],'TERMINAL_SOURCE_V1')
                    exact(proof,('kind','scope_id','lineage_id','status','order','payload_ref'),label='terminal source')
                    need(all(proof[k]==p[k] for k in ('scope_id','lineage_id','status','order')),'terminal source identity mismatch')
                    store.get(proof['payload_ref']); no_future_evidence(store,s['terminal_evidence_ref'],s['order'])
                    finish(s['terminal'],row)
                elif not a: finish('RECOVERED' if s['state']['debt_units']==0 or s['state']['health_factor_wad']>=10**18 else 'EXPIRED',row)
            elif s['terminal'] is not None:
                raise Invalid('terminal outcome without an observed active episode')
            previous=row
        if active is not None:
            if rows[-1][0]!=point(w['end_order']):
                # An acquisition hole is not boundary censoring. Keep an explicit
                # partial episode with no invented terminal or duration.
                active.update(right_censored=False,terminal={'status':'EVIDENCE_INSUFFICIENT','order':None},lifetime_seconds=None,observed_duration_seconds=None)
                active.pop('_birth_timestamp',None); active.pop('_first_timestamp',None)
                active['state_refs']=sorted(set(active['state_refs'])); active['trigger_ids']=sorted(set(active['trigger_ids']))
                episodes.append(active); active=None
            else: finish('RIGHT_CENSORED')
    dispositions=[]; rejected=set()
    for d in doc['dispositions']:
        need(d['trigger_id'] not in rejected,'duplicate disposition'); need(d['trigger_id'] not in consumed,'trigger consumed and rejected')
        proven=rejection(store,d,byid,scope,w,set(doc['state_refs'])); rejected.add(d['trigger_id']); dispositions.append(d)
        if not proven: blockers.append({'code':d['category'],'trigger_id':d['trigger_id'],'reason':d['reason']})
    missing=set(byid)-set(consumed)-rejected
    for tid in sorted(missing): blockers.append({'code':'UNACCOUNTED_TRIGGER','trigger_id':tid})
    linked={t for e in episodes for t in e['trigger_ids']}
    for tid in sorted(set(consumed)-linked):
        blockers.append({'code':'TRIGGER_NOT_LINKED_TO_EPISODE_OR_REJECTION','trigger_id':tid})
    report={'schema':'nqc-temporal-local-report-v1','status':'LOCAL_PACKAGE_CANDIDATE_COMPLETE_NOT_CERTIFIED' if not blockers else 'LOCAL_PACKAGE_BLOCKED',
            'evidence_kind':doc['evidence_kind'],'terminal_authority':False,'real_market_census_closed':False,
            'chain_semantic_replay_certified':False,'independent_provider_identity_certified':False,
            'execution_economics_semantically_verified':False,
            'terminal_outcome_semantically_verified':False,
            'coverage_complete_for_supplied_scope':not blockers,'material_unknown_count':len(blockers),
            'blockers':sorted(blockers,key=canonical),'scope':scope,'window':w,'trigger_count':len(byid),
            'population_lineage_count':len(pop),'observed_population_lineage_count':len(lineages),
            'consumed_trigger_count':len(consumed),'disposition_count':len(dispositions),'episode_count':len(episodes),
            'observability_limited_competitor_arrival_count':len(episodes)}
    return {'report':report,'episodes':sorted(episodes,key=lambda e:e['episode_id']),
            'dispositions':sorted(dispositions,key=lambda d:d['trigger_id'])}


def build(source,evidence_root,out):
    need(not out.resolve().is_relative_to(Path(evidence_root).resolve()),'output must be outside immutable evidence root')
    raw=Path(source).read_bytes(); doc=decode(raw)
    need(type(doc) is dict,'source object required')
    existing=diagnose_existing(doc)
    if existing:
        out.mkdir(parents=False,exist_ok=False)
        existing['source_sha256']=sha(raw)
        (out/'blockers.json').write_bytes(canonical(existing)); return existing
    envelope(doc); store=Store(evidence_root,doc['evidence']); result=compile_bundle(doc,store)
    out.mkdir(parents=False,exist_ok=False); (out/'evidence').mkdir()
    (out/'raw-source.json').write_bytes(raw)
    for h,b in sorted(store.raw.items()): (out/'evidence'/h).write_bytes(b)
    for kind in ('episodes','dispositions'):
        (out/(kind+'.jsonl')).write_bytes(b''.join(canonical(r) for r in result[kind]))
    (out/'report.json').write_bytes(canonical(result['report']))
    files={p.relative_to(out).as_posix():{'sha256':sha(p.read_bytes()),'bytes':p.stat().st_size} for p in sorted(out.rglob('*')) if p.is_file()}
    manifest={'schema':'nqc-temporal-local-package-v1','evidence_kind':doc['evidence_kind'],'terminal_authority':False,
              'real_market_census_closed':False,'source_sha256':sha(raw),'files':files}
    (out/'manifest.json').write_bytes(canonical(manifest)); return result['report']


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--input',required=True,type=Path); p.add_argument('--evidence-root',required=True,type=Path); p.add_argument('--out',required=True,type=Path)
    a=p.parse_args()
    try: r=build(a.input,a.evidence_root,a.out)
    except (Invalid,OSError,KeyError,TypeError) as exc:
        print(json.dumps({'status':'INPUT_REJECTED','error':str(exc),'terminal_authority':False,'real_market_census_closed':False})); return 2
    print(json.dumps(r,sort_keys=True)); return 0 if r['status']=='LOCAL_PACKAGE_CANDIDATE_COMPLETE_NOT_CERTIFIED' else 2
if __name__=='__main__': raise SystemExit(main())
