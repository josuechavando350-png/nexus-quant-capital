"""Test lossless integer representation of the seven frozen Census WAD fields."""
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile

from .product_notice_ranking import ISOLATE
from .product_reasoning import EvidenceError
from .product_review import ROOT, sha
from .product_sources import git
from .safe_io import canonical, read_artifact, strict_json

INPUT = 'ci/nqc-census/rmc016-production-evidence.json'
INPUT_SHA = '6f128949f4062068898b81130b01fb7f8dfc0068e82ee8d6a9d5b166050e0cfc'
SDK = 'cosmos/cosmos-sdk'
IBC = 'lfdt-ibc/ibc-go'
CW = 'CosmWasm/cosmwasm'
SUI = 'MystenLabs/sui'
CAIRO = 'starkware-libs/cairo'
GO_SHA = 'de0ae3e082ce7599eae4fb69fa2ef1e43b8f31ffd3fce62cdf81930aa9005050'
DRIVER = 'superhunter/product_supply/census-state-amounts.go.txt'
BINARY_SHA = '606b9b741a14f37ae2164782f5cf5525d08d1e57efdf555f846123a104c92ede'

UPSTREAM = {
    'lfdt-ibc/ibc-go': ('184-ibc-go', '873b622380fbbce76ac407c6e0299fcbec557045', {
        'modules/apps/transfer/types/token.go':
            '8e52dadbe0b352845e3d2489488d740b82984332d898c6757cd9d1a99de2cf1f',
        'proto/ibc/applications/transfer/v1/token.proto':
            'ce9e7f1d2cc20f3c15608bacee7b8f4f512009a706bed19f986c5cc331791cd3',
    }),
    'CosmWasm/cosmwasm': ('185-cosmwasm', 'b7da6a4d373f5fdb7cd752f855271ed9909ec1ce', {
        'contracts/staking/schema/raw/response_to_balance.json':
            '3cd4800828d1f0a92ddaf2257924fd153029da547db094dd063120d1f52612f3',
        'contracts/staking/schema/cw_schema/raw/response_to_balance.json':
            'fd6be0e2b08a3b7d4ad73f6c5911ae32a2c5ef63bb029943ca2f5cb5fab6fc72',
    }),
    'cosmos/cosmos-sdk': ('186-cosmos-sdk', '0c3dd0e3eb5413ea86fddaa9e8fbe8c16fda815b', {
        'math/go.mod':
            '4ab0b987ac4a4456550bcb4d9c50f33945fe320c14170583ed497570d6a5817c',
        'math/go.sum':
            '5f9ce25e29e7ae8a14bb6fa1e46d979852816ab24a2b22aae041c97d4a5280bd',
        'math/doc.go':
            'cee16dd9f2e0481576d8c4f18656f56c688aec7c0aa4fe981ab8505c07a919bf',
        'math/int.go':
            '27b2907f922f6f0634e7110e2d18fdb2d75926e723fd8c7f79c7c8d27e128f45',
        'math/legacy_dec.go':
            'a8b380791b7628bd285e1e96afc613ce9b43f841939042c7eb5ee566fe502daf',
        'math/max_min.go':
            '69a2fa3a22e8a2e9ba0ba3a98f69434c3afc7df3c3146d19c48caf81a707de90',
        'math/proto.go':
            '4dc8b807453b5a0b40313015f6c19403878fb4aa0dab1bc102edfc952c29672b',
        'math/uint.go':
            'b418c399db90084dc780e2a7816de26ac501ecbc89eecc8ab66de57254f51bc7',
    }),
    'MystenLabs/sui': ('187-sui', 'f0f5a5f03da8ae1a90c3858dafcfa460f851fcf4', {
        'crates/sui-types/src/balance.rs':
            'd51a3f7310b5d7801163a99ce567b1876094a812b186de20da1d1054cdff6b07',
    }),
    'starkware-libs/cairo': ('188-cairo', '4a078b123ce242b2a04c0eaae790a976a8da469a', {
        'corelib/src/integer.cairo':
            '322f20c008159217226b7a5963e94e8a2d4d4acfe8055408ac1b386cf50bc852',
    }),
}


def need(ok, reason):
    if not ok:
        raise EvidenceError('Census amount formats: ' + reason)


def source_files(root):
    files = {}
    for repo, (dirname, revision, hashes) in UPSTREAM.items():
        checkout = Path(root) / dirname
        need(git(checkout, 'rev-parse', 'HEAD').decode().strip() == revision, 'different pin for ' + repo)
        for path, digest in hashes.items():
            raw = read_artifact(checkout, path)
            need(sha(raw) == digest, 'different source at ' + path)
            files[path] = raw
    return files


def shape(files):
    specs = UPSTREAM[CW][2]
    wire, types = [strict_json(files[path]) for path in specs]
    query = wire['properties']['balance']['$ref'].split('/')[-1]
    node = types['definitions'][types['root']]
    amount = types['definitions'][node['properties']['balance']['value']]
    need(wire['required'] == ['balance'] and wire['additionalProperties'] is False
         and wire['definitions'][query]['type'] == 'string' and not amount['signed']
         and amount['type'] == 'integer' and amount['name'].endswith('_' + query), 'Wasm response schema')

    sui = files[next(iter(UPSTREAM[SUI][2]))].decode()
    storage = re.search(r'pub struct Balance \{\s+value: u(\d+),\s*\}', sui)
    layout = re.search(r'ident_str!\("value"\).to_owned\(\),\s*MoveTypeLayout::U(\d+)', sui)
    need(storage and layout and storage[1] == layout[1], 'Sui storage and wire layout disagree')

    cairo = files[next(iter(UPSTREAM[CAIRO][2]))].decode()
    limbs = re.search(r'#\[derive\([^\n]*Serde\)\]\s*pub struct u256 \{\s*pub (\w+): u(\d+),'
                      r'\s*pub (\w+): u(\d+),\s*\}', cairo)
    need(limbs and (limbs[1], limbs[3]) == ('low', 'high') and limbs[2] == limbs[4], 'Cairo limb layout')

    validation, proto = [files[p].decode() for p in UPSTREAM[IBC][2]]
    need(re.search(r'message Token \{[^}]*\bstring amount = 2;', proto)
         and re.search(r'amount, ok := sdkmath.NewIntFromString\(t.Amount\).*?if !ok \{\s*return .*?'
                       r'if !amount.IsPositive\(\) \{\s*return ', validation, re.S),
         'IBC amount validation differs')
    return amount['precision'], int(storage[1]), int(limbs[2])


def inputs():
    raw = read_artifact(ROOT, INPUT)
    need(sha(raw) == INPUT_SHA, 'unreviewed historical input')
    selected = {name: value for name, value in strict_json(raw)['authority'].items() if name.endswith('_wad')}
    need(len(selected) == 7 and all(type(value) is str and re.fullmatch(r'0|[1-9][0-9]*', value)
                                    for value in selected.values()), 'unexpected WAD fields')
    return selected


def build(files, work, target, go):
    need(go.is_file(), 'Go 1.27.4 required')
    with go.open('rb') as stream:
        need(hashlib.file_digest(stream, 'sha256').hexdigest() == GO_SHA, 'Go executable differs')
    package = work/'sdkmath'
    package.mkdir()
    for name in UPSTREAM[SDK][2]:
        (package / Path(name).name).write_bytes(files[name])
    (work/'go.mod').write_text('module nqc.local/amounts\n\ngo 1.27.4\n\nrequire cosmossdk.io/math v1.0.0\n'
                               'replace cosmossdk.io/math => ./sdkmath\n')
    (work/'main.go').write_bytes(read_artifact(ROOT, DRIVER))
    env = {'GOROOT': str(go.parent.parent), 'GOCACHE': str(work/'gocache'), 'GOPATH': str(work/'gopath'),
           'GOSUMDB': 'off', 'GOPROXY': 'off', 'GOTOOLCHAIN': 'local', 'GOENV': 'off', 'CGO_ENABLED': '0',
           'HOME': str(work), 'TMPDIR': str(work/'tmp'), 'LANG': 'C', 'PATH': os.defpath}
    (work/'tmp').mkdir()
    try:
        subprocess.run([*ISOLATE, go, 'build', '-p', '2', '-trimpath', '-mod=readonly', '-buildvcs=false',
                        '-ldflags=-buildid=', '-o', target, '.'], cwd=work, env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=180)
    except (OSError, subprocess.SubprocessError) as exc:
        raise EvidenceError('Census amount formats: SDK offline build failed') from exc


def observe(source, runner):
    controls = {'u64_max': str(2**64-1), 'over_u64': str(2**64),
                'u128_max': str(2**128-1), 'over_u128': str(2**128), 'u256_max': str(2**256-1),
                'over_u256': str(2**256), 'negative': '-1', 'exponent': '1e3', 'leading_zero': '01',
                'not_binary64_exact': str(2**53+1)}
    values = dict(source, **controls)
    items = list(values.items())
    with tempfile.TemporaryDirectory(prefix='nqc-amount-run-') as tmp:
        raw = subprocess.run([*ISOLATE, runner], input=canonical([text for _, text in items]),
                             cwd=tmp, env={'LANG': 'C'}, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             check=True, timeout=10).stdout
    rows = strict_json(raw)['rows']
    need(len(rows) == len(items), 'SDK dropped a quantity')
    return dict(zip(values, rows, strict=True)), values, controls


def compare(text, sdk, widths):
    cw, sui, limb = widths
    digits = re.fullmatch(r'0|[1-9][0-9]*', text) is not None
    number = int(text) if digits else None
    accepted = digits and number < (1 << (2*limb))
    need(sdk['text'] == text and ((sdk['uint'] and sdk['canonical'] == text) == accepted),
         'unbounded integer oracle disagrees with SDK normalization')
    if not accepted:
        return {'representable': False}
    need(sdk['bits'] == number.bit_length() and sdk['positive'] == (number > 0),
         'SDK bit length or positivity disagrees')
    low = number & ((1 << limb) - 1)
    high = number >> limb
    # Independent decode proceeds from a fixed-width big-endian byte string.
    be = number.to_bytes(2 * limb // 8, 'big')
    split = len(be) // 2
    need((high, low) == (int.from_bytes(be[:split], 'big'), int.from_bytes(be[split:], 'big')),
         'limb round trip differs')
    return {'representable': True, 'normalized_decimal': sdk['canonical'], 'bits': sdk['bits'],
            'ibc_positive_amount': sdk['positive'], 'wasm_response_uint_fits': number < 1 << cw,
            'sui_balance_fits': number < 1 << sui, 'cairo_low_high': [str(low), str(high)]}


def review(source_root):
    files = source_files(source_root)
    widths = shape(files)
    need(widths == (128, 64, 128), 'unknown amount type widths')
    source = inputs()
    with tempfile.TemporaryDirectory(prefix='nqc-amounts-') as tmp:
        work = Path(tmp)
        runner = work/'amounts'
        supplied = os.environ.get('NQC_STATE_HELPER')
        if supplied:
            candidate = Path(supplied)
            need(candidate.stat().st_size < 12_000_000, 'unexpected helper size')
            raw = candidate.read_bytes()
            need(sha(raw) == BINARY_SHA, 'unreviewed cached SDK binary')
            runner.write_bytes(raw)
            runner.chmod(0o500)
        else:
            build(files, work, runner, Path(os.environ.get('NQC_STATE_GO', '/no-state-go')).resolve())
        need(sha(runner.read_bytes()) == BINARY_SHA, 'SDK binary differs from two independent builds')
        observations, values, controls = observe(source, runner)
    reports = {key: compare(txt, observations[key], widths) for key, txt in values.items()}
    actual = {key: reports[key] for key in source}
    checks = {key: reports[key] for key in controls}
    need(all(row['representable'] for row in actual.values())
         and checks['u64_max']['sui_balance_fits'] and not checks['over_u64']['sui_balance_fits']
         and checks['u128_max']['wasm_response_uint_fits'] and not checks['over_u128']['wasm_response_uint_fits']
         and checks['over_u128']['cairo_low_high'] == ['0', '1']
         and checks['u256_max']['representable'] and not any(checks[k]['representable']
             for k in ('over_u256', 'negative', 'exponent', 'leading_zero'))
         and checks['not_binary64_exact']['normalized_decimal'] == str(2**53+1), 'boundary control failed')
    roles = {SDK: ('executable', 'Cosmos SDK integer parsing and JSON round trips'),
             IBC: ('reference', 'positive-amount constraint from the IBC token schema and validator'),
             CW: ('reference', 'staking response shape and unsigned precision from both Wasm schemas'),
             SUI: ('reference', 'Sui Balance storage and Move value layout'),
             CAIRO: ('reference', 'Serde u256 field order and limb widths')}
    return {repo: {'revision': UPSTREAM[repo][1], 'role': role, 'operation': operation,
                   'source_files': UPSTREAM[repo][2], 'input_sha256': INPUT_SHA, 'results': actual,
                   'controls': checks, 'go_binary_sha256': GO_SHA, 'sdk_runner_sha256': BINARY_SHA}
            for repo, (role, operation) in roles.items()}
