"""Multiplatform program registry and fail-closed OFFLINE review routing.

No crawler, account connector, network scan, PoC execution or submission. An
operator-reviewed snapshot is not proof of permission from a platform. The only
positive decision is ELIGIBLE_LOCAL_REVIEW; it never authorizes live testing.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from .bridge import candidate as validate_candidate
from .native_runtime import load_components
from .static_intake import _PrivateParser as PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

PLATFORMS = ('immunefi', 'hackenproof', 'sherlock', 'cantina',
             'hackerone', 'bugcrowd', 'intigriti', 'yeswehack')
ACTIONS = ('offline_source_review', 'offline_evidence_review', 'offline_policy_review')
MAX_PROGRAMS, MAX_REQUESTS, MAX_DOC_BYTES = 128, 2048, 8_000_000
MAX_REVIEW_DAYS = 7  # local safety policy, NOT a rule attributed to any platform
HEX = re.compile(r'[0-9a-f]{64}\Z')
SLUG = re.compile(r'[a-z0-9][a-z0-9_-]{0,79}\Z')
REPO = re.compile(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z')
SHA = re.compile(r'[0-9a-f]{40}\Z')
ADDRESS = re.compile(r'0x[0-9a-fA-F]{40}\Z')
FIXED_FILES = {'registry.json', 'requests.json', 'decision.json', 'audit.json', 'REVIEW.md'}


class RegistryError(ValueError):
    """Fixed error codes only; no input values in public diagnostics."""


def need(ok, code):
    if not ok:
        raise RegistryError(code)


def keys(obj, names, code):
    need(type(obj) is dict and set(obj) == set(names.split()), code)
    return obj


def text(value, limit=256):
    need(type(value) is str and 0 < len(value) <= limit and
         all(ord(c) >= 32 for c in value), 'INVALID_TEXT')
    return value


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def utc(value):
    text(value, 40)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise RegistryError('INVALID_TIME') from exc
    need(parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0), 'UTC_TIME_REQUIRED')
    return parsed


def clock():
    return datetime.now(timezone.utc)


def asset(value):
    need(type(value) is dict, 'ASSET_SCHEMA')
    kind = value.get('kind')
    if kind == 'repository':
        keys(value, 'kind repo commit', 'REPOSITORY_SCHEMA')
        need(REPO.fullmatch(text(value['repo'])) is not None and
             SHA.fullmatch(text(value['commit'])) is not None, 'REPOSITORY_IDENTITY')
        return deepcopy(value)
    if kind == 'evm_contract':
        keys(value, 'kind chain_id address', 'CONTRACT_SCHEMA')
        need(type(value['chain_id']) is int and 0 < value['chain_id'] < 2**64 and
             ADDRESS.fullmatch(text(value['address'])) is not None, 'CONTRACT_IDENTITY')
        return {**value, 'address': value['address'].lower()}
    if kind == 'web_origin':
        keys(value, 'kind origin', 'ORIGIN_SCHEMA')
        raw = text(value['origin']); parts = urlsplit(raw)
        need(parts.scheme == 'https' and parts.hostname is not None and
             parts.username is None and parts.password is None and parts.path in ('', '/') and
             not parts.query and not parts.fragment and '\\' not in raw and '%' not in raw and
             '*' not in raw and all(ord(c)<128 for c in raw), 'EXACT_HTTPS_ORIGIN_REQUIRED')
        try:
            port = parts.port
        except ValueError as exc:
            raise RegistryError('INVALID_PORT') from exc
        need(parts.hostname == parts.hostname.lower() and ':' not in parts.hostname, 'HOST_PROFILE')
        need(re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', parts.hostname) is not None and
             '..' not in parts.hostname and not parts.hostname.endswith('.'), 'HOST_PROFILE')
        return {'kind': kind, 'origin': 'https://' + parts.hostname + (':'+str(port) if port not in (None,443) else '')}
    raise RegistryError('UNSUPPORTED_ASSET_KIND')


def program_key(program):
    return program['platform'] + ':' + program['program_id']


def revision(program):
    """Any scope/rule/document change invalidates the previous human review."""
    return digest({k:v for k,v in program.items() if k != 'review'})


def validate(registry):
    keys(registry, 'schema_version programs', 'REGISTRY_SCHEMA')
    need(type(registry['schema_version']) is int and registry['schema_version'] == 1, 'REGISTRY_VERSION')
    need(type(registry['programs']) is list and 1 <= len(registry['programs']) <= MAX_PROGRAMS, 'PROGRAM_LIMIT')
    seen, scopes = set(), set()
    for p in registry['programs']:
        keys(p, 'platform program_id scope_id kind status participation visibility window document rules assets excluded review', 'PROGRAM_SCHEMA')
        need(type(p['platform']) is str and p['platform'] in PLATFORMS and
             SLUG.fullmatch(text(p['program_id'])) is not None, 'PROGRAM_IDENTITY')
        key = program_key(p); text(p['scope_id'], 160)
        need(key not in seen and p['scope_id'] not in scopes, 'DUPLICATE_PROGRAM_OR_SCOPE')
        seen.add(key); scopes.add(p['scope_id'])
        need(p['kind'] in ('bounty','contest','disclosure') and p['status'] in ('active','paused','ended') and
             p['participation'] in ('accepted','unknown','revoked') and
             p['visibility'] in ('public','private'), 'PROGRAM_STATE')
        w = keys(p['window'], 'starts_at ends_at', 'WINDOW_SCHEMA')
        start = utc(w['starts_at'])
        if w['ends_at'] is not None:
            need(start < utc(w['ends_at']), 'WINDOW_ORDER')
        d = keys(p['document'], 'file sha256 source_url captured_at', 'DOCUMENT_SCHEMA')
        filename=text(d['file'], 128)
        need(re.fullmatch(r'[A-Za-z0-9_-]+\.(?:txt|md|json)',filename) is not None, 'DOCUMENT_PATH')
        need(HEX.fullmatch(text(d['sha256'])) is not None, 'DOCUMENT_HASH')
        url=urlsplit(text(d['source_url'],1024))
        need(url.scheme=='https' and url.hostname and url.username is None and url.password is None and
             not url.query and not url.fragment, 'DOCUMENT_URL')
        utc(d['captured_at'])
        r=keys(p['rules'], 'allowed_actions disclosure', 'RULES_SCHEMA')
        need(type(r['allowed_actions']) is list and all(type(a) is str and a in ACTIONS for a in r['allowed_actions']) and
             len(set(r['allowed_actions']))==len(r['allowed_actions']) and
             r['disclosure']=='manual_private_review', 'RULES_UNSUPPORTED')
        for name in ('assets','excluded'):
            rows=p[name];need(type(rows) is list and len(rows)<=512, 'ASSET_LIMIT')
            normalized=[canonical(asset(a)) for a in rows]
            need(len(normalized)==len(set(normalized)), 'DUPLICATE_ASSET')
        review=keys(p['review'], 'status reviewer reviewed_at expires_at revision_sha256', 'REVIEW_SCHEMA')
        need(review['status'] in ('pending','approved','revoked'), 'REVIEW_STATE')
        text(review['reviewer'],128)
        at,end=utc(review['reviewed_at']),utc(review['expires_at'])
        need(at<end<=at+timedelta(days=MAX_REVIEW_DAYS), 'REVIEW_VALIDITY_LIMIT')
        need(HEX.fullmatch(text(review['revision_sha256'])) is not None, 'REVIEW_DIGEST')
    return deepcopy(registry)


def validate_requests(requests):
    keys(requests, 'schema_version cases', 'REQUEST_SCHEMA')
    need(type(requests['schema_version']) is int and requests['schema_version']==1, 'REQUEST_VERSION')
    need(type(requests['cases']) is list and 1<=len(requests['cases'])<=MAX_REQUESTS,'REQUEST_LIMIT')
    seen=set()
    for case in requests['cases']:
        keys(case, 'id program_key action asset', 'CASE_SCHEMA')
        need(SLUG.fullmatch(text(case['id'])) is not None and case['id'] not in seen, 'CASE_ID')
        seen.add(case['id']);text(case['program_key'],170);text(case['action'],80);asset(case['asset'])
    return deepcopy(requests)


def evaluate(registry, documents, requests, *, now=None):
    """Pure finite routing: declared policy and snapshots, never a live permission."""
    registry,requests=validate(registry),validate_requests(requests)
    now=now or clock();need(isinstance(now,datetime) and now.tzinfo is not None,'AWARE_CLOCK_REQUIRED')
    now=now.astimezone(timezone.utc)
    names={p['document']['file'] for p in registry['programs']}
    need(type(documents) is dict and set(documents)==names and
         all(type(raw) is bytes and 0<len(raw)<=2_000_000 for raw in documents.values()) and
         sum(map(len,documents.values()))<=MAX_DOC_BYTES,'DOCUMENT_SET_OR_SIZE')
    programs={program_key(p):p for p in registry['programs']}
    audit=load_components().audit.AuditLog(clock=lambda:now.isoformat())
    audit.append('programs.review.start',{'registry_sha256':digest(registry),'requests_sha256':digest(requests)})
    decisions=[]
    for case in requests['cases']:
        reasons=[];p=programs.get(case['program_key'])
        if case['action'] not in ACTIONS:reasons.append('ACTION_NOT_IMPLEMENTED_OFFLINE')
        if p is None:reasons.append('PROGRAM_NOT_REGISTERED')
        else:
            rev=p['review'];doc=p['document'];win=p['window']
            if p['status']!='active':reasons.append('PROGRAM_NOT_ACTIVE')
            if p['participation']!='accepted':reasons.append('PARTICIPATION_NOT_ACCEPTED')
            if now<utc(win['starts_at']) or (win['ends_at'] is not None and now>=utc(win['ends_at'])):
                reasons.append('PROGRAM_WINDOW_CLOSED')
            if rev['status']!='approved':reasons.append('HUMAN_REVIEW_NOT_APPROVED')
            if rev['revision_sha256']!=revision(p):reasons.append('POLICY_CHANGED_SINCE_REVIEW')
            if now<utc(rev['reviewed_at']) or now>=utc(rev['expires_at']):reasons.append('REVIEW_EXPIRED_OR_FUTURE')
            if utc(doc['captured_at'])>utc(rev['reviewed_at']) or utc(doc['captured_at'])<utc(rev['reviewed_at'])-timedelta(days=MAX_REVIEW_DAYS):
                reasons.append('DOCUMENT_NOT_CURRENT_AT_REVIEW')
            if hashlib.sha256(documents[doc['file']]).hexdigest()!=doc['sha256']:reasons.append('POLICY_DOCUMENT_CHANGED')
            if case['action'] not in p['rules']['allowed_actions']:reasons.append('ACTION_NOT_DECLARED')
            target=canonical(asset(case['asset']))
            if target in {canonical(asset(a)) for a in p['excluded']}:reasons.append('EXPLICITLY_EXCLUDED')
            if target not in {canonical(asset(a)) for a in p['assets']}:reasons.append('ASSET_NOT_EXPLICITLY_LISTED')
        decision={'case_id':case['id'],'case_sha256':digest(case),'program_key_sha256':digest(case['program_key']),
                  'policy_revision_sha256':revision(p) if p else None,
                  'status':'BLOCKED' if reasons else 'ELIGIBLE_LOCAL_REVIEW','reasons':reasons,
                  'live_testing_authorized':False,'submission_authorized':False}
        decisions.append(decision)
        audit.append('programs.review.case',decision)
    counts=dict(Counter(d['status'] for d in decisions))
    audit.append('programs.review.complete',{'cases':len(decisions),'counts':counts})
    audit.assert_intact()
    return {'schema_version':1,'checked_at':now.isoformat(),'registry_sha256':digest(registry),
            'requests_sha256':digest(requests),'document_hashes':{n:hashlib.sha256(documents[n]).hexdigest() for n in sorted(names)},
            'counts':counts,'decisions':decisions,'operator_attestations_only':True,
            'platform_accounts_connected':False,'authorization_authenticated':False,
            'network_used':False,'tests_executed_on_targets':False,'submission_enabled':False,
            'vulnerability_confirmed':False}, {'entries':[asdict(e) for e in audit.entries]}


def candidate_requests(registry, candidate, *, program, chain_id):
    """Bind the existing unverified Candidate to explicit program/repo/chain IDs.

    Both the code revision AND every affected contract need their own listed
    asset. This gate prepares human evidence review, not execution of the PoC.
    """
    registry=validate(registry);c=validate_candidate(candidate)
    p=next((p for p in registry['programs'] if program_key(p)==program),None)
    need(p is not None and p['scope_id']==c['scope_id'],'CANDIDATE_PROGRAM_SCOPE_MISMATCH')
    need(type(chain_id) is int and 0<chain_id<2**64,'CANDIDATE_CHAIN_REQUIRED')
    targets=[{'kind':'repository','repo':c['target']['repo'],'commit':c['target']['commit']}]
    targets += [{'kind':'evm_contract','chain_id':chain_id,'address':a} for a in c['affected_contracts']]
    return {'schema_version':1,'cases':[{'id':f'candidate-{i:03d}','program_key':program,
        'action':'offline_evidence_review','asset':a} for i,a in enumerate(targets)]}


def review_candidate(registry,documents,candidate,*,program,chain_id,now=None):
    req=candidate_requests(registry,candidate,program=program,chain_id=chain_id)
    result,audit=evaluate(registry,documents,req,now=now)
    return {'candidate_id':candidate['id'],'candidate_sha256':digest(candidate),
            'status':'BLOCKED' if result['counts'].get('BLOCKED') else 'ELIGIBLE_LOCAL_REVIEW',
            'decision':result,'audit':audit,'finding_confirmed':False,'poc_executed':False}


def render(result):
    return ('# Revisión multiplataforma — solo local\n\n'
            f"Casos: {len(result['decisions'])}; aptos para revisión local: {result['counts'].get('ELIGIBLE_LOCAL_REVIEW',0)}; "
            f"bloqueados: {result['counts'].get('BLOCKED',0)}.\n\n"
            'Las reglas son instantáneas revisadas por un operador, no permisos autenticados de una plataforma. '
            'No se ejecutaron pruebas contra objetivos, no se conectaron cuentas y no se enviaron reportes. '
            'El paquete contiene políticas y objetivos privados: no publicarlo.\n').encode()


def create(registry_file,requests_file,documents_root,out,*,now=None):
    need(not out.exists() and not out.is_symlink(),'NEW_OUTPUT_REQUIRED')
    need(not out.resolve().is_relative_to(Path(__file__).resolve().parent.parent),'OUTPUT_INSIDE_CODE')
    raw=read_artifact(registry_file.parent,registry_file.name);registry=validate(strict_json(raw))
    request_raw=read_artifact(requests_file.parent,requests_file.name);req=validate_requests(strict_json(request_raw))
    names=sorted({p['document']['file'] for p in registry['programs']})
    docs={name:read_artifact(documents_root,name) for name in names}
    result,audit=evaluate(registry,docs,req,now=now)
    files={'registry.json':raw,'requests.json':request_raw,'decision.json':canonical(result),
           'audit.json':canonical(audit),'REVIEW.md':render(result)}
    files.update({f'policy-{i:03d}.txt':docs[name] for i,name in enumerate(names)})
    write_new_bundle(out,files)
    return verify(out,now=now)


def verify(root,*,now=None):
    marker=strict_json(read_artifact(root,'COMPLETE.json'))
    keys(marker,'schema_version sha256','MANIFEST_SCHEMA')
    need(type(marker['schema_version']) is int and marker['schema_version']==1 and type(marker['sha256']) is dict,'MANIFEST_VERSION')
    registry=validate(strict_json(read_artifact(root,'registry.json')))
    names=sorted({p['document']['file'] for p in registry['programs']})
    expected=FIXED_FILES | {f'policy-{i:03d}.txt' for i in range(len(names))}
    need(set(marker['sha256'])==expected and {p.name for p in root.iterdir()}==expected|{'COMPLETE.json'},'BUNDLE_FILES')
    data={name:read_artifact(root,name) for name in expected}
    need(all(hashlib.sha256(raw).hexdigest()==marker['sha256'][name] for name,raw in data.items()),'ARTIFACT_HASH')
    need(canonical(registry)==canonical(strict_json(data['registry.json'])),'REGISTRY_CHANGED_DURING_READ')
    result=strict_json(data['decision.json']);checked=utc(result['checked_at'])
    now=now or clock();need(now.tzinfo is not None and checked<=now,'FUTURE_DECISION')
    docs={name:data[f'policy-{i:03d}.txt'] for i,name in enumerate(names)}
    req=strict_json(data['requests.json'])
    replay,audit=evaluate(registry,docs,req,now=checked)
    need(data['decision.json']==canonical(replay) and data['audit.json']==canonical(audit) and
         data['REVIEW.md']==render(replay),'REPLAY_DISAGREEMENT')
    current,_=evaluate(registry,docs,req,now=now)
    return {'status':'LOCAL_PROGRAM_REVIEW_VERIFIED','historical_counts':result['counts'],
            'current_counts':current['counts'],'current_decisions':current['decisions'],
            'checked_at':now.astimezone(timezone.utc).isoformat(),'historical_checked_at':result['checked_at'],
            'authorization_authenticated':False,'live_testing_authorized':False,
            'platform_accounts_connected':False,'submission_enabled':False}


def main(argv=None):
    parser=PrivateArgumentParser(description='Offline program registry; no platform accounts or target execution')
    sub=parser.add_subparsers(dest='command',required=True)
    make=sub.add_parser('review-programs')
    for name in ('registry','requests','documents','out'):make.add_argument('--'+name,type=Path,required=True)
    sub.add_parser('verify-programs').add_argument('--bundle',type=Path,required=True)
    sub.add_parser('program-platforms')
    args=parser.parse_args(argv)
    try:
        if args.command=='program-platforms':
            print(json.dumps({'platforms':PLATFORMS,'account_connectors':False,'allowed_actions':ACTIONS}));return 0
        result=create(args.registry,args.requests,args.documents,args.out) if args.command=='review-programs' else verify(args.bundle)
        print(json.dumps({k:result[k] for k in ('status','current_counts','authorization_authenticated','live_testing_authorized')}))
        return 1 if result['current_counts'].get('BLOCKED') else 0
    except (ValueError,OSError,KeyError,TypeError,OverflowError,RecursionError):
        print(json.dumps({'status':'PROGRAM_REVIEW_ERROR','live_testing_authorized':False}));return 2


if __name__=='__main__':
    raise SystemExit(main())
