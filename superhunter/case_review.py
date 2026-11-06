"""Cross-check existing policy/static/accounting evidence for ONE declared case.

No scanner, compiler, target execution, exploit, RPC or submission. External
candidate/context pins are mandatory. Internally consistent bundles can still
refer to different cases; this module checks their explicit associations.
No claim that an alert caused a balance discrepancy, or that a PoC executed.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import tempfile

from . import balance_reconciliation as accounting
from . import program_registry as programs
from . import static_review
from . import ledger_sequence
from .bridge import candidate as validate_candidate
from .custody import capture_bundle
from .native_runtime import load_components, source_inventory
from .privacy import PrivateArgumentParser
from .safe_io import MAX_BYTES, canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
GROUPS = ('programs', 'static', 'balances')
ORDERED_GROUPS = GROUPS + ('sequence',)
OUTPUT = {'candidate.json', 'context.json', 'case.json', 'audit.json', 'REVIEW.md'}
MAX_TOTAL = 32_000_000
MAX_FILES = 512
HEX = re.compile(r'[a-f0-9]{64}\Z')
ADDRESS = re.compile(r'0x[a-f0-9]{40}\Z')
CODE_FILES = ('case_review.py', 'program_registry.py', 'static_review.py',
              'balance_reconciliation.py', 'bridge.py', 'native_runtime.py',
              'safe_io.py', 'privacy.py', 'custody.py', 'source_graph.py', 'ledger_sequence.py')
LIMITS = {'vulnerability_confirmed': False, 'final_severity': None,
          'execution_verified': False, 'program_authorization_authenticated': False,
          'source_commit_authenticated': False, 'chain_state_authenticated': False,
          'account_bindings_authenticated': False, 'causal_impact_proven': False,
          'network_execution_allowed': False, 'submission_enabled': False,
          'producer_authenticated': False, 'human_review_required': True}


class CaseError(ValueError):
    """Stable codes only; never echo a path, candidate field or report text."""


def need(condition: bool, code: str) -> None:
    if not condition:
        raise CaseError(code)


def fields(value: object, keys: set[str], code: str) -> None:
    need(type(value) is dict and set(value) == keys, code)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def engine() -> dict:
    return {'sources': {p: sha(read_artifact(ROOT, p)) for p in CODE_FILES},
            'native_sources': source_inventory()}


def context_groups(context: dict) -> tuple[str, ...]:
    """Select an explicit profile; never infer or silently drop sequence evidence."""
    need(type(context) is dict and type(context.get('schema_version')) is int and
         context['schema_version'] in (1, 2), 'CONTEXT_VERSION')
    return ORDERED_GROUPS if context['schema_version'] == 2 else GROUPS


def context_record(value: object, cand: object) -> tuple[dict, dict]:
    c = deepcopy(validate_candidate(cand))
    groups = context_groups(value)
    names = {'schema_version', 'candidate_sha256', 'platform', 'program_id',
             'chain_id', 'state_anchor', 'ledger_case_id', 'account_bindings',
             'static_fingerprint', 'evidence_manifests'}
    if value['schema_version'] == 2:
        names.add('sequence_binding')
    fields(value, names, 'CONTEXT_SCHEMA')
    if value['schema_version'] == 2:
        fields(value['sequence_binding'], {'ledger_sha256', 'sequence_sha256'}, 'SEQUENCE_BINDING_SCHEMA')
        for digest in value['sequence_binding'].values():
            need(type(digest) is str and HEX.fullmatch(digest) is not None, 'SEQUENCE_BINDING_HASH')
    need(value['candidate_sha256'] == sha(canonical(c)), 'CANDIDATE_PIN_MISMATCH')
    need(type(value['platform']) is str and value['platform'] in programs.PLATFORMS, 'PLATFORM')
    programs.ident(value['program_id'])
    need(type(value['chain_id']) is int and 0 < value['chain_id'] < 2**64, 'CHAIN_ID')
    anchor = value['state_anchor']
    fields(anchor, {'block_number', 'block_hash'}, 'ANCHOR_SCHEMA')
    need(type(anchor['block_number']) is int and 0 <= anchor['block_number'] < 2**64 and
         type(c['target']['fork_block']) is int and c['target']['fork_block'] == anchor['block_number'],
         'CANDIDATE_BLOCK_MISMATCH')
    need(type(anchor['block_hash']) is str and re.fullmatch(r'0x[a-f0-9]{64}', anchor['block_hash']) is not None,
         'BLOCK_HASH')
    accounting.identifier(value['ledger_case_id'])
    mapping = value['account_bindings']
    fields(mapping, {a.lower() for a in c['affected_contracts']}, 'AFFECTED_CONTRACT_SET')
    need(all(ADDRESS.fullmatch(a) for a in mapping), 'ADDRESS_BINDING')
    for account in mapping.values():
        accounting.identifier(account)
    need(len(set(mapping.values())) == len(mapping), 'AMBIGUOUS_ACCOUNT_BINDING')
    fingerprint = value['static_fingerprint']
    need(fingerprint is None or type(fingerprint) is str and HEX.fullmatch(fingerprint) is not None,
         'STATIC_FINGERPRINT')
    fields(value['evidence_manifests'], set(groups), 'EVIDENCE_GROUPS')
    need(all(type(v) is str and HEX.fullmatch(v) for v in value['evidence_manifests'].values()), 'EVIDENCE_PINS')
    need(len(canonical(value)) <= MAX_BYTES and len(canonical(c)) <= MAX_BYTES, 'INPUT_SIZE')
    return deepcopy(value), c


def capture(root: Path) -> dict[str, bytes]:
    """Capture a flat original bundle, no implicit files or symlink ancestors."""
    inventory = capture_bundle(root)
    need(len(inventory['artifacts']) + 1 <= MAX_FILES, 'INPUT_FILE_LIMIT')
    data = {'COMPLETE.json': read_artifact(root, 'COMPLETE.json')}
    need(sha(data['COMPLETE.json']) == inventory['manifest_sha256'], 'INPUT_CHANGED')
    for entry in inventory['artifacts']:
        raw = read_artifact(root, entry['name'])
        need(len(raw) == entry['bytes'] and sha(raw) == entry['sha256'], 'INPUT_CHANGED')
        data[entry['name']] = raw
    need(capture_bundle(root) == inventory, 'INPUT_CHANGED')
    return data


def _validate_bytes(data: object) -> None:
    need(type(data) is dict and 1 <= len(data) <= MAX_FILES, 'BUNDLE_MAP')
    total = 0
    for name, raw in data.items():
        need(type(name) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,199}', name) is not None,
             'ARTIFACT_NAME')
        need(type(raw) is bytes and len(raw) <= MAX_BYTES, 'ARTIFACT_SIZE')
        total += len(raw)
        need(total <= MAX_TOTAL, 'TOTAL_SIZE')
    need('COMPLETE.json' in data, 'MISSING_MANIFEST')
    marker = strict_json(data['COMPLETE.json'])
    fields(marker, {'schema_version', 'sha256'}, 'INNER_MANIFEST')
    need(type(marker['schema_version']) is int and marker['schema_version'] == 1, 'INNER_VERSION')
    fields(marker['sha256'], set(data) - {'COMPLETE.json'}, 'INNER_FILE_SET')
    need(all(sha(data[name]) == digest for name, digest in marker['sha256'].items()), 'INNER_HASH')


def _request_identity(requests: dict) -> list[dict]:
    return sorted(programs.validate_requests(requests)['requests'], key=lambda r: r['id'])


def evaluate(cand: dict, context: dict, captured: dict[str, dict[str, bytes]], *, at: str) -> dict:
    """Re-run semantic verifiers over the captured bytes, then enforce case links.

    Both the external context and all inputs are declarations, not facts obtained
    on-chain. This never promotes a tool severity or balance mismatch to a bug.
    """
    before = engine()
    ctx, c = context_record(context, cand)
    current = programs.timestamp(at)
    groups = context_groups(ctx)
    fields(captured, set(groups), 'CAPTURED_GROUPS')
    total = 0
    for group in groups:
        _validate_bytes(captured[group])
        total += sum(map(len, captured[group].values()))
        need(total <= MAX_TOTAL, 'TOTAL_SIZE')
        need(sha(captured[group]['COMPLETE.json']) == ctx['evidence_manifests'][group], 'EVIDENCE_PIN_MISMATCH')
    with tempfile.TemporaryDirectory(prefix='sh-case-read-') as tmp:
        dirs = {}
        for group in groups:
            target = Path(tmp) / group
            target.mkdir(mode=0o700)
            for name, raw in captured[group].items():
                p = target / name
                with p.open('xb') as f:
                    f.write(raw)
                p.chmod(0o600)
            dirs[group] = target
        policy = programs.verify_registry(dirs['programs'], at=current.isoformat())
        static = static_review.verify_report(dirs['static'])
        ledger = accounting.verify_bundle(dirs['balances'])
        ordered = None
        if ctx['schema_version'] == 2:
            ordered = ledger_sequence.verify(dirs['sequence'],
                ledger_pin=ctx['sequence_binding']['ledger_sha256'],
                sequence_pin=ctx['sequence_binding']['sequence_sha256'])
    policy_input = strict_json(captured['programs']['registry.json'])
    expected_key = ctx['platform'] + ':' + ctx['program_id']
    # A case cannot silently reuse a batch that includes different programs.
    need(len(policy_input['programs']) == 1 and
         programs.program_key(policy_input['programs'][0]) == expected_key, 'PROGRAM_CASE_MISMATCH')
    expected_requests = programs.requests_for_candidate(c, platform=ctx['platform'],
                                      program_id=ctx['program_id'], chain_id=ctx['chain_id'])
    requests = strict_json(captured['programs']['requests.json'])
    need(canonical(_request_identity(requests)) == canonical(_request_identity(expected_requests)),
         'CANDIDATE_REQUESTS_MISMATCH')
    historical = strict_json(captured['programs']['decision.json'])
    need(programs.timestamp(historical['evaluated_at']) <= current, 'FUTURE_POLICY_RECEIPT')
    need(static['repository_declared'] == {'repo': c['target']['repo'], 'commit': c['target']['commit'].lower()},
         'STATIC_TARGET_MISMATCH')
    need(static['scope_id_declared'] == c['scope_id'], 'STATIC_SCOPE_MISMATCH')
    model = accounting.validate(strict_json(captured['balances']['input.json']))
    expected_subject = {'repo': c['target']['repo'], 'commit': c['target']['commit'].lower(),
                        'chain_id': ctx['chain_id'], 'anchor': ctx['state_anchor']}
    need(canonical(model['subject']) == canonical(expected_subject), 'ACCOUNTING_TARGET_MISMATCH')
    need(model['case_id'] == ctx['ledger_case_id'], 'LEDGER_CASE_MISMATCH')
    need(set(ctx['account_bindings'].values()) <= set(model['accounts']), 'ACCOUNT_BINDING_MISSING')
    # These address->account mappings are supplied, not derived or authenticated.
    blocked, gaps, signals = [], [], []
    if ordered is not None:
        sequence_model = accounting.validate(strict_json(captured['sequence']['ledger.json']))
        need(canonical(sequence_model) == canonical(model), 'SEQUENCE_LEDGER_MISMATCH')
        need(sha(canonical(model)) == ctx['sequence_binding']['ledger_sha256'], 'SEQUENCE_LEDGER_PIN_MISMATCH')
        need(ordered.get('ledger_sha256') == ctx['sequence_binding']['ledger_sha256'] and
             ordered.get('sequence_sha256') == ctx['sequence_binding']['sequence_sha256'], 'SEQUENCE_VERIFIER_BINDING')
        need(ordered.get('aggregate_status') == ledger['status'], 'SEQUENCE_AGGREGATE_DISAGREEMENT')
        need(ordered.get('status') in ('LEDGER_SEQUENCE_CONSISTENT', 'LEDGER_SEQUENCE_INCONCLUSIVE',
                                      'LEDGER_SEQUENCE_CONTRADICTION'), 'UNKNOWN_SEQUENCE_VERDICT')
        if ordered['status'] == 'LEDGER_SEQUENCE_CONTRADICTION':
            blocked.append('DECLARED_SEQUENCE_CONTRADICTION')
            signals.append('ORDER_CONTRADICTION_NOT_A_CONFIRMED_BUG')
        elif ordered['status'] == 'LEDGER_SEQUENCE_INCONCLUSIVE':
            gaps.append('ORDERED_LEDGER_INCOMPLETE')
        else:
            need(ordered.get('full_replay_complete') is True, 'SEQUENCE_COMPLETION_DISAGREEMENT')
    for decision in policy['current_review']['decisions']:
        if decision['status'] != 'LOCAL_SCOPE_ELIGIBLE':
            blocked += decision['deny_reasons'] + decision['review_reasons']
    selected = None
    if ctx['static_fingerprint'] is not None:
        selected = next((a for a in static['alerts'] if a['fingerprint'] == ctx['static_fingerprint']), None)
        need(selected is not None, 'SELECTED_ALERT_NOT_PRESENT')
        if selected['source_bound'] is not True:
            gaps.append('STATIC_ALERT_HAS_UNBOUND_LOCATIONS')
    else:
        gaps.append('NO_STATIC_ALERT_SELECTED')
    if static['status'] == 'TOOL_ERROR':
        gaps.append('STATIC_TOOL_REPORTED_ERROR')
    if static['normalization_complete'] is not True:
        gaps.append('STATIC_NORMALIZATION_INCOMPLETE')
    if ledger['status'] == 'ACCOUNTING_INCONCLUSIVE':
        gaps.append('ACCOUNTING_COVERAGE_INCOMPLETE')
    if ledger['valuation_complete'] is not True:
        gaps.append('ACCOUNTING_VALUATION_INCOMPLETE')
    if ledger['unexplained_cells']:
        signals.append('UNEXPLAINED_BALANCE_DIFFERENCE_NOT_A_CONFIRMED_BUG')
    status = 'CASE_REVIEW_BLOCKED' if blocked else 'CASE_REVIEW_INCONCLUSIVE' if gaps else 'CASE_REVIEW_REQUIRED'
    facts = {'schema_version': ctx['schema_version'], 'status': status, 'evaluated_at': current.isoformat(),
        'candidate_id': c['id'], 'candidate_sha256': sha(canonical(c)),
        'context_sha256': sha(canonical(ctx)), 'engine': before,
        'evidence_manifests': ctx['evidence_manifests'],
        'link_checks': ['exact_candidate', 'exact_policy_request_set', 'program_and_scope',
                        'static_repo_and_commit', 'ledger_repo_commit_chain_block',
                        'declared_account_bindings'] + (['selected_static_observation'] if selected is not None else []),
        'blocked_reasons': sorted(set(blocked)), 'incomplete_reasons': sorted(set(gaps)),
        'review_signals': signals,
        'components': {'programs': {'current_counts': policy['current_review']['counts']},
                       'static': {'status': static['status'], 'selected_fingerprint': ctx['static_fingerprint'],
                                  'selected_source_bound': selected['source_bound'] if selected else None},
                       'balances': ledger},
        'sequence_required': ctx['schema_version'] == 2,
        'ordered_model_checked': ordered is not None,
        'order_authenticated': False,
        'original_inputs_retained': True, 'input_kind': static['input_kind'],
        'not_verified': ['PoC execution', 'independent vulnerability reproduction',
                         'policy authenticity or latest remote rules', 'deployed code and state',
                         'link from static alert to economic effect', 'eligibility for reward'],
        **LIMITS}
    if ordered is not None:
        facts['sequence_binding'] = deepcopy(ctx['sequence_binding'])
        facts['components']['sequence'] = ordered
        facts['link_checks'] += ['same_canonical_ledger', 'external_order_identity', 'ordered_transfer_model']
        facts['not_verified'].append('authenticity and reachability of the declared movement order')
    else:
        facts['not_verified'].append('movement order not checked in legacy profile v1')
    need(engine() == before, 'ENGINE_CHANGED')
    need(len(canonical(facts)) <= MAX_BYTES, 'OUTPUT_SIZE')
    return facts


def _audit(result: dict) -> dict:
    log = load_components().audit.AuditLog(clock=lambda: result['evaluated_at'])
    log.append('case.bind', {'candidate_sha256': result['candidate_sha256'], 'context_sha256': result['context_sha256']})
    for group in context_groups(result):
        log.append('case.evidence', {'kind': group, 'manifest_sha256': result['evidence_manifests'][group]})
    if result['schema_version'] == 2:
        log.append('case.sequence.bind', deepcopy(result['sequence_binding']))
    log.append('case.review', {'result_sha256': sha(canonical(result))})
    log.assert_intact()
    return {'entries': [asdict(e) for e in log.entries], 'head': log.head}


def render(result: dict) -> bytes:
    # All displayed text is controlled, no raw descriptions, addresses or paths.
    sequence_text = ('Orden: ' + result['components']['sequence']['status'] + '\n'
                     if result['schema_version'] == 2 else
                     'Orden: NO COMPROBADO en el perfil legado v1.\n')
    return ('# Expediente enlazado de revisión local\n\n'
        f"Estado: {result['status']}\n"
        f"{sequence_text}"
        f"Condiciones bloqueantes: {len(result['blocked_reasons'])}\n"
        f"Comprobaciones incompletas: {len(result['incomplete_reasons'])}\n"
        f"Señales contables para revisión: {len(result['review_signals'])}\n\n"
        'Se vuelven a verificar alcance declarado, fuente de la observación y conciliación de balances.\n'
        'La coincidencia de expediente no demuestra que la alerta cause una diferencia económica.\n'
        'No se ejecutó una PoC, no se confirmó una vulnerabilidad y no se asignó severidad final.\n'
        'Las fuentes y políticas originales se conservan: el paquete completo es privado.\n'
        'Verificar requiere candidato y contexto esperados obtenidos fuera de este paquete.\n').encode()


def create_case(candidate_path: Path, context_path: Path, programs_path: Path,
                static_path: Path, balances_path: Path, out: Path, *, at: str | None = None,
                sequence_path: Path | None = None) -> dict:
    need(not out.exists() and not out.is_symlink(), 'NEW_OUTPUT_REQUIRED')
    roots = dict(zip(GROUPS, (programs_path, static_path, balances_path)))
    if sequence_path is not None:
        roots['sequence'] = sequence_path
    need(not out.resolve().is_relative_to(ROOT.parent), 'OUTPUT_INSIDE_CODE')
    need(not any(out.resolve().is_relative_to(p.resolve()) for p in roots.values()), 'OUTPUT_INSIDE_INPUT')
    raw_c = read_artifact(candidate_path.parent, candidate_path.name)
    raw_ctx = read_artifact(context_path.parent, context_path.name)
    c, ctx = strict_json(raw_c), strict_json(raw_ctx)
    context_record(ctx, c)
    groups = context_groups(ctx)
    need(set(roots) == set(groups), 'SEQUENCE_ARGUMENT_PROFILE_MISMATCH')
    snapshots = {k: capture(v) for k, v in roots.items()}
    result = evaluate(c, ctx, snapshots, at=at or utc_now())
    need(all(capture(roots[g]) == snapshots[g] for g in groups), 'INPUT_CHANGED')
    need(raw_c == read_artifact(candidate_path.parent, candidate_path.name) and
         raw_ctx == read_artifact(context_path.parent, context_path.name), 'EXTERNAL_REFERENCE_CHANGED')
    payload = {group + '--' + name: raw for group, data in snapshots.items() for name, raw in data.items()}
    payload.update({'candidate.json': raw_c, 'context.json': raw_ctx, 'case.json': canonical(result),
                    'audit.json': canonical(_audit(result)), 'REVIEW.md': render(result)})
    need(len(payload) <= MAX_FILES and sum(map(len, payload.values())) <= MAX_TOTAL, 'OUTPUT_SIZE')
    write_new_bundle(out, payload)
    return result


def verify_case(root: Path, *, expected_candidate: dict, expected_context: dict, at: str | None = None) -> dict:
    """Check original evidence and replay historical AND current policy review.

    Callers must not derive expected references from this same package. CLI
    enforces separate paths; provenance/authenticity of external references
    remains the operator's responsibility. This does not trust arbitrary pins.
    """
    context_record(expected_context, expected_candidate)
    groups = context_groups(expected_context)
    data = capture(root)
    need(set(OUTPUT) <= set(data), 'CASE_FILE_SET')
    c, ctx = strict_json(data['candidate.json']), strict_json(data['context.json'])
    need(canonical(c) == canonical(expected_candidate) and canonical(ctx) == canonical(expected_context),
         'EXTERNAL_REFERENCE_MISMATCH')
    snapshots = {}
    expected_names = OUTPUT | {'COMPLETE.json'}
    for group in groups:
        subset = {name.removeprefix(group + '--'): raw for name, raw in data.items()
                  if name.startswith(group + '--')}
        _validate_bytes(subset)
        expected_names.update(group + '--' + name for name in subset)
        snapshots[group] = subset
    need(set(data) == expected_names, 'CASE_FILE_SET')
    claimed = strict_json(data['case.json'])
    now = programs.timestamp(at or utc_now())
    checked_at = programs.timestamp(claimed.get('evaluated_at'))
    need(checked_at <= now, 'FUTURE_REVIEW')
    historical = evaluate(c, ctx, snapshots, at=checked_at.isoformat())
    need(type(claimed.get('schema_version')) is int and claimed['schema_version'] == ctx['schema_version'],
         'CASE_PROFILE_MISMATCH')
    need(data['case.json'] == canonical(historical) and data['audit.json'] == canonical(_audit(historical)) and
         data['REVIEW.md'] == render(historical), 'CASE_REPLAY_MISMATCH')
    current = evaluate(c, ctx, snapshots, at=now.isoformat())
    need(capture(root) == data, 'INPUT_CHANGED')
    return {'status': current['status'], 'historical_consistency_checked': True,
            'historical_status': historical['status'], 'current_review': current, **LIMITS}


def main(argv: list[str]) -> int:
    p = PrivateArgumentParser(description='Join existing evidence for one declared case; never execute a target')
    subs = p.add_subparsers(dest='command', required=True)
    make = subs.add_parser('review-case')
    for key in ('candidate', 'context', 'programs', 'static', 'balances', 'out'):
        make.add_argument('--' + key, type=Path, required=True)
    make.add_argument('--sequence', type=Path, help='Required for explicit context schema_version=2; forbidden for v1')
    verify = subs.add_parser('verify-case')
    for key in ('bundle', 'candidate', 'context'):
        verify.add_argument('--' + key, type=Path, required=True)
    args = p.parse_args(argv)
    try:
        if args.command == 'review-case':
            r = create_case(args.candidate, args.context, args.programs, args.static, args.balances, args.out,
                            sequence_path=args.sequence)
        else:
            need(not any(v.resolve().is_relative_to(args.bundle.resolve()) for v in (args.candidate, args.context)),
                 'EXTERNAL_REFERENCE_REQUIRED')
            c = strict_json(read_artifact(args.candidate.parent, args.candidate.name))
            ctx = strict_json(read_artifact(args.context.parent, args.context.name))
            r = verify_case(args.bundle, expected_candidate=c, expected_context=ctx)
        print(json.dumps({'status': r['status'], 'vulnerability_confirmed': False, 'network_execution_allowed': False}))
        return 0 if r['status'] == 'CASE_REVIEW_REQUIRED' else 1
    except (ValueError, OSError, KeyError, TypeError, RecursionError, OverflowError):
        print(json.dumps({'status': 'CASE_EVIDENCE_REJECTED', 'vulnerability_confirmed': False}))
        return 2


if __name__ == '__main__':
    import sys
    raise SystemExit(main(sys.argv[1:]))
