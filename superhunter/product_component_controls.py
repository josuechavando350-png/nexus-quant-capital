"""Run selected, fixed defensive checks and connect their verified observations to the product index."""
from concurrent.futures import ThreadPoolExecutor
from functools import cache
from importlib import import_module
import subprocess

from .product_reasoning import EvidenceError
from .product_review import ROOT, sha
from .safe_io import canonical, read_artifact, strict_json


DOMAINS = {'evidence-codec': 'product_evidence_codec', 'changes': 'product_change_batch', 'evm': 'product_evm_standards_batch',
           'infrastructure': 'product_infra_batch', 'diagnostics': 'product_languages_batch',
           'supply': 'product_trust_batch', 'source-extracts': 'product_passive_source_batch',
           'android-policy': 'product_attestations_batch', 'state-amounts': 'product_state_formats_batch',
           'remediation': 'product_remediation_batch', 'configuration': 'product_config_batch',
           'object-format': 'product_formats_batch', 'slot-format': 'product_slot_formats_batch',
           'scoring': 'product_evaluation_batch', 'timeline': 'product_timeline_formats',
           'static-contracts': 'product_static_contracts', 'build-compatibility': 'product_build_compatibility'}
CONTRACT_PATH = 'superhunter/product_supply/component-control-contracts.json'
CONTRACT_SHA = '7ad5ed1a7c4a344bb1b8d1467a3ad109b618fa1a82f67c6486cbcafa2b39105a'
FIELD = 'component_control_receipt'


@cache
def contracts():
    raw = read_artifact(ROOT, CONTRACT_PATH)
    if sha(raw) != CONTRACT_SHA:
        raise EvidenceError('component control acceptance contract differs')
    return strict_json(raw)


def receipt_for(name, observed):
    rule = contracts()[name]
    if not isinstance(observed, dict) or observed.get('revision') != rule['revision']:
        raise EvidenceError('component control producer revision differs')
    digest = sha(canonical(observed))
    if digest != rule['result_sha256']:
        raise EvidenceError('component control result differs from its reviewed evidence')
    return {'domain': rule['domain'], 'revision': rule['revision'], 'result_sha256': digest}


def role_for(row):
    name = row['repository']
    rule = contracts().get(name)
    if rule is None or row[FIELD] != {k: rule[k] for k in ('domain', 'revision', 'result_sha256')}:
        raise EvidenceError('component control row differs from the accepted result')
    return rule['role'], FIELD


def validate_group(domain, rows):
    expected = {name for name, rule in contracts().items() if rule['domain'] == domain}
    if not expected or not isinstance(rows, dict) or set(rows) != expected:
        raise EvidenceError('component control producer returned missing or unexpected subjects')
    return {name: receipt_for(name, rows[name]) for name in sorted(expected)}



def reconcile_digest(results, go_report):
    """Join a live detector, an independent rule catalog and the reconstructed source bytes."""
    taxonomy = results.get('find-sec-bugs/find-sec-bugs')
    repaired = results.get('OpenHands/software-agent-sdk')
    if taxonomy is None or repaired is None or go_report is None:
        return {}
    classifications = taxonomy['result']['classification']
    observation, = go_report['diagnostics']
    changed = classifications['changed']
    fix = repaired['result']
    if (str(changed['taxonomy']['cwe']) != observation['cwe'] or observation != fix['diagnostic']
            or observation['line'] != changed['line'] or changed['line'] not in fix['lines']
            or fix['before_sha256'] != changed['source_sha256']
            or fix['after_sha256'] != classifications['original']['source_sha256']
            or sorted(go_report['clean_cases']) != sorted(k for k,v in classifications.items() if v['pattern'] is None)
            or {k:v['source_sha256'] for k,v in classifications.items()} != go_report['inputs_sha256']):
        raise EvidenceError('detector, taxonomy and reconstructed source disagree')
    return {'rule': observation['rule'], 'cwe': observation['cwe'], 'line': changed['line'],
            'before_sha256': fix['before_sha256'], 'restored_sha256': fix['after_sha256'],
            'subjects': ['securego/gosec', 'find-sec-bugs/find-sec-bugs', 'OpenHands/software-agent-sdk']}


def attach(index, checkout, domain, kit):
    if checkout is None:
        raise EvidenceError('component controls require --control-source-root or --source-references with a verified checkout')
    wanted = tuple(sorted(DOMAINS)) if domain == 'all' else (domain,)
    root = checkout.resolve(strict=True)/'upstream'

    def run(group):
        engine = import_module('.' + DOMAINS[group], __package__)
        if group == 'changes':
            return engine.review(root, kit, index.header_digest)
        return engine.review(root)

    results = {}
    errors = {}
    with ThreadPoolExecutor(max_workers=min(3, len(wanted))) as pool:
        futures = {group: pool.submit(run, group) for group in wanted}
        for group, future in futures.items():
            try:
                rows = future.result()
                receipts = validate_group(group, rows)
                if any(name.casefold() not in index.repos for name in rows):
                    raise EvidenceError('component control subject absent from catalog')
            except (ValueError, KeyError, OSError, ImportError, subprocess.SubprocessError) as error:
                errors[group] = type(error).__name__ + ': ' + str(error)[:500]
                continue
            for name, value in receipts.items():
                index.repos[name.casefold()][FIELD] = value
            results.update(rows)
    index.component_controls = {'requested': list(wanted), 'blocked': errors, 'observations': results,
                                'digest_corroboration': reconcile_digest(results, getattr(index, 'header_digest', None))}
