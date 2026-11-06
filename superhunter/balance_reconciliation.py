"""Exact, offline reconciliation of supplied token balances and declared flows.

This is accounting, not an EVM executor, exploit planner or funds-at-risk
estimator. Completeness, prices, chain anchors and commit are declarations.
Two arithmetic implementations must agree; both share this input model.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal, Context, localcontext, Inexact, DecimalException
import hashlib
import json
from pathlib import Path
import re
import uuid

from .native_runtime import load_components
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle, MAX_BYTES

ROOT = Path(__file__).resolve().parent
MODEL = 'declared-token-ledger-v1'
MAX_ASSETS, MAX_ACCOUNTS, MAX_FLOWS = 16, 32, 2048
IDENTIFIER = re.compile(r'[a-z][a-z0-9_.-]{0,63}\Z')
ATOM = re.compile(r'(?:0|[1-9][0-9]{0,77})\Z')
PRICE = re.compile(r'(?:0|[1-9][0-9]{0,35})(?:\.[0-9]{1,18})?\Z')
HASH = re.compile(r'[0-9a-f]{64}\Z')
ADDRESS = re.compile(r'0x[0-9a-f]{40}\Z')
FILES = {'input.json', 'analysis.json', 'audit.json', 'receipt.json', 'REVIEW.md'}
CODE_FILES = ('balance_reconciliation.py', 'native_runtime.py', 'safe_io.py', 'privacy.py')


class AccountingError(ValueError):
    """Only stable diagnostic codes; input data is not echoed."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise AccountingError(code)


def fields(value: object, keys: set[str]) -> None:
    require(type(value) is dict and set(value) == keys, 'SCHEMA_MISMATCH')


def identifier(value: object) -> None:
    require(type(value) is str and IDENTIFIER.fullmatch(value) is not None, 'IDENTIFIER_INVALID')


def uint(value: object) -> int:
    require(type(value) is str and ATOM.fullmatch(value) is not None, 'ATOMIC_AMOUNT_FORMAT')
    amount = int(value)
    require(amount < 2**256, 'ATOMIC_AMOUNT_OVERFLOW')
    return amount


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def validate(data: object) -> dict:
    fields(data, {'schema_version', 'model', 'case_id', 'subject', 'assets', 'accounts',
                  'before', 'after', 'flows', 'flow_coverage', 'prices'})
    require(type(data['schema_version']) is int and data['schema_version'] == 1, 'SCHEMA_VERSION')
    require(data['model'] == MODEL, 'MODEL_UNSUPPORTED')
    identifier(data['case_id'])
    subject = data['subject']
    fields(subject, {'repo', 'commit', 'chain_id', 'anchor'})
    require(type(subject['repo']) is str and re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', subject['repo']) is not None
            and len(subject['repo']) <= 256, 'REPO_INVALID')
    require(type(subject['commit']) is str and re.fullmatch('[0-9a-f]{40}', subject['commit']) is not None, 'COMMIT_INVALID')
    require(type(subject['chain_id']) is int and 0 < subject['chain_id'] < 2**64, 'CHAIN_INVALID')
    fields(subject['anchor'], {'block_number', 'block_hash'})
    anchor = subject['anchor']
    require(type(anchor['block_number']) is int and 0 <= anchor['block_number'] < 2**64, 'BLOCK_INVALID')
    require(type(anchor['block_hash']) is str and re.fullmatch('0x[0-9a-f]{64}', anchor['block_hash']) is not None,
            'BLOCK_HASH_INVALID')
    assets, accounts = data['assets'], data['accounts']
    require(type(assets) is dict and 1 <= len(assets) <= MAX_ASSETS, 'ASSET_LIMIT')
    require(type(accounts) is list and 1 <= len(accounts) <= MAX_ACCOUNTS, 'ACCOUNT_LIMIT')
    for name in accounts:
        identifier(name)
    require(len(set(accounts)) == len(accounts), 'DUPLICATE_ACCOUNT')
    token_addresses = set()
    for name, item in assets.items():
        identifier(name); fields(item, {'token', 'decimals'})
        require(type(item['token']) is str and ADDRESS.fullmatch(item['token']) is not None, 'TOKEN_INVALID')
        require(item['token'] not in token_addresses, 'DUPLICATE_TOKEN')
        token_addresses.add(item['token'])
        require(type(item['decimals']) is int and 0 <= item['decimals'] <= 255, 'DECIMALS_REQUIRED')
    for label in ('before', 'after'):
        snapshot = data[label]
        fields(snapshot, set(assets))
        for balances in snapshot.values():
            fields(balances, set(accounts))  # Missing is unknown, NOT zero.
            for value in balances.values():
                uint(value)
    require(data['flow_coverage'] in ('declared_complete', 'declared_incomplete'), 'FLOW_COVERAGE_INVALID')
    flows = data['flows']
    require(type(flows) is list and len(flows) <= MAX_FLOWS, 'FLOW_LIMIT')
    seen = set()
    for flow in flows:
        fields(flow, {'id', 'asset', 'from', 'to', 'amount_atomic'})
        identifier(flow['id']); require(flow['id'] not in seen, 'DUPLICATE_FLOW'); seen.add(flow['id'])
        require(type(flow['asset']) is str and flow['asset'] in assets, 'UNKNOWN_ASSET')
        for key in ('from', 'to'):
            require(flow[key] is None or type(flow[key]) is str and flow[key] in accounts, 'UNKNOWN_ACCOUNT')
        require(flow['from'] != flow['to'], 'FLOW_ENDPOINTS_INVALID')
        require(uint(flow['amount_atomic']) > 0, 'ZERO_FLOW')
    prices = data['prices']
    require(type(prices) is dict and set(prices) <= set(assets), 'PRICE_ASSET_UNKNOWN')
    for quote in prices.values():
        fields(quote, {'usd_per_token', 'source_sha256', 'as_of_unix'})
        value = quote['usd_per_token']
        require(type(value) is str and PRICE.fullmatch(value) is not None and Decimal(value) > 0, 'PRICE_INVALID')
        require(type(quote['source_sha256']) is str and HASH.fullmatch(quote['source_sha256']) is not None, 'PRICE_SOURCE_INVALID')
        require(type(quote['as_of_unix']) is int and 0 <= quote['as_of_unix'] < 2**63, 'PRICE_TIME_INVALID')
    require(len(canonical(data)) <= MAX_BYTES, 'INPUT_TOO_LARGE')
    return deepcopy(data)


def fixed(value: int, scale: int) -> str:
    """Exact signed base-ten rendering by integer arithmetic; never float."""
    sign = '-' if value < 0 else ''
    digits = str(abs(value)).rjust(scale + 1, '0')
    if scale:
        digits = (digits[:-scale] + '.' + digits[-scale:]).rstrip('0').rstrip('.')
    return sign + digits if value else '0'


def _price_units(quote: dict) -> tuple[int, int]:
    whole, _, fraction = quote['usd_per_token'].partition('.')
    return int(whole + fraction), len(fraction)


def _primary(model: dict) -> dict:
    """Aggregate signed flow effects in one pass, preserving per-asset units."""
    effects = {(asset, account): 0 for asset in model['assets'] for account in model['accounts']}
    boundary = {asset: 0 for asset in model['assets']}
    for flow in model['flows']:
        amount, asset = int(flow['amount_atomic']), flow['asset']
        if flow['from'] is not None:
            effects[asset, flow['from']] -= amount
        else:
            boundary[asset] += amount
        if flow['to'] is not None:
            effects[asset, flow['to']] += amount
        else:
            boundary[asset] -= amount
    rows, totals, usd_terms = [], [], []
    for asset, metadata in sorted(model['assets'].items()):
        observed_total, residual_total = 0, 0
        for account in sorted(model['accounts']):
            before, after = int(model['before'][asset][account]), int(model['after'][asset][account])
            observed, expected = after - before, effects[asset, account]
            observed_total += observed; residual_total += observed - expected
            quote = model['prices'].get(asset)
            usd = None
            if quote is not None:
                price, scale = _price_units(quote)
                usd = fixed(observed * price, metadata['decimals'] + scale)
            rows.append({'asset': asset, 'account': account, 'before_atomic': str(before), 'after_atomic': str(after),
                         'observed_delta_atomic': str(observed), 'explained_delta_atomic': str(expected),
                         'residual_atomic': str(observed - expected),
                         'observed_delta_tokens': fixed(observed, metadata['decimals']), 'declared_price_usd_delta': usd})
        totals.append({'asset': asset, 'observed_delta_atomic': str(observed_total),
                       'external_net_atomic': str(boundary[asset]), 'residual_atomic': str(residual_total)})
        if asset in model['prices']:
            price, scale = _price_units(model['prices'][asset])
            usd_terms.append((observed_total * price, metadata['decimals'] + scale))
    total_usd = None
    if len(usd_terms) == len(model['assets']):
        max_scale = max(scale for _, scale in usd_terms)
        total_usd = fixed(sum(v * 10**(max_scale-s) for v, s in usd_terms), max_scale)
    return {'rows': rows, 'asset_totals': totals, 'declared_price_usd_total_delta': total_usd}


def _reference(model: dict) -> dict:
    """Per-cell Decimal equations with exactness traps, no primary aggregation.

    Independent calculation path, but same input and model: not independent
    on-chain evidence or proof of implementation correctness.
    """
    with localcontext(Context(prec=512, Emin=-999999, Emax=999999)) as ctx:
        ctx.traps[Inexact] = True
        def fmt(value: Decimal) -> str:
            if value.is_zero():
                return '0'
            s = format(value, 'f')
            return s.rstrip('0').rstrip('.') if '.' in s else s
        rows, totals = [], []
        priced_total = Decimal(0)
        for asset in sorted(model['assets']):
            deltas = []
            for account in sorted(model['accounts']):
                before, after = Decimal(model['before'][asset][account]), Decimal(model['after'][asset][account])
                credits = sum((Decimal(f['amount_atomic']) for f in model['flows'] if f['asset']==asset and f['to']==account), Decimal(0))
                debits = sum((Decimal(f['amount_atomic']) for f in model['flows'] if f['asset']==asset and f['from']==account), Decimal(0))
                observed, explained = after-before, credits-debits
                deltas.append(observed)
                normalized = observed / Decimal(10)**model['assets'][asset]['decimals']
                usd = None
                if asset in model['prices']:
                    usd_value = normalized * Decimal(model['prices'][asset]['usd_per_token'])
                    priced_total += usd_value; usd = fmt(usd_value)
                rows.append({'asset':asset,'account':account,'before_atomic':str(before),'after_atomic':str(after),
                             'observed_delta_atomic':fmt(observed),'explained_delta_atomic':fmt(explained),
                             'residual_atomic':fmt(observed-explained), 'observed_delta_tokens':fmt(normalized),
                             'declared_price_usd_delta':usd})
            incoming = sum((Decimal(f['amount_atomic']) for f in model['flows'] if f['asset']==asset and f['from'] is None), Decimal(0))
            outgoing = sum((Decimal(f['amount_atomic']) for f in model['flows'] if f['asset']==asset and f['to'] is None), Decimal(0))
            total = sum(deltas, Decimal(0))
            totals.append({'asset':asset,'observed_delta_atomic':fmt(total),'external_net_atomic':fmt(incoming-outgoing),
                           'residual_atomic':fmt(total-incoming+outgoing)})
        return {'rows':rows,'asset_totals':totals,
                'declared_price_usd_total_delta':fmt(priced_total) if set(model['prices'])==set(model['assets']) else None}


def reconcile(data: object) -> dict:
    model = validate(data)
    primary, reference = _primary(model), _reference(model)
    require(canonical(primary) == canonical(reference), 'ARITHMETIC_DISAGREEMENT')
    unexplained = sum(row['residual_atomic'] != '0' for row in primary['rows'])
    status = ('ACCOUNTING_INCONCLUSIVE' if model['flow_coverage'] == 'declared_incomplete' else
              'ACCOUNTING_MISMATCH' if unexplained else 'ACCOUNTING_RECONCILED')
    return {'schema_version':1,'model':MODEL,'input_sha256':digest(canonical(model)), 'status':status,
            'cells_checked':len(primary['rows']), 'unexplained_cells':unexplained, **primary,
            'valuation_complete':set(model['prices'])==set(model['assets']), 'prices_authenticated':False,
            'price_freshness_verified':False, 'execution_verified':False, 'coverage_authenticated':False,
            'vulnerability_confirmed':False, 'funds_at_risk_usd':None, 'attacker_profit_usd':None,
            'final_severity':None, 'human_review_required':True}


def code_digest() -> str:
    return digest(canonical({p:digest(read_artifact(ROOT,p)) for p in CODE_FILES}))


def render(result: dict) -> bytes:
    # Keep display free of untrusted identifiers/quotes. Original data is private.
    return ('# Conciliación económica local\n\n'
            f"Estado: {result['status']}\nCeldas comprobadas: {result['cells_checked']}\n"
            f"Celdas con diferencias sin explicar: {result['unexplained_cells']}\n\n"
            'El saldo final se contrasta con el inicial y los movimientos declarados, por cuenta y activo.\n'
            'No se presupone que un saldo faltante sea cero ni que todos los tokens tengan 18 decimales.\n'
            'Los importes USD usan únicamente precios suministrados; no se verifica precio, vigencia o proveedor.\n'
            'No es una prueba de explotación, un cálculo de fondos robables ni una clasificación de severidad.\n'
            'La cobertura y los estados son declarados. No se ejecutó EVM ni se consultó una red.\n').encode()


def _events(run_id: str, result: dict) -> list[tuple[str, dict]]:
    return [('accounting.start', {'run_id':run_id,'input_sha256':result['input_sha256'],'model':MODEL})] + [
        ('accounting.asset', {'index':i,'result_sha256':digest(canonical(row))}) for i,row in enumerate(result['asset_totals'])] + [
        ('accounting.complete', {'run_id':run_id,'result_sha256':digest(canonical(result)),
                                 'status':result['status'],'vulnerability_confirmed':False})]


def create_bundle(data: object, out: Path, *, original_bytes: bytes | None = None) -> dict:
    require(not out.exists() and not out.is_symlink(), 'OUTPUT_EXISTS')
    require(not out.resolve().is_relative_to(ROOT.parent), 'OUTPUT_INSIDE_CODE')
    model = validate(data); before = code_digest(); result = reconcile(model)
    input_bytes = canonical(model) if original_bytes is None else original_bytes
    require(type(input_bytes) is bytes and canonical(strict_json(input_bytes)) == canonical(model), 'ORIGINAL_INPUT_MISMATCH')
    native = load_components(); audit = native.audit.AuditLog(); run_id = str(uuid.uuid4())
    for event, values in _events(run_id, result):
        audit.append(event, values)
    audit.assert_intact(); require(before == code_digest(), 'CODE_CHANGED')
    receipt = {'schema_version':1,'run_id':run_id,'code_sha256':before, 'audit_head':audit.head,
               'native_sources':list(native.provenance)}
    write_new_bundle(out, {'input.json':input_bytes,'analysis.json':canonical(result),
                          'audit.json':canonical({'entries':[asdict(e) for e in audit.entries]}),
                          'receipt.json':canonical(receipt),'REVIEW.md':render(result)})
    return verify_bundle(out)


def verify_bundle(root: Path) -> dict:
    marker = strict_json(read_artifact(root,'COMPLETE.json')); fields(marker,{'schema_version','sha256'})
    require(type(marker['schema_version']) is int and marker['schema_version']==1, 'SCHEMA_VERSION')
    fields(marker['sha256'],FILES)
    require({p.name for p in root.iterdir()}==FILES|{'COMPLETE.json'}, 'BUNDLE_FILES_MISMATCH')
    raw = {name:read_artifact(root,name) for name in sorted(FILES)}
    require(all(digest(value)==marker['sha256'][name] for name,value in raw.items()), 'ARTIFACT_CHANGED')
    before = code_digest(); result = reconcile(strict_json(raw['input.json']))
    require(raw['analysis.json']==canonical(result) and raw['REVIEW.md']==render(result), 'RESULT_MISMATCH')
    receipt = strict_json(raw['receipt.json']); fields(receipt,{'schema_version','run_id','code_sha256','audit_head','native_sources'})
    require(type(receipt['schema_version']) is int and receipt['schema_version']==1, 'SCHEMA_VERSION')
    require(type(receipt['run_id']) is str and str(uuid.UUID(receipt['run_id']))==receipt['run_id'], 'RUN_ID_INVALID')
    require(receipt['code_sha256']==before, 'STALE_CODE')
    native = load_components()
    require(canonical(receipt['native_sources'])==canonical(list(native.provenance)), 'NATIVE_SOURCE_MISMATCH')
    journal = strict_json(raw['audit.json']); fields(journal,{'entries'}); entries=journal['entries']
    expected = _events(receipt['run_id'],result)
    require(type(entries) is list and len(entries)==len(expected), 'AUDIT_COUNT')
    previous, timestamp = '0'*64, None
    for index,(entry,(event,values)) in enumerate(zip(entries,expected)):
        fields(entry,{'index','timestamp','event','data','prev_hash','hash'})
        require(type(entry['index']) is int and entry['index']==index, 'AUDIT_INDEX')
        require(entry['event']==event and canonical(entry['data'])==canonical(values), 'AUDIT_SEMANTICS')
        require(type(entry['timestamp']) is str, 'AUDIT_TIME')
        current=datetime.fromisoformat(entry['timestamp'])
        require(current.tzinfo is not None and (timestamp is None or current>=timestamp), 'AUDIT_TIME')
        require(entry['prev_hash']==previous and native.audit.AuditEntry(**entry).recompute()==entry['hash'], 'AUDIT_CHAIN')
        previous,timestamp=entry['hash'],current
    require(previous==receipt['audit_head'], 'AUDIT_HEAD')
    require(code_digest()==before, 'CODE_CHANGED')
    return {'status':result['status'],'input_sha256':result['input_sha256'],
            'cells_checked':result['cells_checked'],'unexplained_cells':result['unexplained_cells'],
            'valuation_complete':result['valuation_complete'],'execution_verified':False,'vulnerability_confirmed':False}


def example_input() -> dict:
    """Benign constructed accounting fixture; never claimed to be blockchain data."""
    return {'schema_version':1,'model':MODEL,'case_id':'synthetic.cashflow',
            'subject':{'repo':'local/fixtures','commit':'1'*40,'chain_id':31337,
                       'anchor':{'block_number':1,'block_hash':'0x'+'a'*64}},
            'assets':{'usd6':{'token':'0x'+'1'*40,'decimals':6},'eth18':{'token':'0x'+'2'*40,'decimals':18}},
            'accounts':['vault','alice','fee'],
            'before':{'usd6':{'vault':'1000000000','alice':'500000000','fee':'0'},
                      'eth18':{'vault':'2000000000000000000','alice':'1000000000000000000','fee':'0'}},
            'after':{'usd6':{'vault':'1124000000','alice':'400000000','fee':'1000000'},
                     'eth18':{'vault':'1900000000000000000','alice':'1090000000000000000','fee':'0'}},
            'flows':[{'id':'deposit','asset':'usd6','from':'alice','to':'vault','amount_atomic':'100000000'},
                     {'id':'fee','asset':'usd6','from':'vault','to':'fee','amount_atomic':'1000000'},
                     {'id':'withdraw','asset':'eth18','from':'vault','to':'alice','amount_atomic':'100000000000000000'},
                     {'id':'incoming','asset':'usd6','from':None,'to':'vault','amount_atomic':'25000000'},
                     {'id':'outgoing','asset':'eth18','from':'alice','to':None,'amount_atomic':'10000000000000000'}],
            'flow_coverage':'declared_complete',
            'prices':{'usd6':{'usd_per_token':'1','source_sha256':'a'*64,'as_of_unix':1},
                      'eth18':{'usd_per_token':'2500','source_sha256':'b'*64,'as_of_unix':1}}}


# Only these benign, built-in accounting controls are run by review-platform.
EXAMPLE_NAMES = ('balanced', 'one_unit_gap', 'incomplete')
EXAMPLE_INPUT_FILES = tuple(sorted(
    [f'{name}/{file}' for name in EXAMPLE_NAMES for file in FILES | {'COMPLETE.json'}] +
    ['summary/COMPLETE.json', 'summary/result.json']))


def example_controls() -> dict[str, dict]:
    good = example_input()
    gap = deepcopy(good)
    gap['after']['usd6']['vault'] = str(int(gap['after']['usd6']['vault']) + 1)
    incomplete = deepcopy(good)
    incomplete['flow_coverage'] = 'declared_incomplete'
    incomplete['flows'] = [f for f in incomplete['flows'] if f['id'] != 'incoming']
    return {'balanced': good, 'one_unit_gap': gap, 'incomplete': incomplete}


def _lab_summary(results: dict[str, dict]) -> dict:
    require(tuple(results) == EXAMPLE_NAMES, 'CONTROL_INVENTORY')
    for name, status, count in (('balanced','ACCOUNTING_RECONCILED',0),
                               ('one_unit_gap','ACCOUNTING_MISMATCH',1),
                               ('incomplete','ACCOUNTING_INCONCLUSIVE',1)):
        require(results[name]['status'] == status and results[name]['unexplained_cells'] == count,
                'ACCOUNTING_CONTROL_FAILED')
    return {'schema_version':1,'status':'LOCAL_ACCOUNTING_CONTROLS_PASS',
            'cases_checked':3,'cells_checked':18,'fixture_only':True,
            'controls':results,'vulnerability_confirmed':False}


def run_examples(out: Path) -> dict:
    require(not out.exists() and not out.is_symlink(), 'OUTPUT_EXISTS')
    require(not out.resolve().is_relative_to(ROOT.parent), 'OUTPUT_INSIDE_CODE')
    out.parent.mkdir(parents=True,exist_ok=True);out.mkdir(mode=0o700)
    results = {name:create_bundle(model,out/name) for name,model in example_controls().items()}
    summary = _lab_summary(results)
    write_new_bundle(out/'summary', {'result.json':canonical(summary)})
    return verify_examples(out)


def verify_examples(root: Path) -> dict:
    require({p.name for p in root.iterdir()} == set(EXAMPLE_NAMES) | {'summary'}, 'CONTROL_DIRECTORY_SET')
    expected_models = example_controls(); results = {}
    for name in EXAMPLE_NAMES:
        require(read_artifact(root/name,'input.json') == canonical(expected_models[name]), 'CONTROL_INPUT_CHANGED')
        results[name] = verify_bundle(root/name)
    expected = _lab_summary(results)
    marker = strict_json(read_artifact(root/'summary','COMPLETE.json'))
    fields(marker, {'schema_version','sha256'}); fields(marker['sha256'],{'result.json'})
    require(type(marker['schema_version']) is int and marker['schema_version']==1, 'SCHEMA_VERSION')
    require({p.name for p in (root/'summary').iterdir()} == {'COMPLETE.json','result.json'}, 'CONTROL_SUMMARY_FILES')
    raw = read_artifact(root/'summary','result.json')
    require(digest(raw) == marker['sha256']['result.json'] and raw == canonical(expected), 'CONTROL_SUMMARY_CHANGED')
    return expected


def main(argv: list[str]) -> int:
    parser=PrivateArgumentParser(description='Reconcile supplied local balances; no network, trading or exploit execution')
    sub=parser.add_subparsers(dest='command',required=True)
    make=sub.add_parser('reconcile-balances');make.add_argument('--input',type=Path,required=True);make.add_argument('--out',type=Path,required=True)
    sub.add_parser('verify-balances').add_argument('--bundle',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=='reconcile-balances':
            original = read_artifact(args.input.parent,args.input.name)
            result = create_bundle(strict_json(original),args.out,original_bytes=original)
        else:
            result = verify_bundle(args.bundle)
        print(json.dumps(result,sort_keys=True))
        return 0 if result['status']=='ACCOUNTING_RECONCILED' else 1
    except (ValueError,OSError,TypeError,KeyError,AttributeError,RecursionError,DecimalException):
        print(json.dumps({'status':'ACCOUNTING_ERROR','error_code':'INVALID_ACCOUNTING_OR_EVIDENCE','vulnerability_confirmed':False}))
        return 2


if __name__=='__main__':
    import sys
    raise SystemExit(main(sys.argv[1:]))


def reconcile_internal_units(before: object, after: object, transfers: object, *,
                             coverage: str = 'declared_complete') -> dict:
    """Reuse the two accounting paths for NONMONETARY internal variables.

    No token, address, chain, block hash, price or commit is invented to fit the
    token-ledger schema. This narrow arithmetic API proves only the equations of
    its supplied model; the caller must establish where the observations came from.
    Transfers are internal, positive, uint256 amounts with exact account identities.
    """
    require(type(before) is dict and 1 <= len(before) <= MAX_ACCOUNTS, 'UNIT_ACCOUNTS')
    require(all(type(k) is str for k in before), 'UNIT_ACCOUNTS')
    fields(after, set(before))
    for account in before:
        identifier(account); uint(before[account]); uint(after[account])
    require(type(coverage) is str and coverage in ('declared_complete', 'declared_incomplete'), 'FLOW_COVERAGE_INVALID')
    require(type(transfers) is list and len(transfers) <= MAX_FLOWS, 'FLOW_LIMIT')
    ids, flows = set(), []
    for transfer in transfers:
        fields(transfer, {'id', 'from', 'to', 'amount_units'})
        identifier(transfer['id'])
        require(transfer['id'] not in ids, 'DUPLICATE_FLOW'); ids.add(transfer['id'])
        for key in ('from', 'to'):
            require(type(transfer[key]) is str and transfer[key] in before, 'UNKNOWN_ACCOUNT')
        require(transfer['from'] != transfer['to'], 'FLOW_ENDPOINTS_INVALID')
        require(uint(transfer['amount_units']) > 0, 'ZERO_FLOW')
        flows.append({'id': transfer['id'], 'asset': 'unit', 'from': transfer['from'],
                      'to': transfer['to'], 'amount_atomic': transfer['amount_units']})
    supplied = {'before': before, 'after': after, 'transfers': transfers, 'coverage': coverage}
    require(len(canonical(supplied)) <= MAX_BYTES, 'INPUT_TOO_LARGE')
    # Adapter for arithmetic only: _primary/_reference read no token identities.
    model = {'assets': {'unit': {'decimals': 0}}, 'accounts': sorted(before),
             'before': {'unit': before}, 'after': {'unit': after}, 'flows': flows, 'prices': {}}
    primary, reference = _primary(model), _reference(model)
    require(canonical(primary) == canonical(reference), 'ARITHMETIC_DISAGREEMENT')
    rows = [{'account': r['account'], 'before_units': r['before_atomic'],
             'after_units': r['after_atomic'], 'observed_delta_units': r['observed_delta_atomic'],
             'explained_delta_units': r['explained_delta_atomic'], 'residual_units': r['residual_atomic']}
            for r in primary['rows']]
    bad = sum(r['residual_units'] != '0' for r in rows)
    return {'profile': 'internal-unit-equations-v1', 'input_sha256': digest(canonical(supplied)),
            'status': 'UNIT_BALANCES_INCONCLUSIVE' if coverage != 'declared_complete' else
                      'UNIT_BALANCES_MISMATCH' if bad else 'UNIT_BALANCES_RECONCILED',
            'rows': rows, 'unexplained_cells': bad,
            'total_delta_units': primary['asset_totals'][0]['observed_delta_atomic'],
            'monetary_valuation_usd': None, 'token_balances_measured': False,
            'execution_authenticated': False, 'vulnerability_confirmed': False}
