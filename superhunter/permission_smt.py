"""Actual Z3 checking of the declared finite RBAC model, not deployed software.

Translate role-assignment booleans into QF_LIA, ask whether each property can
fail, replay SAT assignments through both existing concrete permission engines,
and compare against bounded exhaustive enumeration. No attack planning, source
execution, arbitrary SMT input, networks, Solidity or automatic changes.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import time
import uuid

from . import permission_domain as domain, permissions, smt_backend
from .native_runtime import load_components
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle, MAX_BYTES

ROOT = Path(__file__).resolve().parent
FILES = {'model.json','encoding.json','analysis.json','audit.json','receipt.json','REVIEW.md'}
CODE_FILES = ('permission_smt.py','smt_backend.py','permission_domain.py','permissions.py',
              'native_runtime.py','safe_io.py','privacy.py')
MAX_PROPERTIES = 128
MAX_ENCODING_BYTES = 500_000


def need(condition: bool, code: str) -> None:
    if not condition:
        raise permissions.PolicyError(code)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _and(parts):
    parts = list(parts)
    return 'true' if not parts else parts[0] if len(parts)==1 else '(and '+' '.join(parts)+')'


def _or(parts):
    parts = list(parts)
    return 'false' if not parts else parts[0] if len(parts)==1 else '(or '+' '.join(parts)+')'


def _not(expr):
    return '(not '+expr+')'


def compile_model(raw: object) -> dict:
    """Original compiler for this explicit policy model, not for Solidity/code.

    User labels never enter SMT identifiers. Independent role-graph walks
    determine each direct role's inherited grants/denials; no calls to the
    concrete permission closure or evaluation routines are used here.
    """
    model = domain.validate_model(raw)
    p, variables = model['policy'], model['variables']
    variable_ids = {(v['user'],v['role']):i for i,v in enumerate(variables)}
    code = ['(set-logic QF_LIA)'] + [f'(declare-fun x{i} () Bool)' for i in range(len(variables))]
    closures = {}
    for role in p['roles']:
        seen, pending = set(), [role]
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            pending.extend(p['roles'][current]['inherits'])
        closures[role] = seen
    memberships = {}
    for ui, user in enumerate(sorted(p['users'])):
        for ri, role in enumerate(sorted(p['roles'])):
            present = role in p['users'][user]['roles']
            index = variable_ids.get((user,role))
            expr = ('true' if present else 'false') if index is None else (f'(not x{index})' if present else f'x{index}')
            name = f'm{ui}_{ri}'
            code.append(f'(define-fun {name} () Bool {expr})')
            memberships[user,role] = name
    defined = {}

    def allowed(user, permission, removed=()):
        key = (user,permission,tuple(sorted(removed)))
        if key in defined:
            return defined[key]
        grants, denies = [], []
        for role in sorted(p['roles']):
            if role in removed:
                continue
            ancestors = closures[role]
            if any(permission in p['roles'][a]['allow'] for a in ancestors):
                grants.append(memberships[user,role])
            if any(permission in p['roles'][a]['deny'] for a in ancestors):
                denies.append(memberships[user,role])
        expr = 'false' if p['users'][user]['disabled'] else _and((_or(grants),_not(_or(denies))))
        name = f'a{len(defined)}'
        code.append(f'(define-fun {name} () Bool {expr})')
        defined[key] = name
        return name

    props = []
    for rule in p['assertions']:
        access = allowed(rule['user'],rule['permission'])
        props.append({'id':'assertion:'+rule['id'], 'applicable':'true',
                      'violation':_not(access) if rule['expected']=='ALLOW' else access})
    for rule in p['separation_rules']:
        for user in sorted(p['users']):
            terms = [f'(ite {allowed(user,permission)} 1 0)' for permission in rule['permissions']]
            total = terms[0] if len(terms)==1 else '(+ '+' '.join(terms)+')'
            props.append({'id':'separation:'+rule['id']+':'+user, 'applicable':'true',
                          'violation':f'(> {total} {rule["max_allowed"]})'})
    for rule in p['revocations']:
        user, removed = rule['user'], rule['remove_roles']
        app = _and(memberships[user,r] for r in removed)
        remains = _or(allowed(user,permission,removed) for permission in rule['must_deny'])
        props.append({'id':'revocation:'+rule['id'], 'applicable':app, 'violation':_and((app,remains))})
    need(len(props)<=MAX_PROPERTIES, 'SMT_PROPERTY_LIMIT')
    need([r['id'] for r in props] == domain._property_ids(p), 'SMT_PROPERTY_ID_MISMATCH')
    result = {'schema_version':1,'model':'sh-rbac-smt-v1','input_sha256':digest(canonical(model)),
              'logic':'QF_LIA','variable_count':len(variables),'base':'\n'.join(code)+'\n','properties':props}
    need(len(canonical(result))<=MAX_ENCODING_BYTES, 'SMT_ENCODING_LIMIT')
    return result


def _program(encoding: dict, prop: dict, kind: str) -> str:
    return encoding['base']+'(assert '+prop[kind]+')\n'


def replay_assignment(model: dict, property_id: str, assignment: list[bool]) -> dict:
    """A solver-produced assignment must be valid in both concrete engines."""
    need(type(assignment) is list and len(assignment)==len(model['variables']) and
         all(type(x) is bool for x in assignment), 'SMT_WITNESS_SHAPE')
    index = sum((1<<j) for j,bit in enumerate(assignment) if bit)
    users = domain._primary_assignment(model['policy'],model['variables'],index)
    other = domain._reference_assignment(model['policy'],model['variables'],tuple(assignment))
    for user in users.values():
        user['roles'] = sorted(user['roles'])
    need(canonical(users)==canonical(other), 'SMT_WITNESS_ENUMERATION_MISMATCH')
    closures = permissions._closures(model['policy']['roles'])
    states = domain._decisions(model['policy'],users,closures)
    checks,_ = domain._properties(model['policy'],users,states,closures)
    found = [x for x in checks if x['id']==property_id]
    need(len(found)==1, 'SMT_WITNESS_PROPERTY_MISSING')
    check = found[0]
    return {'applicable': check['applicable'],
            'violation': check['applicable'] is True and check['passed'] is False,
            'configuration_index': index, 'assignment_sha256':digest(canonical(users))}


def _validate_budgets(timeout_ms,resource_limit,wall_ms):
    need(type(timeout_ms) is int and 1<=timeout_ms<=5000 and
         type(resource_limit) is int and 1<=resource_limit<=10_000_000 and
         type(wall_ms) is int and 1<=wall_ms<=30_000, 'SMT_BUDGET_INVALID')


def _check_record(model,encoding,prop,kind,result):
    need(type(result) is dict and set(result)=={'status','query_sha256','timeout_ms',
         'resource_limit','assignment','unknown_reason','engine'}, 'SMT_QUERY_SCHEMA')
    need(result['query_sha256']==digest(_program(encoding,prop,kind).encode('ascii')), 'SMT_QUERY_BINDING')
    need(type(result['status']) is str and result['status'] in ('SAT','UNSAT','UNKNOWN','NOT_RUN'), 'SMT_QUERY_STATUS')
    need(type(result['timeout_ms']) is int and type(result['resource_limit']) is int, 'SMT_QUERY_BUDGET_TYPE')
    if result['status']=='SAT':
        replay = replay_assignment(model,prop['id'],result['assignment'])
        need(replay[kind] is True, 'SMT_WITNESS_DISAGREEMENT')
        need(result['unknown_reason'] is None,'SMT_KNOWN_WITH_UNKNOWN_REASON')
    else:
        need(result['assignment'] is None,'SMT_UNEXPECTED_WITNESS')
        need((result['status']=='UNSAT' and result['unknown_reason'] is None) or
             (result['status'] in ('UNKNOWN','NOT_RUN') and result['unknown_reason'] in
              ('TIMEOUT','RESOURCE_LIMIT','OTHER','WALL_BUDGET')), 'SMT_REASON_INVALID')


def _summary(model,encoding,queries,reference,engine,budgets):
    need(len(queries)==len(encoding['properties']), 'SMT_QUERY_COUNT')
    violations = unknown = vacuous = 0
    for prop,row in zip(encoding['properties'],queries):
        need(set(row)=={'id','applicable','violation'} and row['id']==prop['id'], 'SMT_QUERY_IDENTITY')
        for kind in ('applicable','violation'):
            result=row[kind]
            _check_record(model,encoding,prop,kind,result)
            need(canonical(result['engine'])==canonical(engine) and result['timeout_ms']==budgets['timeout_ms']
                 and result['resource_limit']==budgets['resource_limit'], 'SMT_ENGINE_OR_BUDGET_MISMATCH')
        app,fail = row['applicable']['status'],row['violation']['status']
        violations += fail=='SAT'
        unknown += app in ('UNKNOWN','NOT_RUN') or fail in ('UNKNOWN','NOT_RUN')
        vacuous += app=='UNSAT'
        concrete=reference['property_coverage'][prop['id']]
        # Any observed failure refutes UNSAT, even in a truncated enumeration.
        need(not (concrete['failed'] and fail=='UNSAT'), 'SMT_EXHAUSTIVE_DISAGREEMENT')
        need(not (concrete['evaluated'] and app=='UNSAT'), 'SMT_APPLICABILITY_DISAGREEMENT')
        if reference['coverage_complete']:
            need(not (not concrete['failed'] and fail=='SAT'), 'SMT_EXHAUSTIVE_DISAGREEMENT')
            need(not (not concrete['evaluated'] and app=='SAT'), 'SMT_APPLICABILITY_DISAGREEMENT')
    proved = bool(queries) and not violations and not unknown and not vacuous
    status=('POLICY_SMT_VIOLATION' if violations else 'POLICY_SMT_PROVED' if proved else 'POLICY_SMT_INCONCLUSIVE')
    return {'schema_version':1,'status':status,'model_sha256':digest(canonical(model)),
            'encoding_sha256':digest(canonical(encoding)), 'engine':engine, 'budgets':budgets,
            'properties':len(queries),'violated_properties':violations,'inconclusive_properties':unknown,
            'vacuous_properties':vacuous,'queries':queries,'domain_configurations':1<<len(model['variables']),
            'enumeration':{key:reference[key] for key in ('coverage_complete','examined_configurations',
                'unexamined_configurations','violating_configurations','property_coverage','coverage_chain_sha256')},
            'solver_executed':any(r[k]['status']!='NOT_RUN' for r in queries for k in ('applicable','violation')),
            'proved_for_declared_model':proved,
            'independently_exhaustive_confirmed':proved and reference['coverage_complete'],
            'unsat_proof_certificate_checked':False,'production_reachability_verified':False,
            'live_enforcement_verified':False,'solidity_analyzed':False,
            'vulnerability_confirmed':False,'producer_authenticated':False,'manual_review_required':True}


def analyze_smt(raw: object, *, timeout_ms=1000, resource_limit=1_000_000, wall_ms=30_000) -> tuple[dict,dict]:
    _validate_budgets(timeout_ms,resource_limit,wall_ms)
    model=domain.validate_model(raw); encoding=compile_model(model)
    engine=smt_backend.engine_identity()
    queries=[];deadline=time.monotonic()+wall_ms/1000
    for prop in encoding['properties']:
        row={'id':prop['id']}
        for kind in ('applicable','violation'):
            program=_program(encoding,prop,kind)
            if time.monotonic()>=deadline:
                result={'status':'NOT_RUN','query_sha256':digest(program.encode('ascii')),
                        'assignment':None,'unknown_reason':'WALL_BUDGET','timeout_ms':timeout_ms,
                        'resource_limit':resource_limit,'engine':engine}
            else:
                result=smt_backend.solve_generated(program,len(model['variables']),timeout_ms=timeout_ms,
                                                   resource_limit=resource_limit)
            _check_record(model,encoding,prop,kind,result)
            row[kind]=result
        queries.append(row)
    reference=domain.analyze_domain(model)
    budgets={'timeout_ms':timeout_ms,'resource_limit':resource_limit,'wall_ms':wall_ms}
    result=_summary(model,encoding,queries,reference,engine,budgets)
    need(canonical(smt_backend.engine_identity())==canonical(engine),'SMT_ENGINE_CHANGED')
    need(len(canonical(result))<=MAX_BYTES,'SMT_OUTPUT_LIMIT')
    return encoding,result


def _code_digest():
    return digest(canonical({p:digest(read_artifact(ROOT,p)) for p in CODE_FILES}))


def _events(result,run_id):
    rows=[('smt.start',{'run_id':run_id,'model_sha256':result['model_sha256'],
                      'encoding_sha256':result['encoding_sha256'],'engine':result['engine']})]
    rows.extend(('smt.query',{'index':i,'property_sha256':digest(row['id'].encode()),
                             'query_pair_sha256':digest(canonical(row))}) for i,row in enumerate(result['queries']))
    rows.append(('smt.complete',{'run_id':run_id,'analysis_sha256':digest(canonical(result)),
                                'status':result['status'],'vulnerability_confirmed':False}))
    return rows


def render(result):
    return (f"# Verificación SMT de la política declarada\n\nEstado: **{result['status']}**.\n\n"
            f"Propiedades: {result['properties']}; violadas: {result['violated_properties']}; "
            f"inconclusas: {result['inconclusive_properties']}.\n"
            f"Motor ejecutado: Z3 {result['engine']['version']}. Dominio: {result['domain_configurations']} configuraciones.\n"
            f"Enumeración contrastada: {result['enumeration']['examined_configurations']}; "
            f"completa: {result['enumeration']['coverage_complete']}.\n\n"
            "PROVED significa únicamente que Z3 resolvió UNSAT para las negaciones de las propiedades "
            "dentro de este modelo JSON, sin vacuidad observada. La traducción, los supuestos y el motor "
            "pueden tener errores. Los testigos SAT se comprueban con dos evaluadores concretos. "
            "La enumeración independiente puede ser parcial: se declara por separado. "
            "No se verificó un certificado formal UNSAT externo. UNKNOWN/NOT_RUN nunca son aprobación.\n\n"
            "No analiza Solidity ni prueba alcanzabilidad o cumplimiento en producción. "
            "No hay explotación ni cambio de permisos. El paquete completo contiene políticas privadas. "
            "Los hashes identifican bytes; no autentican al productor.\n").encode()


def create_smt(source: Path,out: Path,**budgets):
    need(not out.exists() and not out.is_symlink(),'SMT_OUTPUT_EXISTS')
    need(not out.resolve().is_relative_to(ROOT.parent),'SMT_OUTPUT_INSIDE_CHECKOUT')
    raw=read_artifact(source.parent,source.name);code=_code_digest()
    encoding,result=analyze_smt(strict_json(raw),**budgets)
    native=load_components();audit=native.audit.AuditLog();run_id=str(uuid.uuid4())
    for event,data in _events(result,run_id):audit.append(event,data)
    audit.assert_intact()
    need(code==_code_digest(),'SMT_CODE_CHANGED')
    receipt={'schema_version':1,'run_id':run_id,'code_sha256':code,'audit_head':audit.head,
             'audit_count':len(audit),'native_sources':list(native.provenance)}
    write_new_bundle(out,{'model.json':raw,'encoding.json':canonical(encoding),'analysis.json':canonical(result),
        'audit.json':canonical({'entries':[asdict(x) for x in audit.entries]}),'receipt.json':canonical(receipt),
        'REVIEW.md':render(result)})
    return _public(result)


def _public(result):
    return {k:result[k] for k in ('status','properties','violated_properties','inconclusive_properties',
             'domain_configurations','solver_executed','proved_for_declared_model',
             'independently_exhaustive_confirmed','vulnerability_confirmed')}


def verify_smt(root: Path):
    before=_code_digest();marker=strict_json(read_artifact(root,'COMPLETE.json'))
    need(set(marker)=={'schema_version','sha256'} and type(marker['schema_version']) is int and
         marker['schema_version']==1 and type(marker['sha256']) is dict and set(marker['sha256'])==FILES,
         'SMT_MANIFEST')
    need({p.name for p in root.iterdir()}==FILES|{'COMPLETE.json'},'SMT_FILE_SET')
    blobs={name:read_artifact(root,name) for name in FILES}
    need(all(digest(raw)==marker['sha256'][name] for name,raw in blobs.items()),'SMT_ARTIFACT_HASH')
    model=domain.validate_model(strict_json(blobs['model.json']));encoding=compile_model(model)
    need(canonical(encoding)==blobs['encoding.json'],'SMT_ENCODING_MISMATCH')
    result=strict_json(blobs['analysis.json']);budgets=result['budgets']
    need(set(budgets)=={'timeout_ms','resource_limit','wall_ms'},'SMT_BUDGET_FIELDS')
    _validate_budgets(**budgets)
    engine=smt_backend.engine_identity()
    need(canonical(result['engine'])==canonical(engine),'SMT_ENGINE_MISMATCH')
    reference=domain.analyze_domain(model)
    expected=_summary(model,encoding,result['queries'],reference,engine,budgets)
    need(canonical(expected)==blobs['analysis.json'],'SMT_ANALYSIS_MISMATCH')
    need(render(result)==blobs['REVIEW.md'],'SMT_REPORT_MISMATCH')
    # Re-run determinate queries. SAT models may differ; replay the saved one
    # independently rather than comparing two equally valid assignments.
    deadline=time.monotonic()+budgets['wall_ms']/1000
    for prop,row in zip(encoding['properties'],result['queries']):
        for kind in ('applicable','violation'):
            saved=row[kind]
            if saved['status'] in ('SAT','UNSAT'):
                need(time.monotonic()<deadline,'SMT_RECHECK_BUDGET')
                new=smt_backend.solve_generated(_program(encoding,prop,kind),len(model['variables']),
                       timeout_ms=budgets['timeout_ms'],resource_limit=budgets['resource_limit'])
                _check_record(model,encoding,prop,kind,new)
                need(new['status']==saved['status'],'SMT_RECHECK_INCONCLUSIVE_OR_DISAGREEMENT')
    receipt=strict_json(blobs['receipt.json']);native=load_components()
    need(set(receipt)=={'schema_version','run_id','code_sha256','audit_head','audit_count','native_sources'}
         and type(receipt['schema_version']) is int and receipt['schema_version']==1,'SMT_RECEIPT')
    need(receipt['code_sha256']==before,'SMT_STALE_CODE')
    need(type(receipt['run_id']) is str and str(uuid.UUID(receipt['run_id']))==receipt['run_id'],'SMT_RUN_ID')
    need(canonical(receipt['native_sources'])==canonical(list(native.provenance)),'SMT_NATIVE_SOURCE')
    journal=strict_json(blobs['audit.json']);need(set(journal)=={'entries'},'SMT_JOURNAL')
    rows=journal['entries'];events=_events(result,receipt['run_id'])
    need(type(rows) is list and len(rows)==len(events) and type(receipt['audit_count']) is int
         and receipt['audit_count']==len(rows),'SMT_AUDIT_COUNT')
    previous='0'*64;last=None
    for i,(row,(event,data)) in enumerate(zip(rows,events)):
        need(type(row) is dict and set(row)=={'index','timestamp','event','data','prev_hash','hash'},'SMT_AUDIT_FIELDS')
        need(type(row['index']) is int and row['index']==i and row['event']==event and
             canonical(row['data'])==canonical(data),'SMT_AUDIT_SEMANTICS')
        need(type(row['timestamp']) is str,'SMT_AUDIT_TIME')
        stamp=datetime.fromisoformat(row['timestamp'])
        need(stamp.tzinfo is not None and (last is None or stamp>=last),'SMT_AUDIT_TIME')
        need(row['prev_hash']==previous and native.audit.AuditEntry(**row).recompute()==row['hash'],'SMT_AUDIT_HASH')
        previous,last=row['hash'],stamp
    need(previous==receipt['audit_head'],'SMT_AUDIT_HEAD')
    need(before==_code_digest() and canonical(smt_backend.engine_identity())==canonical(engine),'SMT_CODE_OR_ENGINE_CHANGED')
    return _public(result)


def main(argv):
    parser=PrivateArgumentParser(description='Z3 plus concrete checks for declared local RBAC policies only')
    sub=parser.add_subparsers(dest='command',required=True)
    run=sub.add_parser('check-permission-smt')
    run.add_argument('--model',required=True,type=Path);run.add_argument('--out',required=True,type=Path)
    run.add_argument('--timeout-ms',type=int,default=1000)
    run.add_argument('--resource-limit',type=int,default=1_000_000)
    sub.add_parser('verify-permission-smt').add_argument('--bundle',required=True,type=Path)
    args=parser.parse_args(argv)
    try:
        result=(create_smt(args.model,args.out,timeout_ms=args.timeout_ms,resource_limit=args.resource_limit)
                if args.command=='check-permission-smt' else verify_smt(args.bundle))
        print(json.dumps(result,sort_keys=True))
        return 0 if result['status']=='POLICY_SMT_PROVED' else 1
    except (OSError,ValueError,TypeError,KeyError,AttributeError,RecursionError):
        print(json.dumps({'status':'POLICY_SMT_ERROR','error_code':'INVALID_MODEL_ENGINE_OR_EVIDENCE',
                          'vulnerability_confirmed':False}))
        return 2
