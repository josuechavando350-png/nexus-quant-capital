"""Join native, locally reproduced capability controls to the product index."""
from importlib import import_module
from pathlib import Path
from subprocess import SubprocessError
import re

from .product_reasoning import EvidenceError
from .product_review import ROOT, sha
from .safe_io import canonical, read_artifact, strict_json

CONTRACT = 'superhunter/product_supply/native-capability-contracts.json'
CONTRACT_SHA = '7d140e5ca9e303a6c995d1871f5915821864c4763aefc727a3e71ff49a1fcc38'
HISTORICAL_CONTRACTS = {
    'core-eight': ('superhunter/product_supply/native-capability-contracts-core-eight.json',
          '51e2d24afa9f7bc98152c4dd8337560e41efe9b50657c4a222ceedfc28b1355a'),
    'accounting-nine': ('superhunter/product_supply/native-capability-contracts-accounting-nine.json',
          '4dfec613c3f4ad64084a7487d4f4d5ecadea8f177f1bcc7283637c4a8adcdefa'),
    'canonical-ten': ('superhunter/product_supply/native-capability-contracts-canonical-ten.json',
          'c3b7c10d1c72aacae73e09c5b96b521baeb9a8e6f4b15b03886ddcb8a16395c3'),
    'grpc-eleven': ('superhunter/product_supply/native-capability-contracts-grpc-eleven.json',
          'ae4a0e3a7026cd08083e144e92abb19f334ef816bfefeb4f4d79a48abf4dc003'),
    'html-twelve': ('superhunter/product_supply/native-capability-contracts-html-twelve.json',
          '1b0c5ecf4ec91e9f0a0ec45a0984c60ad615e37f9d0512474ed30dd2e3e19add'),
    140: ('superhunter/product_supply/native-capability-contracts-140.json',
          '7a1a414d48b995ac310b17f1e15d722001a3c0a510f3dcf5f43dedb6ae90e6ac'),
    139: ('superhunter/product_supply/native-capability-contracts-139.json',
          'e624bd12b6df9181e1a8db4520700267c57e9e566fd53d9f2d4aee28f10af3a4'),
    84: ('superhunter/product_supply/native-capability-contracts-84.json',
         '664d10946c40e197b443d0d9f745c72e5f6425e74662a403e84419fa1e9f6a8f'),
    70: ('superhunter/product_supply/native-capability-contracts-70.json',
         '1289b2523dca27657dcde15cb81c7a862e50c7f523c92d0e145238fee268d237'),
}
# Stable names retained for archived dossier readers.
CORE_EIGHT = HISTORICAL_CONTRACTS['core-eight']
ACCOUNTING_NINE = HISTORICAL_CONTRACTS['accounting-nine']
CANONICAL_TEN = HISTORICAL_CONTRACTS['canonical-ten']
GRPC_ELEVEN = HISTORICAL_CONTRACTS['grpc-eleven']

MODULES = {'evm': 'product_evm_native', 'web': 'product_web_native', 'static': 'product_static_native',
           'slither': 'product_slither_native', 'secrets': 'product_secrets_native',
           'http': 'product_http_native', 'discovery': 'product_discovery_native',
           'fuzz': 'product_fuzz_native', 'java': 'product_java_native',
           'properties': 'product_contract_properties_native', 'iam': 'product_iam_native',
           'upgrades': 'product_upgrade_layout_native',
           'rlp': 'product_rlp_library_native', 'mutation': 'product_mutation_native',
           'python_fuzz': 'product_python_fuzz_native', 'grpc': 'product_grpc_schema_native',
           'html_review': 'product_html_review'}


def add_arguments(parser):
    parser.add_argument('--native-kits', type=Path,
                        help='one JSON manifest mapping reviewed native groups to local kit directories')
    for group in MODULES:
        parser.add_argument('--' + group + '-native-kit', type=Path,
                            help='local kit for the reviewed ' + group + ' controls')


def selected_kits(options):
    kits = {}
    if options.native_kits:
        manifest = options.native_kits.resolve(strict=True)
        record = strict_json(read_artifact(manifest.parent, manifest.name))
        if not record or not set(record) <= set(MODULES):
            raise EvidenceError('native kit manifest names an unknown or empty group selection')
        for group, name in record.items():
            if type(name) is not str or not name or '\x00' in name:
                raise EvidenceError('native kit manifest contains an invalid directory')
            path = (manifest.parent/name).resolve(strict=True)
            if not path.is_dir():
                raise EvidenceError('native kit must be a local directory')
            kits[group] = path
    for group in MODULES:
        path = getattr(options, group + '_native_kit')
        if path is not None:
            if group in kits:
                raise EvidenceError('native group selected twice')
            kits[group] = path.resolve(strict=True)
            if not kits[group].is_dir():
                raise EvidenceError('native kit must be a local directory')
    return kits


def contracts(version=None):
    if version is not None and version not in HISTORICAL_CONTRACTS:
        raise EvidenceError('unknown historical native contract version')
    path, digest = (CONTRACT, CONTRACT_SHA) if version is None else HISTORICAL_CONTRACTS[version]
    raw = read_artifact(ROOT, path)
    if sha(raw) != digest:
        raise EvidenceError('native capability contracts differ from reviewed controls')
    record = strict_json(raw)
    if record.get('schema_version') != 1 or (version is None and set(record['groups']) != set(MODULES)):
        raise EvidenceError('native capability group contract differs')
    for group in record['groups'].values():
        if (not group.get('repositories') or not re.fullmatch('[0-9a-f]{64}', group.get('report_sha256', ''))
                or any(role not in ('executable', 'reference_data') for role in group['repositories'].values())):
            raise EvidenceError('invalid native capability role or result binding')
    names = [name.casefold() for group in record['groups'].values() for name in group['repositories']]
    if len(names) != len(set(names)):
        raise EvidenceError('native capability repositories overlap')
    return record['groups']


def expected_receipt(group, repository, contract):
    return {'query': 'native-capabilities', 'group': group, 'repository': repository,
            'role': contract['repositories'][repository], 'report_sha256': contract['report_sha256']}


def validate_receipt(row):
    name = row['repository'].casefold()
    for group, contract in contracts().items():
        for repository, role in contract['repositories'].items():
            if repository.casefold() == name:
                expected = expected_receipt(group, repository, contract)
                if row.get('native_capability_receipt') != expected:
                    raise EvidenceError('native capability receipt differs from accepted controls')
                return role, 'native_capability_receipt'
    raise EvidenceError('unregistered native capability receipt')


def attach(index, kits, *, allow_partial=False):
    expected = contracts()
    if not kits or not set(kits) <= set(MODULES):
        raise EvidenceError('unknown or empty native capability selection')
    reports, receipts, blocked = {}, {}, {}
    for group, kit in sorted(kits.items()):
        contract = expected[group]
        try:
            module = import_module('.' + MODULES[group], __package__)
            if module.REPOSITORIES != contract['repositories']:
                raise EvidenceError('native capability identities differ from reviewed group')
            report = module.run(kit)
            if sha(canonical(report)) != contract['report_sha256']:
                raise EvidenceError('native capability output differs from reviewed controls: ' + group)
            group_receipts = {}
            for repository in contract['repositories']:
                key = repository.casefold()
                if key not in index.repos or key in receipts:
                    raise EvidenceError('native capability identity is absent or duplicated')
                group_receipts[key] = expected_receipt(group, repository, contract)
        except (EvidenceError, ImportError, OSError, RuntimeError, ValueError, SubprocessError) as exc:
            if not allow_partial:
                raise
            # Child-process command lines may contain temporary directory names.
            # Only stable local validation diagnoses are exposed as evidence.
            message = str(exc) if isinstance(exc, EvidenceError) else 'native producer failed'
            blocked[group] = {'error_type': type(exc).__name__, 'message': message}
            continue
        reports[group] = report
        receipts.update(group_receipts)
    # Replace the previous selection in one commit, including removal of stale
    # receipts if a selected kit failed during a later run.
    for row in index.repos.values():
        row.pop('native_capability_receipt', None)
    for key, receipt in receipts.items():
        index.repos[key]['native_capability_receipt'] = receipt
    # A report consumer may reuse only a kit whose native controls just passed.
    index.verified_web_kit = kits['web'] if 'web' in reports else None
    index.native_capabilities = {'groups': reports, 'repositories': sorted(receipts),
                                 'functional_participations': len(receipts),
                                 'scope': 'fixed_owned_controls_and_pinned_local_inputs',
                                 'original_vulnerabilities_confirmed': 0}
    if blocked:
        index.native_capabilities['blocked_groups'] = blocked
    return index.native_capabilities
