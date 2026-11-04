"""Offline multi-platform program/policy review. No targeting or execution.

A record describes a human-reviewed policy snapshot. It does NOT authenticate
permission, fetch current rules, enrol a researcher or grant testing rights.
Only local review requests can be eligible; active actions are always blocked.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from urllib.parse import urlsplit

from .native_runtime import load_components
from .privacy import PrivateArgumentParser
from .safe_io import canonical, strict_json, read_artifact, write_new_bundle, MAX_BYTES

PLATFORMS = ('immunefi','hackenproof','sherlock','cantina','hackerone','bugcrowd','intigriti','yeswehack')
HOSTS = {
    'immunefi': {'immunefi.com'}, 'hackenproof': {'hackenproof.com'},
    'sherlock': {'sherlock.xyz','audits.sherlock.xyz'}, 'cantina': {'cantina.xyz'},
    'hackerone': {'hackerone.com'}, 'bugcrowd': {'bugcrowd.com','bugcrowd.com.au'},
    'intigriti': {'intigriti.com','app.intigriti.com'},
    'yeswehack': {'yeswehack.com','app.yeswehack.com'},
}
LOCAL_ACTIONS = ('review_source','review_evidence','review_model','draft_report')
SLUG = re.compile(r'[a-z0-9][a-z0-9_.-]{0,95}\Z')
HASH = re.compile(r'[a-f0-9]{64}\Z')
COMMIT = re.compile(r'[a-f0-9]{40}\Z')
REPO = re.compile(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z')
ADDRESS = re.compile(r'0x[a-fA-F0-9]{40}\Z')
MAX_PROGRAMS, MAX_ASSETS, MAX_REQUESTS, MAX_DOCUMENT_BYTES = 200, 128, 1000, 8_000_000
ROOT = Path(__file__).resolve().parent
FIXED_FILES = {'catalog.json','requests.json','decision.json','audit.json','REVIEW.md'}
CODE_FILES = ('program_registry.py','safe_io.py','native_runtime.py','privacy.py')


class RegistryError(ValueError):
    """Fixed diagnostic codes; no secret or private program content echoed."""


def need(ok: bool, code: str) -> None:
    if not ok:
        raise RegistryError(code)


def fields(obj: object, keys: set[str], code: str) -> None:
    need(type(obj) is dict and set(obj) == keys, code)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def identifier(value: object) -> str:
    need(type(value) is str and SLUG.fullmatch(value) is not None, 'INVALID_IDENTIFIER')
    return value


def hash_value(value: object) -> str:
    need(type(value) is str and HASH.fullmatch(value) is not None, 'INVALID_HASH')
    return value


def instant(value: object) -> datetime:
    need(type(value) is str and len(value) <= 40, 'INVALID_TIME')
    try:
        parsed = datetime.fromisoformat(value.replace('Z','+00:00'))
    except (ValueError,TypeError) as exc:
        raise RegistryError('INVALID_TIME') from exc
    need(parsed.tzinfo is not None and parsed.utcoffset() is not None, 'TIMEZONE_REQUIRED')
    return parsed.astimezone(timezone.utc)


def now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_time(value: str) -> str:
    return instant(value).isoformat()


def https_url(value: object) -> str:
    need(type(value) is str and 1 <= len(value) <= 1024 and value.isascii() and
         not any(ord(c) <= 32 for c in value) and '\\' not in value and '%' not in value, 'INVALID_URL')
    try:
        u=urlsplit(value)
        need(u.scheme=='https' and bool(u.hostname) and u.username is None and u.password is None and
             u.port in (None,443) and not u.query and not u.fragment, 'INVALID_URL')
    except ValueError as exc:
        raise RegistryError('INVALID_URL') from exc
    need('*' not in value and not any(p in ('.','..') for p in u.path.split('/')), 'AMBIGUOUS_URL')
    return value


def asset(value: object) -> dict:
    fields(value,{'type','identifier','revision','chain_id'},'ASSET_SCHEMA')
    kind, name, rev, chain=value['type'],value['identifier'],value['revision'],value['chain_id']
    need(type(kind) is str and kind in ('repository','contract','domain'), 'ASSET_TYPE')
    need(type(name) is str and len(name)<=256, 'ASSET_IDENTIFIER')
    if kind=='repository':
        need(REPO.fullmatch(name) is not None and type(rev) is str and COMMIT.fullmatch(rev) is not None
             and chain is None, 'REPOSITORY_IDENTITY')
    elif kind=='contract':
        need(ADDRESS.fullmatch(name) is not None and type(chain) is int and 0<chain<2**64 and
             type(rev) is str and re.fullmatch(r'0x[a-f0-9]{64}',rev) is not None, 'CONTRACT_IDENTITY')
        name=name.lower()
    else:
        need(name.isascii() and name==name.lower() and
             re.fullmatch(r'(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}',name)
             is not None and rev is None and chain is None, 'EXACT_DOMAIN_REQUIRED')
    return {'type':kind,'identifier':name,'revision':rev,'chain_id':chain}


def asset_key(value: dict) -> bytes:
    return canonical(asset(value))


def record_key(record: dict) -> str:
    return record['platform']+':'+record['program_id']


def policy_digest(record: dict) -> str:
    """Binds review to all normalized declarations and evidence hashes, not to a name."""
    return digest(canonical({k:v for k,v in record.items() if k!='review'}))


def validate_catalog(value: object) -> dict:
    fields(value,{'schema_version','programs'},'CATALOG_SCHEMA')
    need(type(value['schema_version']) is int and value['schema_version']==1, 'CATALOG_VERSION')
    rows=value['programs']
    need(type(rows) is list and 0<=len(rows)<=MAX_PROGRAMS, 'PROGRAM_LIMIT')
    seen=set(); paths=set()
    for p in rows:
        fields(p,{'platform','program_id','program_url','mode','status','visibility','participation',
                  'window','policy','scope','local_actions','local_automation','external_ai','review'},'PROGRAM_SCHEMA')
        need(type(p['platform']) is str and p['platform'] in PLATFORMS, 'PLATFORM_UNSUPPORTED')
        identifier(p['program_id']);key=record_key(p)
        need(key not in seen,'DUPLICATE_PROGRAM');seen.add(key)
        u=urlsplit(https_url(p['program_url']))
        need(u.hostname in HOSTS[p['platform']], 'PLATFORM_URL_MISMATCH')
        need(p['mode'] in ('bounty','contest','vdp') and p['status'] in ('active','paused','closed')
             and p['visibility'] in ('public','private'), 'PROGRAM_ENUM')
        fields(p['participation'],{'enrolled','invitation_confirmed'},'PARTICIPATION_SCHEMA')
        need(all(type(v) is bool for v in p['participation'].values()),'PARTICIPATION_BOOLEAN')
        fields(p['window'],{'starts_at','ends_at'},'WINDOW_SCHEMA')
        start=instant(p['window']['starts_at'])
        end=instant(p['window']['ends_at']) if p['window']['ends_at'] is not None else None
        need(end is None or end>start,'WINDOW_ORDER')
        need(p['mode']!='contest' or end is not None,'CONTEST_DEADLINE_REQUIRED')
        pol=p['policy'];fields(pol,{'file','sha256','retrieved_at','review_until'},'POLICY_SCHEMA')
        path=pol['file'];need(type(path) is str and len(path)<=256,'POLICY_PATH')
        pure=PurePosixPath(path)
        need(not pure.is_absolute() and all(x not in ('','.','..') for x in path.split('/')) and
             '\\' not in path and ':' not in path and pure.suffix in ('.md','.txt','.json'),'POLICY_PATH')
        hash_value(pol['sha256']);retrieved=instant(pol['retrieved_at']);until=instant(pol['review_until'])
        need(retrieved<until<=retrieved+timedelta(days=30),'POLICY_REVIEW_WINDOW')
        paths.add(path)
        need(type(p['scope']) is list and len(p['scope'])<=MAX_ASSETS,'SCOPE_LIMIT')
        scope_seen=set()
        for row in p['scope']:
            fields(row,{'asset','effect','bounty_eligible','severity_label'},'SCOPE_SCHEMA')
            k=asset_key(row['asset']);need(row['effect'] in ('include','exclude'),'SCOPE_EFFECT')
            need((k,row['effect']) not in scope_seen,'DUPLICATE_SCOPE');scope_seen.add((k,row['effect']))
            need(row['bounty_eligible'] is None or type(row['bounty_eligible']) is bool,'BOUNTY_BOOLEAN')
            need(row['severity_label'] is None or (type(row['severity_label']) is str and
                 1<=len(row['severity_label'])<=64),'SEVERITY_LABEL')
        acts=p['local_actions'];need(type(acts) is list and len(acts)<=len(LOCAL_ACTIONS) and
             all(type(a) is str and a in LOCAL_ACTIONS for a in acts) and len(set(acts))==len(acts),'LOCAL_ACTIONS')
        need(p['local_automation'] in ('allowed','denied','unknown') and
             p['external_ai'] in ('allowed','denied','unknown'),'RESTRICTION_ENUM')
        r=p['review'];fields(r,{'state','reviewer','at','normalized_sha256'},'REVIEW_SCHEMA')
        need(r['state'] in ('pending','approved','rejected'),'REVIEW_STATE')
        if r['state']=='pending':
            need(r['reviewer'] is None and r['at'] is None and r['normalized_sha256'] is None,'PENDING_REVIEW_FIELDS')
        else:
            identifier(r['reviewer']);instant(r['at']);hash_value(r['normalized_sha256'])
    need(len(paths)<=MAX_PROGRAMS,'DOCUMENT_LIMIT')
    return deepcopy(value)


def validate_requests(value: object) -> dict:
    fields(value,{'schema_version','requests'},'REQUESTS_SCHEMA')
    need(type(value['schema_version']) is int and value['schema_version']==1,'REQUESTS_VERSION')
    rows=value['requests'];need(type(rows) is list and len(rows)<=MAX_REQUESTS,'REQUEST_LIMIT')
    seen=set()
    for q in rows:
        fields(q,{'id','platform','program_id','asset','action','expected_policy_sha256','uses_external_ai'},'REQUEST_SCHEMA')
        identifier(q['id']);need(q['id'] not in seen,'DUPLICATE_REQUEST');seen.add(q['id'])
        need(type(q['platform']) is str and q['platform'] in PLATFORMS,'PLATFORM_UNSUPPORTED')
        identifier(q['program_id']);asset(q['asset']);identifier(q['action']);hash_value(q['expected_policy_sha256'])
        need(type(q['uses_external_ai']) is bool,'EXTERNAL_AI_BOOLEAN')
    return deepcopy(value)


def capture_documents(catalog: dict, evidence_root: Path) -> dict[str,bytes]:
    docs={};total=0
    for p in catalog['programs']:
        path=p['policy']['file']
        if path in docs:continue
        raw=read_artifact(evidence_root,path);total+=len(raw)
        need(0<len(raw)<=MAX_BYTES and total<=MAX_DOCUMENT_BYTES,'POLICY_BYTES_LIMIT')
        docs[path]=raw
    return docs


def validate_documents(catalog: dict, docs: dict) -> None:
    expected={p['policy']['file'] for p in catalog['programs']}
    need(type(docs) is dict and set(docs)==expected,'DOCUMENT_SET')
    need(all(type(v) is bytes and 0<len(v)<=MAX_BYTES for v in docs.values()) and
         sum(len(v) for v in docs.values())<=MAX_DOCUMENT_BYTES,'POLICY_BYTES_LIMIT')
    for p in catalog['programs']:
        need(digest(docs[p['policy']['file']])==p['policy']['sha256'],'POLICY_HASH_MISMATCH')


def _decision(p: dict|None, q: dict, at: datetime) -> dict:
    reasons=[]; required=[];matches=[]
    if p is None:
        reasons.append('UNKNOWN_PROGRAM')
    else:
        if p['status']!='active':reasons.append('PROGRAM_NOT_ACTIVE')
        if not p['participation']['enrolled']:required.append('PARTICIPATION_NOT_REVIEWED')
        if p['visibility']=='private' and not p['participation']['invitation_confirmed']:
            required.append('PRIVATE_INVITATION_NOT_REVIEWED')
        if at<instant(p['window']['starts_at']):reasons.append('WINDOW_NOT_STARTED')
        if p['window']['ends_at'] is not None and at>=instant(p['window']['ends_at']):reasons.append('WINDOW_ENDED')
        pol=p['policy'];review=p['review']
        if at<instant(pol['retrieved_at']):reasons.append('POLICY_FROM_FUTURE')
        if at>=instant(pol['review_until']):reasons.append('POLICY_REVIEW_EXPIRED')
        if q['expected_policy_sha256']!=policy_digest(p):reasons.append('POLICY_CHANGED')
        if review['state']=='rejected':reasons.append('REVIEW_REJECTED')
        elif review['state']!='approved':required.append('HUMAN_REVIEW_REQUIRED')
        else:
            if review['normalized_sha256']!=policy_digest(p):reasons.append('REVIEW_NOT_BOUND_TO_POLICY')
            if not instant(pol['retrieved_at'])<=instant(review['at'])<=at:reasons.append('REVIEW_TIME_INVALID')
        for row in p['scope']:
            if asset_key(row['asset'])==asset_key(q['asset']):matches.append(row)
        if any(r['effect']=='exclude' for r in matches):reasons.append('EXCLUDED_ASSET')
        if not any(r['effect']=='include' for r in matches):reasons.append('ASSET_NOT_EXPLICITLY_INCLUDED')
        if q['action'] not in p['local_actions']:reasons.append('ACTION_NOT_IN_POLICY')
        if p['local_automation']=='denied':reasons.append('AUTOMATION_DENIED')
        elif p['local_automation']!='allowed':required.append('AUTOMATION_UNSPECIFIED')
        if q['uses_external_ai']:
            # This local registry never sends private data to a model provider.
            # Even an affirmative declaration is not a configured data-sharing permission.
            reasons.append('EXTERNAL_AI_TRANSMISSION_NOT_IMPLEMENTED')
    if q['action'] not in LOCAL_ACTIONS:reasons.append('ACTIVE_OR_UNSUPPORTED_ACTION')
    includes=[r for r in matches if r['effect']=='include']
    return {'request_id':q['id'],'program_key':q['platform']+':'+q['program_id'],
            'status':'BLOCKED' if reasons else 'REVIEW_REQUIRED' if required else 'LOCAL_REVIEW_ELIGIBLE',
            'reasons':sorted(set(reasons+required)),
            'bounty_eligible_declared':includes[0]['bounty_eligible'] if len(includes)==1 else None,
            'severity_label_as_declared':includes[0]['severity_label'] if len(includes)==1 else None,
            'permission_authenticated':False,'live_scope_verified':False,'execution_authorized':False,
            'reward_guaranteed':False,'action_executed':False}


def evaluate(catalog: object, requests: object, docs: dict, at: str) -> dict:
    cat,req=validate_catalog(catalog),validate_requests(requests);validate_documents(cat,docs)
    stamp=instant(at);by_key={record_key(p):p for p in cat['programs']}
    rows=[_decision(by_key.get(q['platform']+':'+q['program_id']),q,stamp) for q in req['requests']]
    return {'schema_version':1,'status':'PROGRAM_POLICIES_REVIEWED','evaluated_at':stamp.isoformat(),
            'catalog_sha256':digest(canonical(cat)),'requests_sha256':digest(canonical(req)),
            'program_count':len(cat['programs']),'platform_counts':dict(sorted(Counter(p['platform'] for p in cat['programs']).items())),
            'decision_counts':dict(sorted(Counter(r['status'] for r in rows).items())), 'decisions':rows,
            'documents_sha256':{k:digest(v) for k,v in sorted(docs.items())},
            'accounts_connected':0,'live_scope_verified':False,'automatic_submission':False,
            'actions_executed':0,'vulnerability_confirmed':False,
            'limitations':['Local snapshot and explicit human declarations only; not external permission authentication.',
                           'Snapshot may be stale before its review deadline; inspect the official program before research.',
                           'Exact assets only; wildcards and unstated rules never expand scope.',
                           'Eligibility is for local review of supplied material, not permission to test services.']}


def render(result: dict) -> bytes:
    # Never repeat program names, private URLs, raw scope, descriptions or policy clauses.
    return ('# Revisión local de políticas multiplataforma\n\n'
            f"Programas declarados: {result['program_count']}. Evaluado: {result['evaluated_at']}.\n"
            f"Decisiones: {json.dumps(result['decision_counts'],sort_keys=True)}.\n\n"
            'No se conectaron cuentas ni se ejecutaron solicitudes contra objetivos.\n'
            'La elegibilidad local no autentica permisos, alcance actual ni recompensas.\n'
            'Los originales del paquete son privados y no deben publicarse.\n').encode()


def code_identity() -> dict:
    return {name:digest(read_artifact(ROOT,name)) for name in CODE_FILES}


def _audit(result: dict) -> dict:
    log=load_components().audit.AuditLog()
    log.append('programs.review.start',{'catalog_sha256':result['catalog_sha256'],
                                      'requests_sha256':result['requests_sha256'],'at':result['evaluated_at']})
    for row in result['decisions']:
        log.append('programs.review.decision',{'decision_sha256':digest(canonical(row))})
    log.append('programs.review.finish',{'result_sha256':digest(canonical(result))})
    log.assert_intact()
    return {'entries':[asdict(e) for e in log.entries],'head':log.head,'code_sha256':code_identity()}


def _verify_audit(data: dict, result: dict) -> None:
    fields(data,{'entries','head','code_sha256'},'AUDIT_SCHEMA')
    need(data['code_sha256']==code_identity(),'AUDIT_CODE_CHANGED')
    events=[('programs.review.start',{'catalog_sha256':result['catalog_sha256'],
                                    'requests_sha256':result['requests_sha256'],'at':result['evaluated_at']})]
    events += [('programs.review.decision',{'decision_sha256':digest(canonical(row))}) for row in result['decisions']]
    events += [('programs.review.finish',{'result_sha256':digest(canonical(result))})]
    entries=data['entries'];need(type(entries) is list and len(entries)==len(events),'AUDIT_LENGTH')
    prev='0'*64;last=None;native=load_components()
    for i,(row,(event,payload)) in enumerate(zip(entries,events)):
        fields(row,{'index','timestamp','event','data','prev_hash','hash'},'AUDIT_ENTRY')
        need(type(row['index']) is int and row['index']==i,'AUDIT_INDEX')
        need(row['event']==event and canonical(row['data'])==canonical(payload),'AUDIT_EVENT_MISMATCH')
        time=instant(row['timestamp']);need(last is None or time>=last,'AUDIT_TIME_ORDER');last=time
        need(row['prev_hash']==prev and native.audit.compute_hash(i,row['timestamp'],event,payload,prev)==row['hash'], 'AUDIT_HASH')
        prev=row['hash']
    need(data['head']==prev,'AUDIT_HEAD')


def create(catalog_path: Path, requests_path: Path, evidence_root: Path, out: Path, *, at: str|None=None) -> dict:
    need(not out.exists() and not out.is_symlink(),'OUTPUT_EXISTS')
    need(not out.resolve().is_relative_to(ROOT.parent) and
         not out.resolve().is_relative_to(evidence_root.resolve()),'OUTPUT_LOCATION')
    cat_raw=read_artifact(catalog_path.parent,catalog_path.name); req_raw=read_artifact(requests_path.parent,requests_path.name)
    cat=validate_catalog(strict_json(cat_raw));req=validate_requests(strict_json(req_raw));docs=capture_documents(cat,evidence_root)
    result=evaluate(cat,req,docs,at or now_text())
    files={'catalog.json':cat_raw,'requests.json':req_raw,'decision.json':canonical(result),
           'audit.json':canonical(_audit(result)),'REVIEW.md':render(result)}
    for i,path in enumerate(sorted(docs)):files[f'policy-{i:03d}.txt']=docs[path]
    write_new_bundle(out,files)
    # Historical replay uses the same instant; ordinary verify() also assesses the current instant.
    verify(out,at=result['evaluated_at'])
    return result


def verify(root: Path, *, at: str|None=None) -> dict:
    marker=strict_json(read_artifact(root,'COMPLETE.json'))
    fields(marker,{'schema_version','sha256'},'BUNDLE_SCHEMA')
    need(type(marker['schema_version']) is int and marker['schema_version']==1 and type(marker['sha256']) is dict,'BUNDLE_VERSION')
    cat=validate_catalog(strict_json(read_artifact(root,'catalog.json')))
    paths=sorted({p['policy']['file'] for p in cat['programs']})
    expected=FIXED_FILES|{f'policy-{i:03d}.txt' for i in range(len(paths))}
    need(set(marker['sha256'])==expected and {p.name for p in root.iterdir()}==expected|{'COMPLETE.json'},'BUNDLE_FILE_SET')
    files={};total=0
    for name in sorted(expected):
        raw=read_artifact(root,name);total+=len(raw)
        need(total<=MAX_DOCUMENT_BYTES+5*MAX_BYTES,'BUNDLE_TOTAL_LIMIT')
        need(digest(raw)==marker['sha256'][name],'BUNDLE_HASH');files[name]=raw
    need(canonical(cat)==canonical(strict_json(files['catalog.json'])),'CATALOG_CHANGED')
    req=validate_requests(strict_json(files['requests.json']));old=strict_json(files['decision.json'])
    docs={path:files[f'policy-{i:03d}.txt'] for i,path in enumerate(paths)}
    result=evaluate(cat,req,docs,old['evaluated_at'])
    need(canonical(result)==files['decision.json'] and render(result)==files['REVIEW.md'],'RECOMPUTED_RESULT_MISMATCH')
    _verify_audit(strict_json(files['audit.json']),result)
    current=evaluate(cat,req,docs,at or now_text())
    return {'status':'PROGRAM_POLICY_REPLAY_PASS','historical':result,'current':current,
            'permission_authenticated':False,'current_rules_fetched':False}


def example_catalog() -> tuple[dict,dict,dict]:
    """Explicit own synthetic fixtures, NOT accounts, enrolments or live programs."""
    asset_value={'type':'repository','identifier':'local/demo','revision':'1'*40,'chain_id':None}
    cat={'schema_version':1,'programs':[]};docs={};requests={'schema_version':1,'requests':[]}
    for i,platform in enumerate(PLATFORMS):
        path=f'{platform}.txt';docs[path]=f'SYNTHETIC LOCAL POLICY ONLY {platform}; never a live authorization.'.encode()
        p={'platform':platform,'program_id':'local-demo','program_url':f'https://{sorted(HOSTS[platform])[0]}/local-demo',
           'mode':'bounty','status':'active','visibility':'public','participation':{'enrolled':True,'invitation_confirmed':False},
           'window':{'starts_at':'2026-11-01T00:00:00Z','ends_at':None},
           'policy':{'file':path,'sha256':digest(docs[path]),'retrieved_at':'2026-11-04T00:00:00Z','review_until':'2026-11-05T00:00:00Z'},
           'scope':[{'asset':deepcopy(asset_value),'effect':'include','bounty_eligible':None,'severity_label':None}],
           'local_actions':list(LOCAL_ACTIONS),'local_automation':'allowed','external_ai':'unknown',
           'review':{'state':'approved','reviewer':'local-fixture','at':'2026-11-04T01:00:00Z','normalized_sha256':None}}
        p['review']['normalized_sha256']=policy_digest(p);cat['programs'].append(p)
        requests['requests'].append({'id':f'demo-{i}','platform':platform,'program_id':'local-demo','asset':deepcopy(asset_value),
                                     'action':'review_source','expected_policy_sha256':policy_digest(p),'uses_external_ai':False})
    return cat,requests,docs


def main(argv: list[str]) -> int:
    parser=PrivateArgumentParser(description='Review supplied program policies offline; no active testing or accounts')
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('review-programs')
    for name in ('catalog','requests','evidence-root','out'):p.add_argument('--'+name,required=True,type=Path)
    p.add_argument('--at')
    v=sub.add_parser('verify-programs');v.add_argument('--bundle',type=Path,required=True);v.add_argument('--at')
    a=parser.parse_args(argv)
    try:
        if a.command=='review-programs':r=create(a.catalog,a.requests,a.evidence_root,a.out,at=a.at)
        else:r=verify(a.bundle,at=a.at)['current']
        print(json.dumps({'status':r['status'],'program_count':r['program_count'],'decision_counts':r['decision_counts'],
                          'accounts_connected':0,'actions_executed':0,'permission_authenticated':False}))
        return 0 if r['decisions'] and all(x['status']=='LOCAL_REVIEW_ELIGIBLE' for x in r['decisions']) else 1
    except (ValueError,OSError,KeyError,TypeError,RecursionError,OverflowError):
        print(json.dumps({'status':'PROGRAM_POLICY_ERROR','actions_executed':0,'permission_authenticated':False}))
        return 2


if __name__=='__main__':
    import sys
    raise SystemExit(main(sys.argv[1:]))
