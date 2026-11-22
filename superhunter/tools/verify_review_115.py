"""Verify catalog, source and live operations from a bounded transcript without executing producers."""
import argparse
import re
import base64
from collections import Counter
from functools import cache
from pathlib import Path
import sys
import zlib

from superhunter.product_batches import FIXED_SOURCE_RECEIPTS, RECEIPTS, check_native, check_reference
from superhunter.product_matrix import published_excerpts
from superhunter.product_reasoning import EvidenceError
from superhunter.product_source_audit import SNAPSHOT, SNAPSHOT_SHA
from superhunter.product_review import ROOT, sha
from superhunter.product_upstream_notices import sources
from superhunter.safe_io import MAX_BYTES, canonical, read_artifact, strict_json
from superhunter.tools.catalog_session import review_queries


def observed(row):
    name = row['repository'].casefold()
    if name in FIXED_SOURCE_RECEIPTS:
        role, key, expected = FIXED_SOURCE_RECEIPTS[name]
        if key in row and row[key] != expected:
            raise EvidenceError('fixed product result changed')
    elif name in RECEIPTS:
        role, key = 'executable', RECEIPTS[name]
        if row.get(key):
            check_native(name, row[key])
    elif name in ('ethereum/eips', 'ethereum/execution-specs'):
        role, key = 'reference_data', 'census_header_reference'
        if row.get(key):
            check_reference(name, row[key])
    elif name in ('owasp/asvs', 'owasp/cheatsheetseries', 'in-toto/in-toto'):
        supply = row.get('supply_role') or {}
        if supply and (supply.get('role') == 'executable' or row.get('controls')):
            check_reference(name, {k: row[k] for k in ('supply_role', 'controls') if k in row})
            return supply['role'], supply['artifact']
        return 'pending', None
    else:
        return 'pending', None
    return (role, key) if row.get(key) else ('pending', None)


def response_keys(raw):
    keys = review_queries()
    tail = raw.splitlines()[len(keys):]
    if len(tail) > 4:
        raise EvidenceError('acceptance transcript has missing or extra responses')
    markers = {'archive_sha256': 'portable-source-proof', 'go_archive_sha256': 'go-header-digest',
               'observations': 'component-controls', 'groups': 'native-capabilities'}
    extras = []
    for line in tail:
        groups = [name for field, name in markers.items() if field in strict_json(line)]
        if len(groups) != 1 or groups[0] in extras:
            raise EvidenceError('acceptance transcript has missing or extra responses')
        extras.append(groups[0])
    optional = [name for name in extras if name in ('component-controls', 'native-capabilities')]
    if extras != optional and extras != ['portable-source-proof', 'go-header-digest', *optional]:
        raise EvidenceError('acceptance transcript has missing or extra responses')
    return keys + extras


@cache
def source_snapshot(digest):
    if digest == SNAPSHOT_SHA:
        path = SNAPSHOT
    elif digest == SNAPSHOT_153:
        path = 'superhunter/product_supply/source-inventory-153.json'
    else:
        raise EvidenceError('unknown source inventory snapshot')
    raw = read_artifact(ROOT, path)
    if sha(raw) != digest:
        raise EvidenceError('source audit differs from the reviewed snapshot')
    return strict_json(raw)


def native_bindings(report, *, version=None):
    """Compare each selected native group with its pinned, independently reviewed output."""
    native = report.get('native-capabilities')
    if native is None:
        return {}
    from superhunter.product_native_capabilities import contracts
    registry = contracts(version=version)
    groups = native.get('groups')
    failed = native.get('blocked_groups', {})
    if (not isinstance(groups, dict) or not isinstance(failed, dict) or not (groups or failed)
            or set(groups) & set(failed) or (set(groups) | set(failed)) - registry.keys()
            or ('blocked_groups' in native and not failed)
            or any(not isinstance(error, dict) or set(error) != {'error_type', 'message'}
                   or not all(isinstance(value, str) for value in error.values()) or not error['error_type']
                   for error in failed.values())
            or type(native.get('original_vulnerabilities_confirmed')) is not int
            or native['original_vulnerabilities_confirmed'] != 0
            or native.get('scope') != 'fixed_owned_controls_and_pinned_local_inputs'):
        raise EvidenceError('native group membership or scope differs')
    bindings = {}
    for group, result in groups.items():
        contract = registry[group]
        if sha(canonical(result)) != contract['report_sha256']:
            raise EvidenceError('native producer bytes differ from reviewed controls')
        for name, role in contract['repositories'].items():
            bindings[name] = {'query': 'native-capabilities', 'group': group, 'repository': name,
                              'role': role, 'report_sha256': contract['report_sha256']}
    if (native.get('repositories') != sorted(k.casefold() for k in bindings)
            or type(native.get('functional_participations')) is not int
            or native['functional_participations'] != len(bindings)):
        raise EvidenceError('native totals differ from producer identities')
    return bindings


INTERIM_99 = '81ab0b56f1970caeecc58ffc2fbf09197f340ede1b193b5d984c3db00593c9f5'
NATIVE_SESSION_70 = '2a6fd0bb2ceddb08d0a1f461e71da538fcd7bb7ccb486d537e6a244b403e973e'
SUPPLY = ROOT / 'superhunter/product_supply'
ARCHIVE_99_SHA = 'c4d9f671093a88aa25be658c583361da7c7abadee5ac582de4e5f723a8375c1b'
ACCEPTANCE_70_SHA = 'd826d1ead698a870ac978d732b943d7aed1d49a14adffaad30295867356ee6ae'
SNAPSHOT_153 = '9fe08694ea198e7872cc954a122fc4bdc4675996a5403cb7344822a89a3bfe3f'
COMPONENTS_THROUGH_HTML = '7ad5ed1a7c4a344bb1b8d1467a3ad109b618fa1a82f67c6486cbcafa2b39105a'
REPORT_INTEROP_TRANSCRIPT_SHA = 'd0cea728fa6a8d58120227a2e803da1afb93313913c7b2268454fc7299cb1b78'
REPORT_INTEROP_EVIDENCE = '4dabd753f601a6f2938b425ba9bf7ed8ddfa245e'
REPORT_INTEROP_PRODUCER = 'f1eea76f24ff0cf0b5af4a870b5d6e117c46d248'
HTML_PRODUCER = '604bd28d528ee809c8e6d38adab86ec6f67b652c'
HTML_TRANSCRIPT_SHA = 'd07aafc5d1c5ba5dfbe5bdcb59d8fe292ddfb7b8a2fe97e5b944ab27fd5b72ff'
COMPONENTS_REPORT_INTEROP = 'f05874680d267a179c47e04b0fd032bbf1695896225293189cec93856b4e4b82'
COMPONENTS_EVIDENCE_CONTRACTS = 'e817543c5ca4887cf618806e3dc6b1981e72239aa679dd78afab68c217d70b6a'
COMPONENTS_SUPPLY_AND_REPORTING = '7442de259902d227b3ba6c05f56597f814abaeca8cc531d0b3a2c6fe28f1ad0e'
COMPONENTS_VENDORED_ATTRIBUTIONS = 'e12a865b8cf73bf405dd3b8b10a388e21b8326e8e6d782cc5b1f1833cf376b6f'
SUPPLY_AND_REPORTING_PRODUCER = 'a05693a9f2562ac147e4c5ec6c7646e8857dcf64'
SUPPLY_AND_REPORTING_ACT = '10919f0cf387809cc529ea15ebe08acafc0bf665'
SUPPLY_AND_REPORTING_TRANSCRIPT_SHA = '972f08f6a715542046ce174863dc385dbfec6851a40d738afec8f22d767782ab'
EVIDENCE_CONTRACTS_PRODUCER = '2ddbe098cc98a667211494a9ff9f21ce014d8c3f'
EVIDENCE_CONTRACTS_ACT = '582cc5c48ee0f92a01d638a55c5d4a2b602d903a'
EVIDENCE_CONTRACTS_TRANSCRIPT_SHA = 'bdb0e859c9a3affd0f0ca198ed1cdeae75571889f9cab67d28d372058c29722e'
SUCCESSOR_BASELINES = {
    'evidence-contracts': 'report-interop',
    'supply-and-reporting': 'evidence-contracts',
    'vendored-attributions': 'supply-and-reporting',
}
HISTORICAL_COMPONENTS = {
    'supply-and-reporting': COMPONENTS_SUPPLY_AND_REPORTING,
    'evidence-contracts': COMPONENTS_EVIDENCE_CONTRACTS,
    'report-interop': COMPONENTS_REPORT_INTEROP,
    'through-html': COMPONENTS_THROUGH_HTML,
    '99': 'adbd7b433b1d3cad6ee0a64fa71e5187f422dafc9050353c07c66d20187abfea',
    '118': '06a61867ec8d0612d7e4a934f723a8c4a8ab42dbb9a1ab3e3a2321c5521d2bf2',
}


@cache
def component_rules(profile):
    if profile == 'vendored-attributions':
        raw = read_artifact(ROOT, 'superhunter/product_supply/component-control-contracts.json')
        if sha(raw) != COMPONENTS_VENDORED_ATTRIBUTIONS:
            raise EvidenceError('vendored attribution contracts differ from the reviewed registry')
        return strict_json(raw)
    if profile == 'current':
        from superhunter.product_component_controls import contracts
        return contracts()
    raw = read_artifact(ROOT, f'superhunter/product_supply/component-control-contracts-{profile}.json')
    if sha(raw) != HISTORICAL_COMPONENTS[profile]:
        raise EvidenceError('historical component contracts differ')
    return strict_json(raw)


def row_operations(row, native, *, profile='current'):
    """Read every independent producer, including an overlapping second operation."""
    role, key = observed(row)
    receipts = [(role, key)] if key else []
    if 'component_control_receipt' in row:
        rule = component_rules(profile).get(row['repository'])
        if (not rule or row['component_control_receipt'] != {k: rule[k] for k in ('domain', 'revision', 'result_sha256')}
                or rule['revision'] != row['source_inventory']['revision']):
            raise EvidenceError('component control row differs from the accepted result')
        receipts.append((rule['role'], 'component_control_receipt'))
    binding = native.get(row['repository'])
    if 'native_capability_receipt' in row or binding:
        if not binding or row.get('native_capability_receipt') != binding:
            raise EvidenceError('native repository has no matching producer receipt')
        receipts.append((binding['role'], 'native_capability_receipt'))
    operations = []
    for role, field in receipts:
        if field in ('supply.link', 'asvs.csv', 'asvs-guides.md'):
            value = {k: row[k] for k in ('supply_role', 'controls') if k in row}
        else:
            value = row[field]
        operations.append({'role': role, 'receipt': field, 'evidence_sha256': sha(canonical(value))})
    return sorted(operations, key=lambda op: (op['role'] != 'executable', op['receipt']))


def verify_policy_corroboration(controls):
    observations = controls['observations']
    if {'iann0036/iamlive', 'BishopFox/cloudfox'} <= observations.keys():
        from superhunter.product_policy_catalog import corroborate
        expected = corroborate(observations['iann0036/iamlive'], observations['BishopFox/cloudfox'])
        if canonical(controls.get('policy_catalog_corroboration')) != canonical(expected):
            raise EvidenceError('policy catalog corroboration differs from the two producer observations')
    elif 'policy_catalog_corroboration' in controls:
        raise EvidenceError('policy catalog corroboration has no joint producer observations')


def verify(raw, expected_hash=None, *, require_consolidated=False, require_accounting=False,
           require_canonical_header=False, require_grpc_schema=False, require_html_review=False,
           require_report_interop=False, require_evidence_contracts=False, require_supply_and_reporting=False,
           require_vendored_attributions=False, producer_commit=None):
    profiles = [name for selected, name in (
        (require_consolidated, 'core-eight'), (require_accounting, 'accounting-nine'),
        (require_canonical_header, 'canonical-ten'), (require_grpc_schema, 'grpc-eleven'),
        (require_html_review, None), (require_report_interop, None), (require_evidence_contracts, None),
        (require_supply_and_reporting, None), (require_vendored_attributions, None)) if selected]
    if len(profiles) > 1:
        raise EvidenceError('select one exact consolidated acceptance profile')
    full_profile = bool(profiles)
    native_version = profiles[0] if full_profile else None
    digest = sha(raw)
    if expected_hash is not None and digest != expected_hash:
        raise EvidenceError('transcript digest differs from the acceptance record')
    keys = response_keys(raw)
    lines = raw.splitlines()
    if len(lines) != len(keys):
        raise EvidenceError('acceptance transcript has missing or extra responses')
    report = {}
    for key, line in zip(keys, lines, strict=True):
        value = strict_json(b'{"response":' + line + b'}')['response']
        expected = list if key == 'notice-overlaps:upstream-002-license.txt' else dict
        if not isinstance(value, expected):
            raise EvidenceError('unexpected response type at ' + key)
        report[key] = value
    archive = read_artifact(ROOT, 'superhunter/product_supply/coverage-d94b58f.json')
    if sha(archive) != 'b47f69c24ee583c5e8ef61954439b56818bccf6e3fa35a60bf099381d10bc1bd':
        raise EvidenceError('historical index changed')
    history = {doc['catalog_id']: doc for doc in strict_json(archive)['receipts']}
    matrix = report['integration-matrix']
    rows = matrix['rows']
    combined = 'component-controls' in report and 'native-capabilities' in report
    coverage = report['integration-coverage']
    operations_format = 'session_operation_count' in matrix
    if combined and not operations_format:
        raise EvidenceError('combined session lacks its per-operation matrix')
    # The first native session predates the operation ledger. Check its historical
    # producers independently, then require the exact published bytes before acceptance.
    historical_native = 'native-capabilities' in report and not operations_format
    native = native_bindings(report, version=70 if historical_native else native_version)
    interim_118 = ('component-controls' in report and not operations_format and
                   'published_excerpts' not in matrix and
                   report['source-inventory'].get('snapshot_sha256') == SNAPSHOT_153)
    component_profile = 'through-html' if full_profile else 'current'
    if require_vendored_attributions:
        component_profile = 'vendored-attributions'
    elif require_supply_and_reporting:
        component_profile = 'supply-and-reporting'
    elif require_evidence_contracts:
        component_profile = 'evidence-contracts'
    elif require_report_interop:
        component_profile = 'report-interop'
    elif interim_118:
        component_profile = '99'
    elif not operations_format and report['source-inventory'].get('snapshot_sha256') == SNAPSHOT_153:
        component_profile = '118'
    if 'component-controls' in report and 'published_excerpts' not in matrix and not interim_118:
        raise EvidenceError('component profile is missing its published excerpt inventory')
    excerpts = {}
    if 'published_excerpts' in matrix or interim_118:
        actual = published_excerpts()
        if not interim_118 and matrix['published_excerpts'] != actual:
            raise EvidenceError('published excerpt inventory differs from its source bytes')
        excerpts = {r['id']: r for r in actual}
    audit = report['source-inventory']
    snapshot = source_snapshot(audit.get('snapshot_sha256'))
    acquired = {r['id']: r for r in snapshot['entries']}
    if (audit.get('entries_sha256') != snapshot['entries_sha256']
            or audit.get('checkouts') != snapshot['checkouts']
            or audit.get('metadata_only') != snapshot['remote_commit_records']):
        raise EvidenceError('source audit differs from the reviewed snapshot')
    if len(rows) != 200 or any(row['id'] != n for n, row in enumerate(rows, 1)):
        raise EvidenceError('incomplete or disordered acceptance matrix')
    coverage_rows = coverage['identities']
    if len(coverage_rows) != len(rows):
        raise EvidenceError('incomplete catalog coverage')
    from superhunter.product_remote_roots import roots
    remote_names = {identity['repository'] for identity, _ in roots()}
    seen_roots = {r['repository'] for r in rows if 'root_declarations' in report[r['repository']]}
    if remote_names != seen_roots:
        raise EvidenceError('portable root declaration scope differs')
    operation_count = multi_operation = 0
    actual_roles, actual_sources, cumulative_roles, pending_sources = Counter(), Counter(), Counter(), Counter()
    credits = []
    for official, summary in zip(sources(), rows, strict=True):
        name, number = official['repository'], official['id']
        row = report[name]
        audited = row['source_inventory']
        if ((row['repository'], row['catalog_id'], audited['revision'], audited['tree']) !=
                (name, number, official['revision'], summary['tree']) or
                (summary['repository'], summary['id'], summary['commit']) != (name, number, official['revision'])):
            raise EvidenceError('matrix and source revisions disagree')
        fixed = acquired[number]
        if any(audited.get(k) != value for k, value in fixed.items()):
            raise EvidenceError('source revisions or checkout inventory differ from the pinned audit')
        operations = row_operations(row, native, profile=component_profile)
        primary = operations[0] if operations else None
        role, receipt = (primary['role'], primary['receipt']) if primary else ('pending', None)
        previous = history.get(number)
        all_roles = {role, previous['role'] if previous else 'pending'}
        cumulative = next(kind for kind in ('executable', 'reference_data', 'pending') if kind in all_roles)
        if audited['contents'] is not None:
            source = 'complete'
        elif excerpts:
            excerpt = excerpts.get(number)
            if excerpt and (name, audited['revision'], audited['tree']) != (
                    excerpt['repository'], excerpt['revision'], excerpt['tree']):
                raise EvidenceError('published excerpt belongs to a different Git source')
            source = 'excerpt' if excerpt else 'metadata'
        else:
            # The archived PR 115/117 format linked its two extract proofs to the owned review.
            source = 'excerpt' if number in (179, 191) and row.get('owned_source_receipt') else 'metadata'
        if ((source, role, cumulative) != (summary['source'], summary['session'], summary['role']) or
                summary['historical_line_sha256'] != (previous['line_sha256'] if previous else None)):
            raise EvidenceError('matrix status differs from the original evidence')
        actual_sources[source] += 1
        actual_roles[role] += 1
        cumulative_roles[cumulative] += 1
        if cumulative == 'pending':
            pending_sources[source] += 1
        if summary['commercial_review'] != 'pending':
            raise EvidenceError('unsupported commercial license decision')
        if source == 'complete':
            content = fixed['contents']
            scope = 'checked_out_contents'
            nested = len(content['nested_gitlinks'])
            manifests = sum(content['manifest_counts_by_filename'].values())
        else:
            remote = row['recursive_tree_inventory']
            if (remote['root'], remote['commit'], remote['repository']) != (fixed['tree'], fixed['revision'], name):
                raise EvidenceError('missing or inconsistent remote tree evidence')
            scope = 'recursive_tree_objects'
            nested = remote['nested_gitlinks']
            manifests = sum(remote['manifest_counts'].values())
        if (summary['verification_scope'], summary['nested_gitlinks'], summary['recognized_manifest_paths'],
                summary['nature']) != (scope, nested, manifests, audited['nature']):
            raise EvidenceError('source scope or inventory summary differs from inspected evidence')
        notice = audited.get('resolved_notice_scan') or audited['notice_scan']
        if (summary['license'] != {'document': audited['notice_path'],
                'detected_expression': notice['detected_expression'], 'effective_text_sha256': notice['sha256']} or
                notice != (fixed.get('resolved_notice_scan') or fixed['notice_scan'])):
            raise EvidenceError('license evidence digest or description differs')
        coverage_row = coverage_rows[number-1]
        if operations_format and (coverage_row['catalog_id'], coverage_row['repository'], coverage_row['observed_role'],
                coverage_row['session_role'], coverage_row['session_receipt']) != (
                number, name, cumulative, role, receipt):
            raise EvidenceError('coverage disagrees with the independently observed role or producer')
        if operations_format or 'session_operations' in summary or 'session_operations' in coverage_row:
            if (not operations_format or summary.get('session_operations') != operations
                    or coverage_row.get('session_operations') != operations):
                raise EvidenceError('operation ledger differs from the producer bytes')
        operation_count += len(operations)
        multi_operation += len(operations) > 1
        if summary['session'] == 'pending':
            if summary['session_evidence_sha256'] is not None:
                raise EvidenceError('pending identity attributed a session result')
            continue
        if receipt != summary['receipt']:
            raise EvidenceError('live receipt points to the wrong producer field')
        if primary['evidence_sha256'] != summary['session_evidence_sha256']:
            raise EvidenceError('session credit differs from its producer bytes')
        credits.append([number, name, summary['session'], receipt])
    live = {name for name in (r['repository'] for r in rows) if 'component_control_receipt' in report[name]}
    if 'component-controls' in report:
        from superhunter.product_component_controls import reconcile_digest
        controls = report['component-controls']
        names = controls['requested']
        rules = component_rules(component_profile)
        allowed_domains = {rule['domain'] for rule in rules.values()}
        failures = controls['blocked']
        if (not isinstance(names, list) or not names or not all(isinstance(n, str) for n in names)
                or len(names) != len(set(names)) or set(names) - allowed_domains or not isinstance(failures, dict)
                or not all(isinstance(cause, str) and cause.strip() for cause in failures.values())
                or set(failures) - set(names)):
            raise EvidenceError('component selection or blocked domains differ')
        blocked = set(failures)
        expected = {name for name, rule in rules.items() if rule['domain'] in set(names) - blocked}
        if set(controls['observations']) != expected or live != expected:
            raise EvidenceError('component evidence does not cover the selected producers')
        if controls['digest_corroboration'] != reconcile_digest(controls['observations'], report.get('go-header-digest')):
            raise EvidenceError('cross-domain source corroboration differs from original observations')
        for name, observation in controls['observations'].items():
            claim = report[name]['component_control_receipt']
            if (observation.get('revision') != claim['revision'] or
                    sha(canonical(observation)) != claim['result_sha256']):
                raise EvidenceError('individual component result differs from the shared evidence')
        verify_policy_corroboration(controls)
    elif live:
        raise EvidenceError('component receipts have no shared evidence')
    if 'portable-source-proof' in report:
        source_report = report['portable-source-proof']
        from superhunter.product_portable_roots import ARCHIVE_SHA, inputs
        records = [report[r['repository']]['offline_source_proof'] for r in rows
                   if 'offline_source_proof' in report[r['repository']]]
        originals, files = inputs()
        if (records != originals or source_report != {'commits': len(records), 'receipt_sha256': sha(canonical(records)),
                                                      'root_declarations': len(files), 'archive_sha256': ARCHIVE_SHA}):
            raise EvidenceError('portable Git evidence differs from product rows')
        go = report['securego/gosec']['go_source_receipt']
        if go['report_sha256'] != sha(canonical(report['go-header-digest'])):
            raise EvidenceError('Go source audit report differs from the producer receipt')
    counts = {'catalog': len(rows), 'sources': dict(actual_sources), 'verified_notices': len(rows),
              'session': len(credits), 'functional': 200 - cumulative_roles['pending'],
              'pending': cumulative_roles['pending'], 'executables': actual_roles['executable'],
              'reference_data': actual_roles['reference_data']}
    expected = {'catalog': len(rows), 'sources': dict(actual_sources), 'pending_by_source': dict(pending_sources),
                'functional': counts['functional'], 'end_to_end': counts['session'], 'pending': counts['pending'],
                'executable': cumulative_roles['executable'], 'references': cumulative_roles['reference_data'],
                'notices_reviewed': len(rows), 'verified_trees': len(acquired), 'commercial_reviews_completed': 0,
                'remote_roots': len(remote_names)}
    if operations_format:
        expected_coverage = {'catalog_count': len(rows), 'session_with_receipts': counts['session'],
                             'with_receipts_in_either': counts['functional'], 'pending': counts['pending'],
                             'executable_in_either': cumulative_roles['executable'],
                             'reference_data_in_either': cumulative_roles['reference_data']}
        if any(canonical(coverage.get(k)) != canonical(v) for k, v in expected_coverage.items()):
            raise EvidenceError('coverage totals differ from independently counted rows')
        expected.update(session_operation_count=operation_count, session_multi_operation_repositories=multi_operation)
        counts.update(operations=operation_count, multiple_operations=multi_operation)
    if full_profile:
        from superhunter.product_native_capabilities import contracts as native_contracts
        controls = report.get('component-controls') or {}
        if component_profile in SUCCESSOR_BASELINES:
            archived = component_rules(SUCCESSOR_BASELINES[component_profile])
            current = component_rules(component_profile)
            if not set(archived) < set(current) or any(current[name] != row for name, row in archived.items()):
                raise EvidenceError('successor component contracts lost a previous binding or have no additional identity')
        if (not combined or not operations_format or set(controls.get('requested', [])) != allowed_domains
                or (require_report_interop and 'report-interop' not in allowed_domains)
                or controls.get('blocked') != {} or not controls.get('digest_corroboration')
                or set(report['native-capabilities']['groups']) != native_contracts(native_version).keys()
                or report['native-capabilities'].get('blocked_groups')
                or actual_sources != {'complete': 200}):
            raise EvidenceError('incomplete consolidated session')
    if (any(canonical(matrix.get(k)) != canonical(v) for k, v in expected.items()) or
            report['root-declarations']['remote_roots_verified'] != expected['remote_roots']):
        raise EvidenceError('claimed totals differ from independently counted rows')
    if full_profile:
        counts.update(check_historical_coverage(rows))
    if require_report_interop:
        counts.update(check_previous_acceptance(rows, report['ossf/scorecard']['license_file_evidence']))
    if full_profile and component_profile in SUCCESSOR_BASELINES:
        if not isinstance(producer_commit, str) or not re.fullmatch('[0-9a-f]{40}', producer_commit):
            raise EvidenceError('an independently supplied producer commit is required')
        if require_vendored_attributions:
            prior, previous_commit = supply_and_reporting_operations(), SUPPLY_AND_REPORTING_PRODUCER
        elif require_supply_and_reporting:
            prior, previous_commit = evidence_contracts_operations(), EVIDENCE_CONTRACTS_PRODUCER
        else:
            prior, previous_commit = report_interop_operations(), REPORT_INTEROP_PRODUCER
        check_preserved_operations(prior, operation_keys(rows), report['ossf/scorecard']['license_file_evidence'],
                                   previous_commit, producer_commit)
        counts.update(prior_identities_preserved=len({k[0] for k in prior}), prior_operations_preserved=len(prior))
    if 'native-capabilities' in report:
        if historical_native and digest != NATIVE_SESSION_70:
            raise EvidenceError('historical native transcript differs from the published 70-identity session')
        native_result = report['native-capabilities']
        counts.update(native_groups=sorted(native_result['groups']), native_credits=len(native),
                      blocked_native_groups=sorted(native_result.get('blocked_groups', {})),
                      original_vulnerabilities_confirmed=native_result['original_vulnerabilities_confirmed'])
    if 'component-controls' in report:
        if interim_118 and digest != INTERIM_99:
            raise EvidenceError('historical component transcript differs from the published 99-identity session')
        controls = report['component-controls']
        # Older acts recorded their then-current registry under the literal name 'current'.
        recorded_profile = 'current' if component_profile == 'through-html' else component_profile
        counts.update(component_contract_profile=recorded_profile, component_domains=sorted(set(controls['requested']) - set(controls['blocked'])),
                      blocked_component_domains=sorted(controls['blocked']))
    return {'transcript_sha256': digest, 'credits_sha256': sha(canonical(credits)),
            'responses': len(keys), **counts}


def unpack(raw):
    archive = strict_json(raw)
    if archive.get('format') != 'gzip-base64-jsonl-v1' or type(archive.get('raw_size')) is not int:
        raise EvidenceError('unrecognized acceptance archive')
    size = archive['raw_size']
    if not 0 < size <= MAX_BYTES:
        raise EvidenceError('unbounded acceptance archive')
    inflater = zlib.decompressobj(wbits=31)
    decoded = inflater.decompress(base64.b64decode(archive['gzip_base64'], validate=True), size + 1)
    if (len(decoded) != size or not inflater.eof or inflater.unused_data or inflater.unconsumed_tail or
            sha(decoded) != archive['raw_sha256']):
        raise EvidenceError('acceptance archive content differs')
    return decoded


def pinned_file(name, expected_sha):
    raw = read_artifact(SUPPLY, name)
    if sha(raw) != expected_sha:
        raise EvidenceError('historical file differs from reviewed bytes: ' + name)
    return raw


def historical_archives():
    """Pin the wrappers as well as the separate historical transcript hashes."""
    record = strict_json(pinned_file('native-acceptance-70.json', ACCEPTANCE_70_SHA))
    component = unpack(pinned_file('component-session-99.json', ARCHIVE_99_SHA))
    native = unpack(pinned_file('native-session-70.json', record['archive_sha256']))
    return ((component, INTERIM_99), (native, record['independent_verification']['transcript_sha256']))


@cache
def historical_operations():
    """Recover the minimum operations from the verified, immutable individual sessions."""
    required = set()
    for raw, expected_hash in historical_archives():
        verify(raw, expected_hash)
        keys = response_keys(raw)
        rows = strict_json(raw.splitlines()[keys.index('integration-matrix')])['rows']
        required.update((row['id'], row['repository'], row['session'], row['receipt'])
                        for row in rows if row['session'] != 'pending')
    return frozenset(required)


def check_historical_coverage(rows):
    """Compare validated producer operations. A promotion must preserve the same receipt field."""
    required = historical_operations()
    present = {(row['id'], row['repository'], op['role'], op['receipt'])
               for row in rows for op in row['session_operations']}
    preserved = present | {(number, name, 'reference_data', field)
                           for number, name, role, field in present if role == 'executable'}
    missing = sorted(required - preserved)
    if missing:
        number, name, role, field = missing[0]
        raise EvidenceError(f'historical operations missing ({len(missing)}), first: {number} {name} {role} {field}')
    return {'historical_identities_preserved': len({number for number, _, _, _ in required}),
            'historical_operations_preserved': len(required)}


@cache
def html_operations():
    raw = unpack(read_artifact(ROOT, 'superhunter/product_supply/consolidated-acceptance-html-review/first/session.json'))
    verify(raw, HTML_TRANSCRIPT_SHA, require_html_review=True)
    rows = strict_json(raw.splitlines()[response_keys(raw).index('integration-matrix')])['rows']
    return operation_keys(rows)


def operation_keys(rows):
    return frozenset((row['id'], row['repository'], op['role'], op['receipt'], op['evidence_sha256'])
                     for row in rows for op in row['session_operations'])


def check_preserved_operations(previous, current, scorecard, previous_commit, current_commit):
    # Scorecard records the particular NQC commit it audited. Bind both versions
    # and reconstruct its old digest, retaining every other byte of this receipt.
    if scorecard.get('nqc_commit') != current_commit:
        raise EvidenceError('Scorecard identifies a different audited commit')
    field = (141, 'ossf/scorecard', 'executable', 'license_file_evidence')
    old = (*field, sha(canonical({**scorecard, 'nqc_commit': previous_commit})))
    new = (*field, sha(canonical(scorecard)))
    if old not in previous or new not in current or (previous - {old}) - current:
        raise EvidenceError('previous accepted operations or their evidence changed')


def check_previous_acceptance(rows, scorecard=None):
    previous = html_operations()
    current = operation_keys(rows)
    if scorecard is None:
        if previous - current:
            raise EvidenceError('previous accepted operations or their evidence changed')
    else:
        check_preserved_operations(previous, current, scorecard, HTML_PRODUCER, REPORT_INTEROP_PRODUCER)
    return {'prior_identities_preserved': len({key[0] for key in previous}),
            'prior_operations_preserved': len(previous)}


@cache
def report_interop_operations():
    from superhunter.tools import render_product_matrix as renderer
    verified, rows, _ = renderer.verified_pair('report-interop', evidence_commit=REPORT_INTEROP_EVIDENCE)
    if verified['transcript_sha256'] != REPORT_INTEROP_TRANSCRIPT_SHA:
        raise EvidenceError('previous report interoperability transcript differs from the reviewed evidence')
    return operation_keys(rows)


@cache
def evidence_contracts_operations():
    from superhunter.tools import render_product_matrix as renderer
    verified, rows, producer = renderer.verified_pair('evidence-contracts', evidence_commit=EVIDENCE_CONTRACTS_ACT)
    if (producer['commit'] != EVIDENCE_CONTRACTS_PRODUCER
            or verified['transcript_sha256'] != EVIDENCE_CONTRACTS_TRANSCRIPT_SHA):
        raise EvidenceError('previous dependency-review baseline differs from its published pair')
    return operation_keys(rows)


@cache
def supply_and_reporting_operations():
    from superhunter.tools import render_product_matrix as renderer
    verified, rows, producer = renderer.verified_pair('supply-and-reporting', evidence_commit=SUPPLY_AND_REPORTING_ACT)
    if (producer['commit'] != SUPPLY_AND_REPORTING_PRODUCER
            or verified['transcript_sha256'] != SUPPLY_AND_REPORTING_TRANSCRIPT_SHA):
        raise EvidenceError('previous supply and reporting baseline differs from its published pair')
    return operation_keys(rows)


def negative_controls(raw, **profile_options):
    keys = response_keys(raw)
    lines = raw.splitlines()
    matrix = strict_json(lines[keys.index('integration-matrix')])
    old_role = matrix['rows'][2]['session']
    cases = [
        ('inflated_count', 'integration-matrix', ('end_to_end',), len(matrix['rows'])+1, 'claimed totals'),
        ('unsupported_credit', 'integration-matrix', ('rows', 2, 'session'),
         'executable' if old_role == 'pending' else 'pending', 'matrix status'),
        ('replaced_historical_digest', 'integration-matrix', ('rows', 24, 'historical_line_sha256'), '0'*64,
         'matrix status'),
        ('changed_native_result', 'PyCQA/bandit', ('owned_source_receipt', 'sha256'), '0'*64, 'fixed product result'),
        ('changed_license', 'integration-matrix', ('rows', 0, 'license', 'effective_text_sha256'), '0'*64,
         'license evidence'),
        ('changed_git_tree', 'integration-matrix', ('rows', 3, 'tree'), '0'*40, 'source revisions')]
    if 'component-controls' in keys:
        controls = strict_json(lines[keys.index('component-controls')])
        observed = controls['observations']
        cases.extend([
            ('erased_domain_selection', 'component-controls', ('requested',), [], 'component selection'),
            ('erased_shared_results', 'component-controls', ('observations',), {} if observed else {'unexpected': {}},
             'component evidence'),
            ('erased_corroboration', 'component-controls', ('digest_corroboration',),
             {} if controls['digest_corroboration'] else {'unexpected': True}, 'cross-domain'),
            ('changed_role_totals', 'integration-matrix', ('references',), -1, 'claimed totals'),
            ('changed_source_distribution', 'integration-matrix', ('pending_by_source',), {'metadata': -1}, 'claimed totals'),
            ('changed_commercial_total', 'integration-matrix', ('commercial_reviews_completed',), 1, 'claimed totals'),
            ('erased_excerpt_inventory', 'integration-matrix', ('published_excerpts',), [], 'excerpt inventory')])
        if 'policy_catalog_corroboration' in controls:
            cases.append(('changed_policy_catalog_joint_digest', 'component-controls',
                          ('policy_catalog_corroboration', 'joint_sha256'), '0' * 64, 'policy catalog corroboration'))
        if observed:
            if 'sqlmapproject/sqlmap' in observed:
                cases.append(('changed_vendored_attribution', 'component-controls',
                              ('observations', 'sqlmapproject/sqlmap', 'result', 'package_evidence',
                               'thirdparty/beautifulsoup', 'disposition'),
                              'named_notice_text_consistent_with_group', 'individual component result'))
            if 'DataDog/stratus-red-team' in observed:
                cases.append(('changed_attribution_review', 'component-controls',
                              ('observations', 'DataDog/stratus-red-team', 'operation'),
                              'unverified', 'individual component result'))
            if 'OWASP/Nettacker' in observed:
                cases.append(('changed_localized_report', 'component-controls',
                              ('observations', 'OWASP/Nettacker', 'result', 'index_sha256'),
                              '0' * 64, 'individual component result'))
            name = sorted(observed)[0]
            cases.append(('changed_group_result', 'component-controls', ('observations', name, 'operation'),
                          'unchecked', 'individual component result'))
    if 'session_operation_count' in matrix:
        cases.extend([
            ('changed_operation_total', 'integration-matrix', ('session_operation_count',), -1, 'claimed totals'),
            ('changed_coverage_total', 'integration-coverage', ('session_with_receipts',), -1, 'coverage totals')])
        overlap = next((row for row in matrix['rows'] if len(row['session_operations']) > 1), None)
        if overlap:
            number = overlap['id'] - 1
            cases.extend([
                ('discarded_secondary_operation', 'integration-matrix', ('rows', number, 'session_operations'),
                 overlap['session_operations'][:1], 'operation ledger'),
                ('forged_secondary_digest', 'integration-coverage',
                 ('identities', number, 'session_operations', 1, 'evidence_sha256'), '0'*64, 'operation ledger')])
    if 'native-capabilities' in keys:
        native = strict_json(lines[keys.index('native-capabilities')])
        cases.append(('invented_discovery', 'native-capabilities', ('original_vulnerabilities_confirmed',), 1,
                      'native group membership or scope'))
        if native['groups']:
            group, result = next(iter(native['groups'].items()))
            cases.append(('changed_native_report', 'native-capabilities', ('groups', group),
                          {**result, 'unverified': True}, 'native producer bytes'))
    rejected = {}
    for name, key, path, replacement, reason in cases:
        lines = raw.splitlines()
        position = keys.index(key)
        record = strict_json(lines[position])
        node = record
        for member in path[:-1]:
            node = node[member]
        node[path[-1]] = replacement
        lines[position] = canonical(record).rstrip(b'\n')
        try:
            verify(b'\n'.join(lines) + b'\n', **profile_options)
        except EvidenceError as exc:
            if reason not in str(exc):
                raise
            rejected[name] = str(exc)
        else:
            raise EvidenceError('negative control accepted: ' + name)
    return rejected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('transcript', type=Path)
    parser.add_argument('--check-controls', action='store_true', help='reject deliberately altered copies of the evidence')
    parser.add_argument('--replay', type=Path, help='independently verify and compare the full second transcript in the same format')
    parser.add_argument('--archive', action='store_true', help='read a published gzip/base64 evidence envelope')
    parser.add_argument('--require-complete-controls', action='store_true', help='require all defensive domains and zero blocked producers')
    profiles = parser.add_mutually_exclusive_group()
    profiles.add_argument('--require-consolidated', action='store_true', help='require the complete eight-group consolidated acceptance profile')
    profiles.add_argument('--require-consolidated-accounting', action='store_true', help='require the complete nine-group acceptance profile including the ten fixed accounting checks')
    profiles.add_argument('--require-consolidated-canonical-header', action='store_true',
                          help='require all ten groups including canonical header interoperability')
    profiles.add_argument('--require-consolidated-grpc-schema', action='store_true',
                          help='require all eleven groups including static gRPC schema interoperability')
    profiles.add_argument('--require-consolidated-html-review', action='store_true',
                          help='require all twelve groups including the fixed NQC HTML report')
    profiles.add_argument('--require-consolidated-report-interop', action='store_true',
                          help='require the twelve native groups, the previous ledger and every report control domain')
    profiles.add_argument('--require-consolidated-evidence-contracts', action='store_true',
                          help='require all current domains and every receipt in the accepted report interoperability pair')
    profiles.add_argument('--require-consolidated-supply-and-reporting', action='store_true',
                          help='verify the dependency attribution review and the entire previous evidence-contracts pair')
    profiles.add_argument('--require-consolidated-vendored-attributions', action='store_true',
                          help='verify the vendored notice review and all previous supply and reporting operations')
    parser.add_argument('--producer-commit', help='independently verified Git identity for the selected producer')
    parser.add_argument('--expect-sha256', help='trusted digest for a specific, published run')
    args = parser.parse_args()
    raw = read_artifact(args.transcript.parent, args.transcript.name)
    if args.archive:
        raw = unpack(raw)
    profile_options = {'require_consolidated': args.require_consolidated,
                       'require_accounting': args.require_consolidated_accounting,
                       'require_canonical_header': args.require_consolidated_canonical_header,
                       'require_grpc_schema': args.require_consolidated_grpc_schema,
                       'require_html_review': args.require_consolidated_html_review,
                       'require_report_interop': args.require_consolidated_report_interop,
                       'require_evidence_contracts': args.require_consolidated_evidence_contracts,
                       'require_supply_and_reporting': args.require_consolidated_supply_and_reporting,
                       'require_vendored_attributions': args.require_consolidated_vendored_attributions}
    if (args.require_consolidated_evidence_contracts or args.require_consolidated_supply_and_reporting
            or args.require_consolidated_vendored_attributions):
        profile_options['producer_commit'] = args.producer_commit
    result = verify(raw, args.expect_sha256, **profile_options)
    if args.require_complete_controls:
        profile = result.get('component_contract_profile', 'current')
        if profile == 'current' and any(profile_options.values()):
            profile = 'through-html'
        expected_domains = {rule['domain'] for rule in component_rules(profile).values()}
        keys = response_keys(raw)
        session = strict_json(raw.splitlines()[keys.index('component-controls')]) if 'component-controls' in keys else {}
        if (set(session.get('requested', [])) != expected_domains or session.get('blocked') != {}
                or not session.get('digest_corroboration')):
            raise EvidenceError('incomplete defensive control session')
    if args.replay:
        if args.transcript.samefile(args.replay):
            raise EvidenceError('two distinct transcript files are required')
        other = read_artifact(args.replay.parent, args.replay.name)
        if args.archive:
            other = unpack(other)
        replay = verify(other, **profile_options)
        if other != raw:
            raise EvidenceError('the verified transcript bytes differ between runs')
        result['replay_sha256'] = replay['transcript_sha256']
    if args.check_controls:
        result['rejected_controls'] = negative_controls(raw, **profile_options)
    sys.stdout.buffer.write(canonical(result))


if __name__ == '__main__':
    main()
