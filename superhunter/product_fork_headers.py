"""Use pinned client data and a Hive corpus to decide how to validate two fixed historical headers."""
from . import product_census_header as census
from .product_reasoning import EvidenceError
from .product_review import ROOT, sha
from .product_sources import git
from .repository_boundary import git_object
from .safe_io import canonical, read_artifact, strict_json

SOURCES = {
    'paradigmxyz/reth': ('upstream/175-reth', '53b5db1c3bc841bae679e58a625485d3d44d5b74',
                         {'hoodi': ('crates/chainspec/res/genesis/hoodi.json', '4b6b5713490ff9adabca742b7864f866dd124203')}),
    'besu-eth/besu': ('upstream/176-besu', '10dc5130f7424488cc5730fca1e98565a313714b',
                      {'mainnet': ('config/src/main/resources/mainnet.json', '48278986a699799d6aeca615a4170df6fd991843'),
                       'hoodi': ('config/src/main/resources/hoodi.json', '1433e48c970339ef6011ab33ab822e4ef33efbd5')}),
    'ethereum/hive': ('upstream/177-hive', 'befb5c9edf4e1df25351e2a4ebdaca15e3d5d01b',
                      {k: ('simulators/ethereum/sync/chain/' + k + '.json', oid) for k, oid in (
                          ('genesis', 'd28bb525d1b5cc92e4c65fdbb15ddf371f65c75b'),
                          ('headblock', '445cad762489de4a3c99d77e9ffcd70d0c496fa8'),
                          ('headnewpayload', '39fce1189642cb3554899f3475283bd89ca01062'),
                          ('headfcu', 'f84d9e5a625f30fdbbc2ba430d071a5f1354cc2c'))})}
FORK_FIELDS = {'shanghai': ('withdrawalsRoot',), 'cancun': ('blobGasUsed', 'excessBlobGas', 'parentBeaconBlockRoot'),
               'prague': ('requestsHash',)}


def read_inputs(checkout):
    results = {}
    for name, (directory, revision, files) in SOURCES.items():
        root = checkout/directory
        if git(root, 'rev-parse', 'HEAD').decode().strip() != revision:
            raise EvidenceError('fork reference source at wrong revision')
        inputs = {}
        for label, (path, oid) in files.items():
            raw = read_artifact(root, path)
            if git(root, 'rev-parse', revision + ':' + path).decode().strip() != oid or git_object('blob', raw) != oid:
                raise EvidenceError('fork reference blob differs from reviewed source')
            inputs[label] = strict_json(raw)
        results[name] = inputs
    return results


def schedule(genesis, chain):
    config = genesis['config']
    if type(config.get('chainId')) is not int or config['chainId'] != chain:
        raise EvidenceError('input belongs to another chain')
    times = {fork: config[fork + 'Time'] for fork in FORK_FIELDS if fork + 'Time' in config}
    if (not times or list(times) != list(FORK_FIELDS)[:len(times)] or
            any(type(t) is not int or t < 0 for t in times.values()) or
            list(times.values()) != sorted(times.values())):
        raise EvidenceError('invalid or incomplete activation schedule')
    return times


def active(times, timestamp):
    return [fork for fork, start in times.items() if timestamp >= start]


def discrepancies(header, times):
    forks = active(times, int(header['timestamp'], 16))
    return sorted(key for name, keys in FORK_FIELDS.items() for key in keys
                  if (header.get(key) is not None) != (name in forks))


def boundary_agreement(first, second):
    if first != second:
        raise EvidenceError('clients disagree on fork activations')
    boundaries = sorted({t for start in first.values() for t in (start-1, start) if t >= 0})
    return [{'timestamp': t, 'active': active(first, t)} for t in boundaries]


def hive_payload(header, fixtures):
    payload, _, parent = fixtures['headnewpayload']['params']
    forkchoice = fixtures['headfcu']['params'][0]
    aliases = {'blockHash': 'hash', 'feeRecipient': 'miner', 'blockNumber': 'number', 'prevRandao': 'mixHash'}
    shared = ('parentHash', 'stateRoot', 'receiptsRoot', 'logsBloom', 'gasLimit', 'gasUsed', 'timestamp',
              'extraData', 'baseFeePerGas', 'blobGasUsed', 'excessBlobGas')
    if (fixtures['headnewpayload']['method'] != 'engine_newPayloadV3' or
            fixtures['headfcu']['method'] != 'engine_forkchoiceUpdatedV3' or
            parent != header['parentBeaconBlockRoot'] or forkchoice['headBlockHash'] != header['hash'] or
            any(payload[k] != header[v] for k, v in aliases.items()) or any(payload[k] != header[k] for k in shared)):
        raise EvidenceError('independent Hive block records disagree')
    return len(aliases) + len(shared)


def build(checkout, kit, receipt):
    if checkout is None or kit is None or receipt is None or receipt['fixture_sha256'] != census.FIXTURE_SHA:
        raise EvidenceError('fork selection requires the verified Census header and checked out references')
    inputs = read_inputs(checkout)
    besu, reth, hive = (inputs[k] for k in ('besu-eth/besu', 'paradigmxyz/reth', 'ethereum/hive'))
    controls = boundary_agreement(schedule(reth['hoodi'], 560048), schedule(besu['hoodi'], 560048))
    mainnet = schedule(besu['mainnet'], 1)
    fixed = strict_json(census.pinned(ROOT, census.FIXTURE, census.FIXTURE_SHA))['block']
    times = schedule(hive['genesis'], 3503995874084926)
    block = hive['headblock']
    mainnet_forks = active(mainnet, int(fixed['timestamp'], 16))
    hive_forks = active(times, int(block['timestamp'], 16))
    if (mainnet_forks[-1:] != ['prague'] or hive_forks[-1:] != ['cancun'] or
            discrepancies(fixed, mainnet) or discrepancies(block, times)):
        raise EvidenceError('fixed headers disagree with their network schedule')
    if fixed['hash'] != receipt['cases']['original']['keccak256']:
        raise EvidenceError('fork selected for different Census evidence')
    remove = discrepancies({**fixed, 'requestsHash': None}, mainnet)
    add = discrepancies({**block, 'requestsHash': fixed['requestsHash']}, times)
    if remove != ['requestsHash'] or add != ['requestsHash']:
        raise EvidenceError('fork-field controls failed')
    shared = hive_payload(block, hive)
    fields = census.field_order(census.pinned(ROOT, census.CENSUS, census.CENSUS_SHA).decode(),
                                census.pinned(kit, 'blocks.py', census.SPEC_SHA))
    inactive_fields = {field for fork, keys in FORK_FIELDS.items() if fork not in hive_forks for field in keys}
    selected_fields = [field for field in fields if field[0] not in inactive_fields]
    cases, _ = census.native_comparison(kit, block, selected_fields, hive_forks[-1])
    return {'census_sha256': sha(canonical(receipt)), 'mainnet_schedule': mainnet, 'mainnet_selected': mainnet_forks[-1],
            'hoodi_boundary_checks': controls, 'hive_selected': hive_forks[-1], 'hive_schedule': times,
            'hive_payload_fields_compared': shared, 'hive_hash_cases': cases,
            'mainnet_removed_field_control': remove, 'hive_premature_field_control': add}


def attach(index, checkout, kit):
    result = build(checkout, kit, index.census_header)
    index.fork_headers = result
    for name, (_, revision, files) in SOURCES.items():
        index.repos[name]['fork_header_reference'] = {
            'query': 'fork-headers', 'revision': revision, 'files': {k: p[1] for k, p in files.items()},
            'result_sha256': sha(canonical(result))}
