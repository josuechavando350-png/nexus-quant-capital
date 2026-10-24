"""Retained fork economics: measured, modeled and paid values stay distinct.

No new EVM execution, Titan request, signing or funding occurs in this reader.
The current Titan-only policy never upgrades historical source authority.
"""
import builtins
import copy
from pathlib import Path
import re
import tempfile
from types import ModuleType

from audit import verify_plan
from cashflow_intake import load_price
from dependency_intake import STAGES, store_chain
from evidence_store import (admit, audit_store, create, export_store, read_batch,
                            restore_store, revoke)
from historical_intake import (API, AUTHORITIES, EVIDENCE, ROOT, SOURCE, SOURCE_ID,
                              fields, need, same, unpack, utc)
from integrity import canonical, digest, read_regular, strict_json
from temporal_intake import build_temporal_report, manifest, query_temporal_report

PIN_SHA256 = '3cc7362656dd3c26bfa0316dd72a27904d79b73ed80be692cddf86fd6025f287'
SCHEMA = 'nqc.omega.retained-execution-economics.v1'
REPORT_NAME = 'execution-report.json'
BINDING_NAME = 'execution-parent-batches.json'
SOURCE_NAMES = {'execution-pin.json'} | {f'execution-{k}-{suffix}'
    for k in ('fork', 'gas') for suffix in ('original.zip', 'metadata.json')}
CATEGORIES = ('PROTOCOL_FEE', 'CAPITAL_FEE', 'SWAP_FEE', 'PRICE_IMPACT', 'GAS',
    'PRIORITY_FEE', 'BUILDER_PAYMENT', 'FINANCING', 'HEDGING', 'INVENTORY',
    'EXPECTED_FAILURE_REVERT', 'OPPORTUNITY_COST', 'MEV', 'CHAIN_SPECIFIC')


def seal(value):
    value['report_commitment_sha256'] = digest(canonical(value))
    return value


def load_execution_sources(directory=EVIDENCE, root=ROOT):
    directory, root = Path(directory), Path(root)
    raw = read_regular(directory / 'execution-pin.json')
    need(digest(raw) == PIN_SHA256, 'execution_pin_changed')
    pin = strict_json(raw); need(canonical(pin) == raw, 'execution_pin_noncanonical')
    members, reports, provenance = {}, {}, {}
    for kind, p in pin['sources'].items():
        raw_meta = read_regular(directory / f'execution-{kind}-metadata.json')
        need(digest(raw_meta) == p['metadata_sha256'], 'execution_metadata_changed')
        meta = strict_json(raw_meta)
        run, commit, art = (meta[k] for k in ('run', 'commit', 'artifact'))
        fields(run, {'id': p['run_id'], 'head_sha': p['commit'], 'head_branch': p['branch'],
            'status': 'completed', 'conclusion': 'success', 'run_attempt': 1,
            'workflow_id': p['workflow_id'], 'path': p['workflow'],
            'url': API + f"/actions/runs/{p['run_id']}"}, 'execution_run')
        for key in ('repository', 'head_repository'):
            fields(run[key], {'id': SOURCE_ID, 'full_name': SOURCE, 'private': False}, 'execution_repo')
        fields(run['head_commit'], {'id': p['commit'], 'tree_id': p['tree']}, 'execution_head')
        fields(commit, {'sha': p['commit'], 'url': API + '/git/commits/' + p['commit']}, 'execution_commit')
        fields(commit['tree'], {'sha': p['tree']}, 'execution_tree')
        fields(art, {'id': p['artifact_id'], 'name': p['artifact_name'], 'expired': False,
            'size_in_bytes': p['archive_bytes'], 'digest': 'sha256:' + p['archive_sha256'],
            'url': API + f"/actions/artifacts/{p['artifact_id']}"}, 'execution_artifact')
        fields(art['workflow_run'], {'id': p['run_id'], 'head_sha': p['commit'],
            'head_branch': p['branch'], 'repository_id': SOURCE_ID,
            'head_repository_id': SOURCE_ID}, 'execution_artifact_run')
        need(utc(run['created_at']) <= utc(run['run_started_at']) <= utc(art['created_at'])
             <= utc(run['updated_at']) <= utc(meta['retrieved_at']) < utc(art['expires_at']),
             'execution_capture_time')
        raw_zip = read_regular(directory / f'execution-{kind}-original.zip', 128*1024)
        need(len(raw_zip) == p['archive_bytes'] and digest(raw_zip) == p['archive_sha256'],
             'execution_archive_changed')
        m = unpack(raw_zip, p['members']); members[kind] = m
        same(manifest(m['archive.sha256']), {n: digest(b) for n, b in m.items()
             if n != 'archive.sha256'}, 'execution_inner_manifest')
        name = 'fork-gas-break-even.json' if kind == 'gas' else 'physical-liquidation-report.json'
        report = strict_json(m[name]); reports[kind] = report
        need(report['report_sha256'] == digest(canonical({k: v for k, v in report.items()
             if k != 'report_sha256'})), 'execution_original_report_commitment')
        provenance[kind] = {k: p[k] for k in ('run_id', 'commit', 'tree', 'artifact_id',
                            'archive_sha256', 'metadata_sha256', 'workflow')}
        provenance[kind].update(repository=SOURCE, repository_id=SOURCE_ID,
            retrieved_at=meta['retrieved_at'], report_sha256=report['report_sha256'],
            trust_basis='REVIEWED_RETAINED_API_CAPTURE_NOT_FRESH_EVM_EXECUTION')
    raw_sources = {}
    for path, sha in pin['source_files'].items():
        data = read_regular(root / path)
        need(digest(data) == sha, 'execution_original_source_changed:' + path)
        if path.endswith('.py'): raw_sources[Path(path).stem] = data
    same(manifest(members['gas']['source-files.sha256']), {
        p: pin['source_files'][p] for p in (
            'ci/nqc-census/rmc016_rank1_fork_gas_budget.py',
            'ci/nqc-census/test_rmc016_rank1_fork_gas_budget.py',
            'ci/nqc-census/weth-physical/test/NqcRmc016RankOneSelfFinancingFork.t.sol')},
        'execution_source_manifest')
    modules = {}
    def pinned_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in raw_sources:
            need(level == 0, 'execution_relative_import'); return load(name)
        return builtins.__import__(name, globals, locals, fromlist, level)
    def load(name):
        if name not in modules:
            m = ModuleType(name); modules[name] = m
            m.__file__ = str(root / 'ci/nqc-census' / (name + '.py'))
            m.__dict__['__builtins__'] = {**vars(builtins), '__import__': pinned_import}
            exec(compile(raw_sources[name], m.__file__, 'exec'), m.__dict__)
        return modules[name]
    original = load('rmc016_rank1_fork_gas_budget')
    return reports, members, provenance, original


def reconstruct_gas(gas, members, directory, original):
    """Replay the original auditor from retained operator observations, offline."""
    observations = gas['historical_source_operator_observations']
    providers = [p for p in original.PROVIDERS if p[0] in ('drpc', 'blast')]
    need(len(observations) == len(providers) == 2, 'execution_provider_count')
    replies = {}
    for row, (pid, operator, url) in zip(observations, providers):
        fields(row, {'provider_id': pid, 'operator': operator}, 'execution_operator')
        replies[url] = {'number': hex(row['winner_block']), 'hash': row['winner_block_hash'],
            'parentHash': row['previous_block_hash'], 'stateRoot': row['winner_state_root'],
            'baseFeePerGas': hex(int(row['winner_base_fee_per_gas_wei'])),
            'gasUsed': hex(int(row['winner_block_gas_used'])),
            'gasLimit': hex(int(row['winner_block_gas_limit']))}
    def retained_rpc(url, method, params):
        need(url in replies, 'execution_unretained_provider')
        if method == 'eth_chainId' and params == []: return '0x1'
        need(method == 'eth_getBlockByNumber' and params == [hex(original.BLOCK), False],
             'execution_unretained_rpc')
        return replies[url]
    with tempfile.TemporaryDirectory(prefix='omega-execution-source-') as tmp:
        fork, price = Path(tmp)/'fork.zip', Path(tmp)/'price.zip'
        fork.write_bytes(read_regular(Path(directory)/'execution-fork-original.zip'))
        price.write_bytes(read_regular(Path(directory)/'weth-price-original.zip'))
        reproduced = original.audit(fork, price, members['gas']['physical-fork-gas-test.txt'].decode(),
                                    call=retained_rpc, providers=providers)
    same(reproduced, gas, 'execution_gas_differs_from_original_replay')
    return reproduced


def build_execution_report(directory=EVIDENCE, root=ROOT):
    base = build_temporal_report(directory, root)
    load_price(directory, root)
    reports, members, provenance, original = load_execution_sources(directory, root)
    gas = reconstruct_gas(reports['gas'], members, directory, original)
    plan = strict_json(read_regular(Path(root)/'omega/architecture_v3.json'))
    need(not verify_plan(plan), 'execution_current_policy_invalid')
    policy = plan['gas_funding_policy']
    matches = [r for r in base['records'] if r['transaction_hash'] == original.WINNER_TX]
    need(len(matches) == 1, 'execution_winner_join')
    row = matches[0]; pre = row['predecessor_state']; time = row['temporal_witness']
    fields(row, {'block_number': original.BLOCK, 'block_hash': original.BLOCK_HASH,
                 'weth_debt_wei': str(original.PRINCIPAL_WEI)}, 'execution_join')
    fields(pre['predecessor_block'], {'number': original.BLOCK-1,
                                     'hash': original.PREVIOUS_BLOCK_HASH}, 'execution_predecessor')
    need(time is not None and time['time_only_below_one'] is True, 'execution_time_only_join')
    # This old fork report points to the original single-case clock artifact,
    # not the later three-case temporal archive. Preserve that exact identity.
    need(reports['fork']['source_sha256'] == original.SOURCE_TIME_ZIP_SHA,
         'execution_original_time_source')
    costs = {k: {'status': 'UNKNOWN', 'paid_amount_wei': None, 'asset': None,
                 'incidence': 'UNKNOWN', 'evidence_sha256': None} for k in CATEGORIES}
    costs['CAPITAL_FEE'].update(status='SIMULATED_FORK_ONLY', asset='WETH',
        simulated_amount_wei=str(original.FLASH_FEE_WEI),
        evidence_sha256=reports['fork']['report_sha256'])
    costs['GAS'].update(status='MEASURED_EVM_CALL_ONLY', asset='ETH',
        measured_call_gas_units=gas['physical_flash_liquidation_call_gas_units'],
        measured_transaction_gas_units=None, evidence_sha256=gas['report_sha256'])
    rows = []
    for upstream in base['records']:
        witness = None
        if upstream['transaction_hash'] == original.WINNER_TX:
            witness = {'scope': 'RETAINED_PREDECESSOR_FORK_WITH_WINNER_CLOCK_ONLY',
                'predecessor_block': copy.deepcopy(pre['predecessor_block']),
                'winner_block': original.BLOCK, 'winner_block_hash': original.BLOCK_HASH,
                'flash_principal_weth_wei': str(original.PRINCIPAL_WEI),
                'surplus_after_fork_flash_fee_weth_wei': str(original.SURPLUS_WEI),
                'costs': costs, 'modeled_gas_sensitivities': gas['sensitivity_cases'],
                'original_gas_log_sha256': digest(members['gas']['physical-fork-gas-test.txt']),
                'original_fork_log_sha256': digest(members['fork']['fork-liquidation.txt']),
                'actual_transaction_prestate_proven': False, 'native_gas_paid_wei': None,
                'titan_execution_coverage_evidence': None, 'titan_repayment_wei': None,
                'titan_net_balance_increase_wei': None, 'complete_net_profit_wei': None,
                'nqc_realized_profit_wei': None, 'capture_probability': None}
        rows.append({'transaction_hash': upstream['transaction_hash'],
            'upstream_record_commitment': upstream['record_commitment_sha256'],
            'execution_status': 'RETAINED_FORK_DIAGNOSTIC' if witness else 'UNOBSERVED',
            'execution_witness': witness, 'executable_candidate': False, 'complete_costs': False})
    return seal({'schema': SCHEMA, 'status': 'RETAINED_EXECUTION_ECONOMICS_PARTIAL',
        'temporal_report_commitment': base['report_commitment_sha256'],
        'source_provenance': provenance, 'records': rows,
        'gas_funding_policy': copy.deepcopy(policy), 'gas_policy_sha256': digest(canonical(policy)),
        'summary': {'historical_corpus_transactions': 127, 'weth_transactions': 9,
            'retained_execution_diagnostics': 1, 'unobserved_execution_count': 8,
            'modeled_gas_cases': 5, 'complete_paid_cost_rows': 0,
            'titan_covered_executions': 0, 'executable_candidates': 0},
        'new_evm_execution_performed': False, 'new_chain_acquisition_performed': False,
        'titan_request_performed': False, 'source_legacy_policy_rewritten': False,
        'authorities': dict(AUTHORITIES)})


def verify_execution_report(report, directory=EVIDENCE, root=ROOT):
    expected = build_execution_report(directory, root)
    same(report, expected, 'execution_report_differs_from_sources'); return expected


def store_execution_report(path, root=ROOT):
    chain = store_chain(path, root)
    parent = chain['batches']['temporal']; objects = read_batch(path, parent)
    objects.update({n: read_regular(Path(root)/'omega/evidence'/n) for n in SOURCE_NAMES})
    with tempfile.TemporaryDirectory(prefix='omega-execution-admit-') as tmp:
        for n, b in objects.items(): (Path(tmp)/n).write_bytes(b)
        report = build_execution_report(Path(tmp), root)
    objects[REPORT_NAME] = canonical(report)
    objects[BINDING_NAME] = canonical(chain['batches'])
    batch = admit(path, objects, parents=[parent])
    return {'batch': batch, 'parents': chain['batches'], 'report': report}


def query_execution_report(path, batch, root=ROOT):
    objects = read_batch(path, batch); parents = strict_json(objects[BINDING_NAME])
    need(set(parents) == set(STAGES), 'execution_parent_inventory')
    graph = audit_store(path)['dependencies']
    for index, stage in enumerate(STAGES):
        same(graph.get(parents[stage]), [] if index == 0 else [parents[STAGES[index-1]]],
             'execution_parent_edges')
    same(graph.get(batch), [parents['temporal']], 'execution_missing_declared_parent')
    temporal = query_temporal_report(path, parents['temporal'], root)
    inherited = read_batch(path, parents['temporal'])
    need(set(objects) == set(inherited) | SOURCE_NAMES | {REPORT_NAME, BINDING_NAME},
         'execution_batch_inventory')
    need(all(objects[n] == b for n, b in inherited.items()), 'execution_inherited_bytes_changed')
    with tempfile.TemporaryDirectory(prefix='omega-execution-query-') as tmp:
        for n, b in objects.items(): (Path(tmp)/n).write_bytes(b)
        result = verify_execution_report(strict_json(objects[REPORT_NAME]), Path(tmp), root)
    need(result['temporal_report_commitment'] == temporal['report_commitment_sha256'],
         'execution_parent_report_mismatch')
    return result


def exercise_fields(directory, root=ROOT):
    directory = Path(directory); path = create(directory/'source.sqlite')
    result = store_execution_report(path, root); batch = result['batch']
    same(query_execution_report(path, batch, root), result['report'], 'execution_query_mismatch')
    before = read_batch(path, batch)
    revoke(path, result['parents']['ledger'], 'CONTROLLED_EXECUTION_DEPENDENCY_TEST',
           b'TEST_ONLY_NOT_A_REAL_CANONICAL_REORG')
    status = audit_store(path); snapshot = export_store(path)
    restored = directory/'restored.sqlite'
    restore_store(restored, snapshot)
    same(audit_store(restored)['journal_head'], status['journal_head'], 'execution_restore_head')
    same(export_store(restored), snapshot, 'execution_restore_changed')
    for database in (path, restored):
        try: query_execution_report(database, batch, root)
        except ValueError as e: need(str(e) == 'batch_inactive_or_missing', 'execution_block_reason')
        else: raise ValueError('revoked_execution_query_accepted')
        need(read_batch(database, batch, include_revoked=True) == before, 'execution_forensic_bytes_changed')
    need(len(status['revoked_batches']) == 1 and len(status['invalidated_batches']) == 5
         and status['active_batches'] == [], 'execution_invalidation_partition')
    return {'schema': 'nqc.omega.execution-local-replay.v1',
        'status': 'EXECUTION_LOCAL_REPLAY_PASS', 'economic_report': result['report'],
        'execution_batch': batch, 'parent_batches': result['parents'],
        'snapshot_sha256': digest(canonical(snapshot)), 'journal_head': status['journal_head'],
        'blocked_batches': 6, 'forensic_bytes_preserved': True, 'restore_byte_identical': True,
        'revoked_query_rejected': True, 'rust_transport_performed': False,
        'certified_components': 0, 'census_closed': False}


def verify_replay(report, root=ROOT):
    network = report.get('network', {})
    need(network.get('interfaces') == ['lo'] and network.get('routable_network') is False
         and all(type(network.get(k)) is str and re.fullmatch(r'net:\[[0-9]+\]', network[k])
                 for k in ('network_namespace', 'parent_network_namespace'))
         and network['network_namespace'] != network['parent_network_namespace'], 'execution_network')
    with tempfile.TemporaryDirectory(prefix='omega-execution-verify-') as tmp:
        expected = exercise_fields(tmp, root)
    expected['network'] = network
    same(report, seal(expected), 'execution_replay_differs_from_sources'); return report


def exercise(directory, network, root=ROOT):
    from rust_store_intake import new_directory
    directory = new_directory(directory, root)
    print('OMEGA_EXECUTION_BEGIN', flush=True)
    report = exercise_fields(directory, root); report['network'] = network; seal(report)
    verify_replay(report, root)
    (directory/'report.json').write_bytes(canonical(report))
    print('OMEGA_EXECUTION_REPORT ' + canonical(report).decode().strip(), flush=True)
    return report
