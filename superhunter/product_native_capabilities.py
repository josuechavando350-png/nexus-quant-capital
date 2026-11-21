"""Join native, locally reproduced capability controls to the product index."""
from importlib import import_module
from pathlib import Path
import re

from .product_reasoning import EvidenceError
from .product_review import ROOT, sha
from .safe_io import canonical, read_artifact, strict_json

CONTRACT = 'superhunter/product_supply/native-capability-contracts.json'
CONTRACT_SHA = '1289b2523dca27657dcde15cb81c7a862e50c7f523c92d0e145238fee268d237'
MODULES = {'evm': 'product_evm_native', 'web': 'product_web_native', 'static': 'product_static_native',
           'slither': 'product_slither_native', 'secrets': 'product_secrets_native'}


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


def contracts():
    raw = read_artifact(ROOT, CONTRACT)
    if sha(raw) != CONTRACT_SHA:
        raise EvidenceError('native capability contracts differ from reviewed controls')
    record = strict_json(raw)
    if record.get('schema_version') != 1 or set(record['groups']) != set(MODULES):
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


def attach(index, kits):
    expected = contracts()
    if not kits or not set(kits) <= set(MODULES):
        raise EvidenceError('unknown or empty native capability selection')
    reports, receipts = {}, {}
    for group, kit in sorted(kits.items()):
        module = import_module('.' + MODULES[group], __package__)
        contract = expected[group]
        if module.REPOSITORIES != contract['repositories']:
            raise EvidenceError('native capability identities differ from reviewed group')
        report = module.run(kit)
        if sha(canonical(report)) != contract['report_sha256']:
            raise EvidenceError('native capability output differs from reviewed controls: ' + group)
        reports[group] = report
        for repository in contract['repositories']:
            key = repository.casefold()
            if key not in index.repos or key in receipts:
                raise EvidenceError('native capability identity is absent or duplicated')
            receipts[key] = expected_receipt(group, repository, contract)
    # A failed producer never publishes a partially accepted capability group.
    for key, receipt in receipts.items():
        index.repos[key]['native_capability_receipt'] = receipt
    index.native_capabilities = {'groups': reports, 'repositories': sorted(receipts),
                                 'functional_participations': len(receipts),
                                 'scope': 'fixed_owned_controls_and_pinned_local_inputs',
                                 'original_vulnerabilities_confirmed': 0}
    return index.native_capabilities
