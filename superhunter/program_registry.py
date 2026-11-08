"""Versioned, offline multi-platform policy registry; no scanners or API clients.

Reviews are local attestations, not signatures or proof of legal authorization.
Exact-match scope only. An eligible snapshot never permits network execution.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from .native_runtime import load_components
from .source_graph import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

PLATFORMS = ('immunefi', 'hackenproof', 'sherlock', 'cantina', 'hackerone',
             'bugcrowd', 'intigriti', 'yeswehack')
MAX_PROGRAMS, MAX_ASSETS, MAX_REQUESTS = 100, 2000, 256
ROOT = Path(__file__).resolve().parent
ID = re.compile(r'[a-z0-9][a-z0-9_.-]{0,95}\Z')
SHA256 = re.compile(r'[0-9a-f]{64}\Z')
COMMIT = re.compile(r'[0-9a-f]{40}\Z')
REPO = re.compile(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z')
ADDRESS = re.compile(r'0x[0-9a-fA-F]{40}\Z')
HOST = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z')
FIXED = {'registry.json', 'requests.json', 'decision.json', 'audit.json', 'REVIEW.md'}
PROGRAM_FIELDS = {'platform','program_id','scope_id','kind','visibility','status',
                  'participation','offline_automation','disclosure','policy','assets','approval'}
CODE_FILES = ('program_registry.py','safe_io.py','native_runtime.py','source_graph.py')


class RegistryError(ValueError):
    """Fixed error codes only; never expose supplied policy text or credentials."""


def need(condition: bool, code: str) -> None:
    if not condition:
        raise RegistryError(code)


def fields(obj: object, names: set[str], code: str) -> None:
    need(type(obj) is dict and set(obj) == names, code)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def ident(value: object) -> None:
    need(type(value) is str and ID.fullmatch(value) is not None, 'IDENTIFIER')


def timestamp(value: object) -> datetime:
    need(type(value) is str and len(value) <= 40, 'TIMESTAMP')
    try:
        result = datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError as exc:
        raise RegistryError('TIMESTAMP') from exc
    need(result.tzinfo is not None and 'T' in value, 'TIMEZONE_REQUIRED')
    return result.astimezone(timezone.utc)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def asset(value: object, *, rule: bool = False) -> dict:
    names = {'kind','locator','commit','chain_id'} | ({'id','effect'} if rule else set())
    fields(value,names,'ASSET_SCHEMA')
    v = deepcopy(value)
    if rule:
        ident(v['id']);need(v['effect'] in ('include','exclude'),'ASSET_EFFECT')
    kind, loc, commit, chain = (v[k] for k in ('kind','locator','commit','chain_id'))
    need(type(loc) is str and 0 < len(loc) <= 512,'ASSET_LOCATOR')
    if kind == 'repository':
        need(REPO.fullmatch(loc) is not None and all(p not in ('.','..') for p in loc.split('/')),'REPOSITORY')
        need(type(commit) is str and COMMIT.fullmatch(commit) is not None and chain is None,'REPOSITORY_REVISION')
    elif kind == 'contract':
        need(ADDRESS.fullmatch(loc) is not None and commit is None,'CONTRACT')
        need(type(chain) is int and 0 < chain < 2**64,'CHAIN_ID')
        v['locator'] = loc.lower()
    elif kind == 'hostname':
        need(loc == loc.lower() and len(loc) <= 253 and all(HOST.fullmatch(p) for p in loc.split('.'))
             and '.' in loc and commit is None and chain is None,'HOSTNAME_EXACT_ONLY')
    else:
        raise RegistryError('ASSET_KIND')
    return v


def program_key(p: dict) -> str:
    return p['platform'] + ':' + p['program_id']


def binding(p: dict) -> str:
    """Bind a local review to ALL declared program rules, not just policy bytes."""
    return sha(canonical({k:v for k,v in p.items() if k != 'approval'}))


def validate_registry(raw: object) -> dict:
    fields(raw,{'schema_version','programs'},'REGISTRY_SCHEMA')
    need(type(raw['schema_version']) is int and raw['schema_version']==1,'VERSION')
    need(type(raw['programs']) is list and 1 <= len(raw['programs']) <= MAX_PROGRAMS,'PROGRAM_LIMIT')
    data=deepcopy(raw);keys=set();scopes=set();asset_count=0
    for p in data['programs']:
        fields(p,PROGRAM_FIELDS,'PROGRAM_SCHEMA')
        need(type(p['platform']) is str and p['platform'] in PLATFORMS,'PLATFORM')
        ident(p['program_id']);ident(p['scope_id'])
        key=program_key(p)
        need(key not in keys and p['scope_id'] not in scopes,'DUPLICATE_PROGRAM_OR_SCOPE')
        keys.add(key);scopes.add(p['scope_id'])
        for k,options in (
            ('kind',('bounty','contest','vdp')),('visibility',('public','private')),
            ('status',('active','paused','closed')),('participation',('confirmed','unknown','declined')),
            ('offline_automation',('allowed','forbidden','unknown')),('disclosure',('private','coordinated','public'))):
            need(type(p[k]) is str and p[k] in options,'PROGRAM_ENUM')
        policy=p['policy']
        fields(policy,{'version','source_url','captured_at','valid_until','evidence_file','sha256'},'POLICY_SCHEMA')
        ident(policy['version'])
        need(type(policy['source_url']) is str and len(policy['source_url']) <= 2048,'POLICY_URL')
        try:
            url=urlsplit(policy['source_url'])
            valid=(url.scheme=='https' and bool(url.hostname) and url.username is None and
                   url.password is None and not url.query and not url.fragment and
                   not any(c.isspace() for c in policy['source_url']) and url.port in (None,443))
        except ValueError:
            valid=False
        need(valid,'POLICY_URL')
        start,end=timestamp(policy['captured_at']),timestamp(policy['valid_until'])
        need(start < end,'POLICY_INTERVAL')
        path=policy['evidence_file']
        need(type(path) is str and len(path)<=512 and not path.startswith('/') and
             '\\' not in path and ':' not in path and
             all(c not in ('','.','..') for c in path.split('/')),'EVIDENCE_PATH')
        need(type(policy['sha256']) is str and SHA256.fullmatch(policy['sha256']) is not None,'POLICY_HASH')
        need(type(p['assets']) is list and 1 <= len(p['assets']) <= 500,'ASSET_LIMIT')
        asset_count+=len(p['assets']);need(asset_count<=MAX_ASSETS,'TOTAL_ASSET_LIMIT')
        rule_ids=set()
        for a in p['assets']:
            normalized=asset(a,rule=True)
            # Require canonical contract addresses so approval bindings are unambiguous.
            need(a==normalized,'NONCANONICAL_ASSET')
            need(a['id'] not in rule_ids,'DUPLICATE_RULE');rule_ids.add(a['id'])
        approval=p['approval']
        fields(approval,{'state','reviewer','reviewed_at','snapshot_sha256'},'APPROVAL_SCHEMA')
        need(approval['state'] in ('pending','approved','rejected'),'APPROVAL_STATE')
        if approval['state']=='pending':
            need(all(approval[k] is None for k in ('reviewer','reviewed_at','snapshot_sha256')),'PENDING_REVIEW_FIELDS')
        else:
            ident(approval['reviewer'])
            reviewed=timestamp(approval['reviewed_at'])
            need(start <= reviewed < end,'REVIEW_INTERVAL')
            need(type(approval['snapshot_sha256']) is str and SHA256.fullmatch(approval['snapshot_sha256']) is not None,'APPROVAL_HASH')
            # A stale approval is accepted as input but never as eligibility.
    return data


def validate_requests(value: object) -> dict:
    fields(value,{'schema_version','requests'},'REQUESTS_SCHEMA')
    need(type(value['schema_version']) is int and value['schema_version']==1,'VERSION')
    need(type(value['requests']) is list and 1 <= len(value['requests']) <= MAX_REQUESTS,'REQUEST_LIMIT')
    out=deepcopy(value);seen=set()
    for r in out['requests']:
        fields(r,{'id','program_key','scope_id','action','asset'},'REQUEST_SCHEMA');ident(r['id']);ident(r['scope_id'])
        need(r['id'] not in seen,'DUPLICATE_REQUEST');seen.add(r['id'])
        need(type(r['program_key']) is str and r['program_key'].count(':')==1,'PROGRAM_KEY')
        platform,key=r['program_key'].split(':');ident(platform);ident(key)
        need(type(r['action']) is str and r['action'] in
             ('offline_review','network_scan','broadcast','submit_report'),'ACTION')
        r['asset']=asset(r['asset'])
    return out


def validate_evidence(registry: dict, evidence: dict[str,bytes]) -> None:
    need(type(evidence) is dict and set(evidence)=={program_key(p) for p in registry['programs']},'EVIDENCE_SET')
    need(all(type(b) is bytes and 0 < len(b)<=2_000_000 for b in evidence.values()),'EVIDENCE_SIZE')
    need(sum(map(len,evidence.values()))<=8_000_000,'EVIDENCE_TOTAL')
    for p in registry['programs']:
        need(sha(evidence[program_key(p)])==p['policy']['sha256'],'POLICY_BYTES_MISMATCH')


def evaluate(registry: object, requests: object, evidence: dict[str,bytes], *, at: str) -> dict:
    """Evaluate a declared, cached policy. Does NOT authorize or execute a test."""
    registry=validate_registry(registry);requests=validate_requests(requests)
    validate_evidence(registry,evidence);now=timestamp(at)
    programs={program_key(p):p for p in registry['programs']};decisions=[]
    for r in requests['requests']:
        deny=[];review=[];matched=[];p=programs.get(r['program_key']);pin=None
        if r['action']!='offline_review':deny.append('ACTION_NOT_SUPPORTED')
        if p is None:
            deny.append('PROGRAM_NOT_REGISTERED')
        else:
            pin=binding(p);policy=p['policy'];approval=p['approval']
            if r['scope_id']!=p['scope_id']:deny.append('SCOPE_ID_MISMATCH')
            if p['status']!='active':deny.append('PROGRAM_INACTIVE')
            if now<timestamp(policy['captured_at']):review.append('SNAPSHOT_IN_FUTURE')
            if now>=timestamp(policy['valid_until']):review.append('SNAPSHOT_EXPIRED')
            if p['participation']=='declined':deny.append('PARTICIPATION_DECLINED')
            elif p['participation']=='unknown':review.append('PARTICIPATION_UNCONFIRMED')
            if p['offline_automation']=='forbidden':deny.append('OFFLINE_AUTOMATION_FORBIDDEN')
            elif p['offline_automation']=='unknown':review.append('AUTOMATION_UNSPECIFIED')
            if approval['state']=='rejected':deny.append('REVIEW_REJECTED')
            elif approval['state']=='pending':review.append('REVIEW_PENDING')
            else:
                if approval['snapshot_sha256']!=pin:review.append('REVIEW_BINDING_STALE')
                if timestamp(approval['reviewed_at'])>now:review.append('REVIEW_IN_FUTURE')
            for a in p['assets']:
                if {k:a[k] for k in r['asset']}==r['asset']:matched.append(a)
            if any(a['effect']=='exclude' for a in matched):deny.append('EXCLUSION_WINS')
            elif not any(a['effect']=='include' for a in matched):deny.append('ASSET_NOT_EXPLICITLY_INCLUDED')
        verdict='LOCAL_SCOPE_DENIED' if deny else 'LOCAL_SCOPE_REVIEW_REQUIRED' if review else 'LOCAL_SCOPE_ELIGIBLE'
        decisions.append({'request_id':r['id'],'program_key':r['program_key'],'snapshot_sha256':pin,
                          'status':verdict,'deny_reasons':deny,'review_reasons':review,
                          'matched_rules':[a['id'] for a in matched],
                          'platform_authorization_verified':False,'network_execution_allowed':False,
                          'human_review_required':True})
    return {'schema_version':1,'status':'PROGRAM_POLICY_REVIEW','evaluated_at':now.isoformat(),
            'registry_sha256':sha(canonical(registry)),'requests_sha256':sha(canonical(requests)),
            'program_count':len(programs),'platforms':sorted({p['platform'] for p in programs.values()}),
            'decisions':decisions,'counts':dict(sorted(Counter(d['status'] for d in decisions).items())),
            'policy_fetch_performed':False,'platform_connectors_active':0,
            'snapshot_authenticity_verified':False,'vulnerability_confirmed':False}


def changes(before: object, after: object) -> dict:
    """Read-only change detection; never silently renew a previous approval."""
    a={program_key(p):p for p in validate_registry(before)['programs']}
    b={program_key(p):p for p in validate_registry(after)['programs']}
    changed=[]
    for key in sorted(a.keys() & b.keys()):
        if binding(a[key])!=binding(b[key]):
            changed.append({'program_key':key,'before_sha256':binding(a[key]),'after_sha256':binding(b[key]),
                            'changed_fields':sorted(k for k in PROGRAM_FIELDS-{'approval'}
                                                    if canonical(a[key][k])!=canonical(b[key][k])),
                            'requires_new_review':True})
    return {'added':sorted(b.keys()-a.keys()),'removed':sorted(a.keys()-b.keys()),'changed':changed}


def requests_for_candidate(value: object, *, platform: str, program_id: str, chain_id: int) -> dict:
    """Bridge existing Candidate metadata to explicit policy checks; never run its PoC.

    The caller must supply the chain: Candidate v1 has no chain_id. No chain is
    inferred from an address or fork block. Every affected contract must match.
    """
    from .bridge import candidate
    c=candidate(value)
    need(type(platform) is str and platform in PLATFORMS,'PLATFORM');ident(program_id)
    need(type(chain_id) is int and 0 < chain_id < 2**64,'CHAIN_ID')
    common={'program_key':platform+':'+program_id,'scope_id':c['scope_id'],'action':'offline_review'}
    base_id='c-'+c['id'].lower()
    rows=[{**common,'id':base_id+'-repo','asset':{'kind':'repository','locator':c['target']['repo'],
                'commit':c['target']['commit'].lower(),'chain_id':None}}]
    rows += [{**common,'id':base_id+'-'+str(i),'asset':{'kind':'contract','locator':address.lower(),
                  'commit':None,'chain_id':chain_id}} for i,address in enumerate(c['affected_contracts'])]
    return validate_requests({'schema_version':1,'requests':rows})


def code_identity() -> dict:
    return {p:sha(read_artifact(ROOT,p)) for p in CODE_FILES}


def _audit(result: dict) -> dict:
    native=load_components();audit=native.audit.AuditLog()
    audit.append('programs.review.start',{'registry_sha256':result['registry_sha256'],
                                        'requests_sha256':result['requests_sha256'],
                                        'evaluated_at':result['evaluated_at']})
    for d in result['decisions']:
        audit.append('programs.review.decision',{'decision_sha256':sha(canonical(d))})
    audit.append('programs.review.complete',{'result_sha256':sha(canonical(result))})
    audit.assert_intact()
    return {'entries':[asdict(e) for e in audit.entries],'head':audit.head,
            'code_sha256':code_identity(),'native_sources':list(native.provenance)}


def _verify_audit(value: dict, result: dict) -> None:
    fields(value,{'entries','head','code_sha256','native_sources'},'AUDIT_SCHEMA')
    native=load_components()
    need(value['code_sha256']==code_identity() and value['native_sources']==list(native.provenance),'CODE_CHANGED')
    expected=[('programs.review.start',{'registry_sha256':result['registry_sha256'],
                 'requests_sha256':result['requests_sha256'],'evaluated_at':result['evaluated_at']})]
    expected += [('programs.review.decision',{'decision_sha256':sha(canonical(d))}) for d in result['decisions']]
    expected += [('programs.review.complete',{'result_sha256':sha(canonical(result))})]
    entries=value['entries'];need(type(entries) is list and len(entries)==len(expected),'AUDIT_COVERAGE')
    prev='0'*64;last=None
    for i,(row,(event,data)) in enumerate(zip(entries,expected)):
        fields(row,{'index','timestamp','event','data','prev_hash','hash'},'AUDIT_ENTRY')
        need(type(row['index']) is int and row['index']==i and row['prev_hash']==prev,'AUDIT_CHAIN')
        need(row['event']==event and canonical(row['data'])==canonical(data),'AUDIT_SEMANTICS')
        moment=timestamp(row['timestamp']);need(last is None or moment>=last,'AUDIT_TIME');last=moment
        need(native.audit.AuditEntry(**row).recompute()==row['hash'],'AUDIT_HASH');prev=row['hash']
    need(prev==value['head'],'AUDIT_HEAD')


def render(result: dict) -> bytes:
    # The complete bundle is PRIVATE; this summary intentionally omits identifiers/policy text.
    return ('# Revisión multiprograma local\n\n'
            f"Programas registrados: {result['program_count']}. Solicitudes: {len(result['decisions'])}.\n"
            + '\n'.join(f'{k}: {v}' for k,v in result['counts'].items()) +
            '\n\nNo se conectó ninguna cuenta ni se ejecutaron acciones sobre objetivos.\n'
            'ELIGIBLE solo significa coincidencia con el snapshot declarado y revisado localmente.\n'
            'No autentica autorización, reglas vigentes, participación o derecho a recompensa.\n'
            'Los originales son privados. Un cambio o vencimiento requiere nueva revisión.\n').encode()


def create_registry(registry_path: Path, requests_path: Path, evidence_root: Path, out: Path, *, at: str) -> dict:
    need(not out.exists() and not out.is_symlink(),'OUTPUT_EXISTS')
    need(not out.resolve().is_relative_to(ROOT.parent) and not out.resolve().is_relative_to(evidence_root.resolve()),'OUTPUT_INSIDE_INPUT')
    raw=read_artifact(registry_path.parent,registry_path.name)
    req=read_artifact(requests_path.parent,requests_path.name)
    registry=validate_registry(strict_json(raw));validate_requests(strict_json(req))
    evidence={};total=0
    for p in registry['programs']:
        blob=read_artifact(evidence_root,p['policy']['evidence_file']);total+=len(blob)
        need(total<=8_000_000,'EVIDENCE_TOTAL');evidence[program_key(p)]=blob
    result=evaluate(registry,strict_json(req),evidence,at=at)
    files={'registry.json':raw,'requests.json':req,'decision.json':canonical(result),
           'audit.json':canonical(_audit(result)),'REVIEW.md':render(result)}
    files.update({f'policy-{i:03d}.txt':evidence[program_key(p)] for i,p in enumerate(registry['programs'])})
    write_new_bundle(out,files)
    return verify_registry(out,at=at)


def verify_registry(root: Path, *, at: str) -> dict:
    """Verify historical bytes AND re-evaluate at an explicit current time.

    A formerly eligible, expired snapshot does not stay eligible after verification.
    The caller's time is not a trusted clock and the receipt is not authentication.
    """
    marker=strict_json(read_artifact(root,'COMPLETE.json'))
    fields(marker,{'schema_version','sha256'},'BUNDLE_SCHEMA')
    need(type(marker['schema_version']) is int and marker['schema_version']==1 and type(marker['sha256']) is dict,'BUNDLE_SCHEMA')
    raw=read_artifact(root,'registry.json');registry=validate_registry(strict_json(raw))
    expected=FIXED | {f'policy-{i:03d}.txt' for i in range(len(registry['programs']))}
    need(set(marker['sha256'])==expected and {p.name for p in root.iterdir()}==expected|{'COMPLETE.json'},'BUNDLE_FILES')
    data={name:read_artifact(root,name) for name in expected}
    need(data['registry.json']==raw and all(sha(v)==marker['sha256'][k] for k,v in data.items()),'BUNDLE_HASH')
    evidence={program_key(p):data[f'policy-{i:03d}.txt'] for i,p in enumerate(registry['programs'])}
    claimed=strict_json(data['decision.json']);requests=strict_json(data['requests.json'])
    historical=evaluate(registry,requests,evidence,at=claimed.get('evaluated_at'))
    need(canonical(historical)==data['decision.json'] and render(historical)==data['REVIEW.md'],'DECISION_MISMATCH')
    _verify_audit(strict_json(data['audit.json']),historical)
    current=evaluate(registry,requests,evidence,at=at)
    return {'status':'PROGRAM_REGISTRY_VERIFIED','historical_evidence_consistent':True,
            'current_review':current,'source_authenticated':False,'network_execution_allowed':False}


def main(argv: list[str]) -> int:
    p=PrivateArgumentParser(description='Review supplied multi-platform policies offline; no account/API access')
    sub=p.add_subparsers(dest='command',required=True)
    make=sub.add_parser('review-programs')
    for key in ('registry','requests','evidence','out'):make.add_argument('--'+key,type=Path,required=True)
    check=sub.add_parser('verify-programs');check.add_argument('--bundle',type=Path,required=True)
    for parser in (make,check):parser.add_argument('--at',help='Explicit evaluation time for offline replay; default current UTC')
    args=p.parse_args(argv)
    try:
        at=args.at or utc_now()
        r=(create_registry(args.registry,args.requests,args.evidence,args.out,at=at)
           if args.command=='review-programs' else verify_registry(args.bundle,at=at))
        counts=r['current_review']['counts']
        print(json.dumps({'status':r['status'],'counts':counts,'network_execution_allowed':False,
                          'platform_connectors_active':0,'explicit_replay_time':args.at is not None}))
        return 0 if set(counts)=={'LOCAL_SCOPE_ELIGIBLE'} else 1
    except (ValueError,OSError,TypeError,KeyError,UnicodeError,RecursionError) as exc:
        print(json.dumps({'status':'PROGRAM_REGISTRY_ERROR','error_type':type(exc).__name__,
                          'network_execution_allowed':False}));return 2


if __name__=='__main__':
    import sys
    raise SystemExit(main(sys.argv[1:]))
