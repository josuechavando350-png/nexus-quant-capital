"""Three-stage, offline label separation and committed scoring protocol.

prepare: labels are sealed OUTSIDE the published unlabeled manifest.
freeze: predictions are committed without reading labels.
score: only after freezing, reveal labels and reuse the benchmark evaluator.

A SHA-256 commitment does not prove honest labels, actual secrecy or time order.
The operator must retain externally pinned marker hashes and isolate producers.
No code under evaluation, subprocess, RPC or network access is executed here.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import secrets
from pathlib import Path
import re
from typing import Any

from . import benchmark as bm
from .native_runtime import source_inventory
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
HASH = re.compile(r'[a-f0-9]{64}\Z')
MAX_CASES = 512
DOMAIN = b'SUPERHUNTER-OFFLINE-HOLDOUT-COMMITMENT-V1\x00'
PUBLIC = {'manifest.json', 'commitment.json', 'README.md'}
PRIVATE = {'labels.json', 'nonce.json'}
FROZEN = {'manifest.json', 'commitment.json', 'predictions.json', 'PREPARED.json', 'README.md'}
SCORED = {'manifest.json', 'commitment.json', 'predictions.json', 'PREPARED.json',
          'FROZEN.json', 'labels.json', 'nonce.json', 'evaluation.json', 'audit.json',
          'ENGINE.json', 'REVIEW.md'}


class HoldoutError(ValueError):
    """Fixed error codes only; no confidential input text in diagnostics."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise HoldoutError(code)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def hash_text(value: Any) -> None:
    require(type(value) is str and HASH.fullmatch(value) is not None, 'INVALID_HASH')


def fields(value: Any, expected: set[str], code: str) -> None:
    require(type(value) is dict and set(value) == expected, code)


def identifier(value: Any) -> None:
    bm.identifier(value)


def validate_manifest(value: Any) -> dict:
    fields(value, {'schema_version','corpus_id','provenance','cases'}, 'MANIFEST_SCHEMA')
    require(type(value['schema_version']) is int and value['schema_version']==1,'VERSION')
    identifier(value['corpus_id'])
    require(type(value['provenance']) is str and value['provenance'] in ('synthetic','curated'), 'PROVENANCE')
    rows=value['cases']
    require(type(rows) is list and 1<=len(rows)<=MAX_CASES, 'CASE_LIMIT')
    ids=set();contents=set();groups={};test_count=0
    for row in rows:
        fields(row, {'case_id','group_id','content_sha256','split','family'}, 'CASE_SCHEMA')
        for field in ('case_id','group_id','family'): identifier(row[field])
        hash_text(row['content_sha256'])
        require(row['case_id'] not in ids,'DUPLICATE_CASE')
        require(row['content_sha256'] not in contents,'DUPLICATE_CONTENT')
        require(type(row['split']) is str and row['split'] in bm.SPLITS, 'SPLIT')
        ids.add(row['case_id']);contents.add(row['content_sha256'])
        old=groups.setdefault(row['group_id'],row['split'])
        require(old==row['split'],'RELATED_GROUP_CROSSES_SPLITS')
        test_count += (row['split']=='test')
    require(test_count>0,'NO_HELD_OUT_CASES')
    return deepcopy(value)


def validate_labels(value: Any, manifest: dict) -> dict:
    fields(value, {'schema_version','corpus_id','cases'}, 'LABELS_SCHEMA')
    require(type(value['schema_version']) is int and value['schema_version']==1,'VERSION')
    require(value['corpus_id']==manifest['corpus_id'],'LABEL_CORPUS_MISMATCH')
    rows=value['cases']
    require(type(rows) is list and len(rows)==len(manifest['cases']),'LABEL_COUNT')
    ids=set()
    for row in rows:
        fields(row, {'case_id','truth','severity'}, 'LABEL_SCHEMA')
        identifier(row['case_id'])
        require(row['case_id'] not in ids,'DUPLICATE_LABEL');ids.add(row['case_id'])
        require(type(row['truth']) is str and row['truth'] in ('positive','negative'), 'TRUTH')
        require(type(row['severity']) is str and (
            (row['truth']=='negative' and row['severity']=='none') or
            (row['truth']=='positive' and row['severity'] in bm.SEVERITIES)), 'SEVERITY')
    require(ids=={x['case_id'] for x in manifest['cases']}, 'LABEL_INVENTORY')
    # Also apply the original corpus partition, count, and type checks.
    full_corpus=assemble_corpus(manifest,value)
    bm.validate_corpus(full_corpus)
    return deepcopy(value)


def assemble_corpus(manifest: dict, labels: dict) -> dict:
    by_id={r['case_id']:r for r in labels['cases']}
    return {'schema_version':1,'corpus_id':manifest['corpus_id'],
            'provenance':manifest['provenance'],'unit':'one-reviewed-property-per-case',
            'cases':[{**r,'truth':by_id[r['case_id']]['truth'],
                     'severity':by_id[r['case_id']]['severity']} for r in manifest['cases']]}


def commitment(manifest: dict, labels: dict, nonce: str) -> dict:
    hash_text(nonce)
    return {'schema_version':1,'profile':'offline-commit-freeze-reveal-v1',
            'manifest_sha256':sha(canonical(manifest)),
            'labels_commitment':sha(DOMAIN+bytes.fromhex(nonce)+canonical(labels)),
            'all_cases':len(manifest['cases']),
            'test_cases':sum(x['split']=='test' for x in manifest['cases'])}


def validate_commitment(value: Any, manifest: dict) -> dict:
    fields(value, {'schema_version','profile','manifest_sha256','labels_commitment','all_cases','test_cases'}, 'COMMITMENT_SCHEMA')
    require(type(value['schema_version']) is int and value['schema_version']==1 and
            value['profile']=='offline-commit-freeze-reveal-v1', 'COMMITMENT_VERSION')
    hash_text(value['manifest_sha256']);hash_text(value['labels_commitment'])
    require(value['manifest_sha256']==sha(canonical(manifest)) and
            type(value['all_cases']) is int and value['all_cases']==len(manifest['cases']) and
            type(value['test_cases']) is int and
            value['test_cases']==sum(x['split']=='test' for x in manifest['cases']), 'COMMITMENT_MISMATCH')
    return deepcopy(value)


def validate_predictions(value: Any, manifest: dict) -> dict:
    fields(value, {'schema_version','run_id','producer','manifest_sha256','records'}, 'PREDICTIONS_SCHEMA')
    require(type(value['schema_version']) is int and value['schema_version']==1,'VERSION')
    identifier(value['run_id'])
    fields(value['producer'], {'name','source_sha256'},'PRODUCER_SCHEMA')
    identifier(value['producer']['name']);hash_text(value['producer']['source_sha256'])
    require(value['manifest_sha256']==sha(canonical(manifest)), 'PREDICTIONS_WRONG_MANIFEST')
    rows=value['records'];selected={r['case_id'] for r in manifest['cases'] if r['split']=='test'}
    require(type(rows) is list and len(rows)==len(selected),'PREDICTION_COUNT')
    seen=set()
    for row in rows:
        fields(row, {'case_id','decision','elapsed_ms','cost_micro_usd'},'PREDICTION_SCHEMA')
        identifier(row['case_id'])
        require(row['case_id'] not in seen,'DUPLICATE_PREDICTION');seen.add(row['case_id'])
        require(type(row['decision']) is str and row['decision'] in bm.DECISIONS, 'DECISION')
        require(type(row['elapsed_ms']) is int and 0<=row['elapsed_ms']<=10**12,'ELAPSED')
        cost=row['cost_micro_usd']
        require(cost is None or (type(cost) is int and 0<=cost<=10**18),'COST')
    require(seen==selected,'PREDICTION_INVENTORY')
    return deepcopy(value)


def _new_output(path: Path, *inputs: Path) -> None:
    require(not path.exists() and not path.is_symlink(), 'OUTPUT_EXISTS')
    require(not path.resolve().is_relative_to(ROOT.parent), 'OUTPUT_INSIDE_CODE')
    for root in inputs:
        require(not path.resolve().is_relative_to(root.resolve()) and
                not root.resolve().is_relative_to(path.resolve()), 'OUTPUT_OVERLAPS_INPUT')


def _read_bundle(path: Path, expected: set[str]) -> dict[str,bytes]:
    require(not path.is_symlink(), 'BUNDLE_SYMLINK')
    marker_bytes=read_artifact(path,'COMPLETE.json')
    marker=strict_json(marker_bytes)
    fields(marker,{'schema_version','sha256'},'BUNDLE_SCHEMA')
    require(type(marker['schema_version']) is int and marker['schema_version']==1 and
            type(marker['sha256']) is dict and set(marker['sha256'])==expected, 'BUNDLE_INVENTORY')
    require({p.name for p in path.iterdir()}==expected|{'COMPLETE.json'}, 'EXTRA_BUNDLE_FILE')
    raw={name:read_artifact(path,name) for name in expected}
    require(all(sha(contents)==marker['sha256'][name] for name,contents in raw.items()), 'BUNDLE_HASH')
    raw['COMPLETE.json']=marker_bytes
    return raw


def _engine() -> dict:
    paths=('holdout_protocol.py','benchmark.py','quality.py','safe_io.py','native_runtime.py','__main__.py')
    return {'source_sha256':{p:sha(read_artifact(ROOT,p)) for p in paths},
            'native_sources':source_inventory()}


def prepare(manifest_file: Path, labels_file: Path, public_out: Path, private_out: Path) -> dict:
    _new_output(public_out,manifest_file.parent,labels_file.parent)
    _new_output(private_out,manifest_file.parent,labels_file.parent)
    require(not public_out.resolve().is_relative_to(private_out.resolve()) and
            not private_out.resolve().is_relative_to(public_out.resolve()), 'OUTPUT_OVERLAP')
    raw_manifest=read_artifact(manifest_file.parent,manifest_file.name)
    raw_labels=read_artifact(labels_file.parent,labels_file.name)
    manifest=validate_manifest(strict_json(raw_manifest))
    labels=validate_labels(strict_json(raw_labels),manifest)
    nonce=secrets.token_hex(32)
    desc=commitment(manifest,labels,nonce)
    write_new_bundle(private_out, {'labels.json':raw_labels,'nonce.json':canonical({'nonce':nonce})})
    write_new_bundle(public_out, {'manifest.json':raw_manifest,
        'commitment.json':canonical(desc),
        'README.md':b'Unlabeled inventory and SHA-256 label commitment. Not authenticated or a blind benchmark.\n'})
    public=_read_bundle(public_out,PUBLIC)
    private=_read_bundle(private_out,PRIVATE)
    require(commitment(manifest,strict_json(private['labels.json']),strict_json(private['nonce.json'])['nonce'])==desc,
            'PRIVATE_PUBLIC_MISMATCH')
    return {'status':'HOLDOUT_PREPARED','prepared_sha256':sha(public['COMPLETE.json']),
            'labels_count':len(labels['cases']),'label_data_exported_publicly':False,
            'independent_label_provenance_verified':False}


def _prepared(public_dir: Path, *, expected_sha256: str) -> tuple[dict,dict,dict]:
    hash_text(expected_sha256)
    raw=_read_bundle(public_dir,PUBLIC)
    require(sha(raw['COMPLETE.json'])==expected_sha256,'PREPARED_PIN_MISMATCH')
    manifest=validate_manifest(strict_json(raw['manifest.json']))
    com=validate_commitment(strict_json(raw['commitment.json']),manifest)
    return raw,manifest,com


def freeze(public_dir: Path, predictions_file: Path, out: Path, *, expected_prepared_sha256: str) -> dict:
    _new_output(out,public_dir,predictions_file.parent)
    prepared,manifest,_=_prepared(public_dir,expected_sha256=expected_prepared_sha256)
    raw_predictions=read_artifact(predictions_file.parent,predictions_file.name)
    validate_predictions(strict_json(raw_predictions),manifest)
    files={'manifest.json':prepared['manifest.json'], 'commitment.json':prepared['commitment.json'],
           'predictions.json':raw_predictions,
           'PREPARED.json':canonical({'prepared_sha256':expected_prepared_sha256,
                                      'manifest_sha256':sha(prepared['manifest.json']),
                                      'commitment_sha256':sha(prepared['commitment.json'])}),
           'README.md':b'Frozen predictions; labels/nonce absent. Record this marker hash externally BEFORE reveal.\n'}
    write_new_bundle(out,files)
    saved=_read_bundle(out,FROZEN)
    return {'status':'HOLDOUT_FROZEN','submission_sha256':sha(saved['COMPLETE.json']),
            'prepared_sha256':expected_prepared_sha256,'label_data_in_submission':False}


def _frozen_bytes(raw: dict[str,bytes], *, expected_prepared: str, expected_frozen: str) -> tuple[dict,dict,dict]:
    hash_text(expected_prepared);hash_text(expected_frozen)
    require(sha(raw['COMPLETE.json'])==expected_frozen,'FROZEN_PIN_MISMATCH')
    meta=strict_json(raw['PREPARED.json'])
    fields(meta,{'prepared_sha256','manifest_sha256','commitment_sha256'},'PREPARED_METADATA')
    require(meta['prepared_sha256']==expected_prepared and
            meta['manifest_sha256']==sha(raw['manifest.json']) and
            meta['commitment_sha256']==sha(raw['commitment.json']), 'PREPARED_BINDING')
    manifest=validate_manifest(strict_json(raw['manifest.json']))
    com=validate_commitment(strict_json(raw['commitment.json']),manifest)
    predictions=validate_predictions(strict_json(raw['predictions.json']),manifest)
    return manifest,com,predictions


def _make_result(manifest: dict, com: dict, predictions: dict, labels: dict, nonce: str) -> dict:
    validate_labels(labels,manifest)
    require(commitment(manifest,labels,nonce)==com,'LABEL_COMMITMENT_MISMATCH')
    corpus=assemble_corpus(manifest,labels)
    run={'schema_version':1,'run_id':predictions['run_id'], 'producer':predictions['producer'],
         'corpus_sha256':bm.digest(corpus),'evaluation_split':'test','records':predictions['records']}
    result=bm.evaluate(corpus,run)
    require(result['evaluation_split']=='test' and result['blind_evaluation_established'] is False,
            'UNEXPECTED_EVALUATION_PROFILE')
    return {'schema_version':1,'status':'COMMITTED_LABEL_EVALUATION',
            'metrics':result,'commitment_sha256':sha(canonical(com)),
            'test_case_count':com['test_cases'], 'labels_committed_before_submission_authenticated':False,
            'label_secrecy_authenticated':False,'independent_curation_authenticated':False,
            'external_target_execution':False,'original_vulnerabilities_found':False}


def _render(result: dict) -> bytes:
    counts=result['metrics']['overall']['counts']
    return ('# Evaluacion con etiquetas separadas\n\n'
            f"Casos evaluados: {result['test_case_count']}. "
            + ', '.join(f'{k}={v}' for k,v in counts.items()) + '\n\n'
            'Las etiquetas no estuvieron dentro del paquete de predicciones congelado.\n'
            'No se autentica el orden temporal, la ceguera, la independencia de etiquetas ni la ejecucion del detector.\n'
            'Las pruebas sobre corpus propio no son evidencia de superioridad ni de hallazgos nuevos.\n').encode()


def score(frozen_dir: Path, private_dir: Path, out: Path, *, expected_prepared: str, expected_frozen: str) -> dict:
    _new_output(out,frozen_dir,private_dir)
    frozen=_read_bundle(frozen_dir,FROZEN)
    manifest,com,predictions=_frozen_bytes(frozen,expected_prepared=expected_prepared,expected_frozen=expected_frozen)
    private=_read_bundle(private_dir,PRIVATE)
    labels=strict_json(private['labels.json'])
    nonce_data=strict_json(private['nonce.json'])
    fields(nonce_data,{'nonce'},'NONCE_SCHEMA')
    result=_make_result(manifest,com,predictions,labels,nonce_data['nonce'])
    engine=_engine()
    audit=bm._audit(result['metrics'])
    require(engine==_engine(), 'ENGINE_CHANGED_DURING_SCORE')
    payload={k:frozen[k] for k in ('manifest.json','commitment.json','predictions.json','PREPARED.json')}
    payload.update({'FROZEN.json':frozen['COMPLETE.json'],
                    'labels.json':private['labels.json'], 'nonce.json':private['nonce.json'],
                    'evaluation.json':canonical(result),'audit.json':canonical(audit),
                    'ENGINE.json':canonical(engine),'REVIEW.md':_render(result)})
    write_new_bundle(out,payload)
    return verify(out,expected_prepared=expected_prepared,expected_frozen=expected_frozen)


def verify(out: Path, *, expected_prepared: str, expected_frozen: str) -> dict:
    data=_read_bundle(out,SCORED)
    frozen={name:data[name] for name in ('manifest.json','commitment.json','predictions.json','PREPARED.json')}
    frozen['README.md']=b'Frozen predictions; labels/nonce absent. Record this marker hash externally BEFORE reveal.\n'
    frozen['COMPLETE.json']=data['FROZEN.json']
    marker=strict_json(data['FROZEN.json'])
    fields(marker,{'schema_version','sha256'},'FROZEN_MARKER_SCHEMA')
    require(type(marker['schema_version']) is int and marker['schema_version']==1 and
            type(marker['sha256']) is dict and set(marker['sha256'])==FROZEN and
            all(sha(frozen[n])==marker['sha256'][n] for n in FROZEN),'FROZEN_FILES_DIFFER')
    manifest,com,predictions=_frozen_bytes(frozen,expected_prepared=expected_prepared,expected_frozen=expected_frozen)
    nonce_data=strict_json(data['nonce.json']);fields(nonce_data,{'nonce'},'NONCE_SCHEMA')
    result=_make_result(manifest,com,predictions,strict_json(data['labels.json']),nonce_data['nonce'])
    require(canonical(result)==data['evaluation.json'] and _render(result)==data['REVIEW.md'],
            'REPLAY_METRIC_DISAGREEMENT')
    bm._verify_audit(strict_json(data['audit.json']),result['metrics'])
    require(data['ENGINE.json']==canonical(_engine()),'SOURCE_IDENTITY_CHANGED')
    return result


def main(argv: list[str]|None=None) -> int:
    parser=PrivateArgumentParser(description='Offline label commitment, prediction freeze and post-freeze scoring')
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare-holdout')
    for name in ('manifest','labels','public-out','private-out'):
        p.add_argument('--'+name,type=Path,required=True)
    f=sub.add_parser('freeze-holdout')
    for name in ('public','predictions','out'):
        f.add_argument('--'+name,type=Path,required=True)
    f.add_argument('--expected-prepared-sha256',required=True)
    s=sub.add_parser('score-holdout')
    for name in ('frozen','private','out'):
        s.add_argument('--'+name,type=Path,required=True)
    v=sub.add_parser('verify-holdout')
    v.add_argument('--bundle',type=Path,required=True)
    for command in (s,v):
        command.add_argument('--expected-prepared-sha256',required=True)
        command.add_argument('--expected-frozen-sha256',required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=='prepare-holdout':
            result=prepare(args.manifest,args.labels,args.public_out,args.private_out)
        elif args.command=='freeze-holdout':
            result=freeze(args.public,args.predictions,args.out,expected_prepared_sha256=args.expected_prepared_sha256)
        elif args.command=='score-holdout':
            result=score(args.frozen,args.private,args.out,expected_prepared=args.expected_prepared_sha256,
                         expected_frozen=args.expected_frozen_sha256)
        else:
            result=verify(args.bundle,expected_prepared=args.expected_prepared_sha256,
                          expected_frozen=args.expected_frozen_sha256)
        response={'status':result['status'],'vulnerability_confirmed':False}
        for field in ('prepared_sha256','submission_sha256','labels_count','test_case_count'):
            if field in result:response[field]=result[field]
        if 'metrics' in result:
            response['counts']=result['metrics']['overall']['counts']
        print(json.dumps(response))
        return 0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError,OverflowError,RecursionError):
        print(json.dumps({'status':'HOLDOUT_REJECTED','vulnerability_confirmed':False}))
        return 2


if __name__=='__main__':
    raise SystemExit(main())
