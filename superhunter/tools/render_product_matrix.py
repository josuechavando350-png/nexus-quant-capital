"""Render a product session or independently verify the two frozen historical sessions."""
import argparse
from collections import Counter
import os
from pathlib import PurePosixPath
import re
import subprocess
import sys

from superhunter.product_matrix import markdown

from superhunter.product_reasoning import EvidenceError
from superhunter.product_review import ROOT, sha
from superhunter.safe_io import read_artifact, strict_json
from superhunter.tools import verify_native_session, verify_review_115

MATRIX = ROOT / 'superhunter/INTEGRATION_STATUS_200.md'
DOSSIER = 'superhunter/product_supply/consolidated-acceptance'
ROLE = {'executable': 'Ejecución', 'reference_data': 'Referencia', 'pending': '—'}


def read_session(raw, expected_sha, verify):
    result = verify(raw, expected_sha)
    keys = verify_review_115.response_keys(raw)
    lines = raw.splitlines()
    rows = strict_json(lines[keys.index('integration-matrix')])['rows']
    operations = {}
    if 'component-controls' in keys:
        observations = strict_json(lines[keys.index('component-controls')])['observations']
        operations = {name: obs['operation'] for name, obs in observations.items()}
    elif 'native-capabilities' in keys:
        for row in rows:
            if row['receipt'] == 'native_capability_receipt':
                entry = strict_json(lines[keys.index(row['repository'])])
                operations[row['repository']] = entry['native_capability_receipt']['group']
    return result, rows, operations


def receipt(row, operations):
    if row['session'] == 'pending':
        return '—'
    label = ROLE[row['session']] + ' · `' + row['receipt'] + '`'
    operation = operations.get(row['repository'])
    if operation:
        label += ' · ' + operation.replace('|', '\\|')
    return label + ' · `' + row['session_evidence_sha256'] + '`'


def current_receipts(operations):
    return ' / '.join(f"{ROLE[op['role']]} · `{op['receipt']}` · `{op['evidence_sha256']}`"
                      for op in operations) or '—'


def render(components, native, *, current=None, producer=None):
    left, component_rows, component_ops = components
    right, native_rows, native_ops = native
    counts = Counter()
    overlap = 0
    details = []
    current_rows = current[1] if current else [None] * len(component_rows)
    for a, b, c in zip(component_rows, native_rows, current_rows, strict=True):
        if any(a[key] != b[key] for key in ('id', 'repository', 'commit', 'tree')):
            raise EvidenceError('historical sessions disagree on identity, revision or tree')
        if c is not None and any(a[key] != c[key] for key in ('id', 'repository', 'commit', 'tree')):
            raise EvidenceError('current session disagrees on identity, revision or tree')
        roles = (a['session'], b['session'])
        overlap += 'pending' not in roles
        role = next(r for r in ROLE if r in roles)
        counts[role] += 1
        name, commit = a['repository'], a['commit']
        details.append(f"| {a['id']} | [{name}](https://github.com/{name}/tree/{commit}) | `{commit}` | "
                       f"{receipt(a, component_ops)} | {receipt(b, native_ops)} |")
        if c is not None:
            details[-1] += f" {current_receipts(c['session_operations'])} |"
    union = counts['executable'] + counts['reference_data']
    repo = 'https://github.com/josuechavando350-png/nexus-quant-capital'
    status = 'Aceptación conjunta verificada' if current else 'Aceptación conjunta pendiente'
    lines = [
        '# SUPERHUNTER · Matriz de integración', '',
        f"**{status}.** Los dos archivos históricos contienen {union} identidades distintas. "
        f"De ellas, {counts['executable']} ejecutaron código y {counts['reference_data']} aportaron referencias. "
        f"Hay {counts['pending']} identidades sin participación en estos archivos.", '',
        '| Evidencia histórica | Respuestas | Identidades | Ejecución | Referencias |',
        '|---|---:|---:|---:|---:|',
    ]
    for label, result in (('[PR 118](product_supply/component-session-99.json)', left),
                          ('[PR 119](product_supply/native-session-70.json)', right)):
        lines.append(f"| {label} | {result['responses']} | {result['session']} | {result['executables']} | "
                     f"{result['reference_data']} |")
    if current:
        result = current[0]
        lines.extend(['', f"**{result['session']}/{result['catalog']} identidades** participaron en ambas ejecuciones "
                      f"del producto. Hubo {result['executables']} de ejecución, {result['reference_data']} de referencia, "
                      f"{result['operations']} operaciones y {result['catalog'] - result['session']} identidades pendientes.",
                      '', f"Los expedientes registran dos checkouts limpios en el mismo host, código de salida cero "
                      f"y {result['responses']} respuestas iguales por ejecución. El productor fue el "
                      f"[commit {producer['commit']}]({repo}/commit/{producer['commit']}) con árbol "
                      f"`{producer['tree']}` y la transcripción tiene SHA-256 `{result['transcript_sha256']}`. "
                      "[Acta y huellas de los dos expedientes](product_supply/consolidated-acceptance/acceptance.json)",
                      '', "Archivos preparados con huellas distintas entre los expedientes: "
                      + (', '.join(f'`{path}`' for path in producer['different_inputs']) or 'ninguno') + '. '
                      + ('Los manifiestos nativos tienen huellas distintas.' if producer['different_native_manifest']
                         else 'Coincide la huella de los manifiestos nativos.')])
    pending = '' if current else (' El conteo actual de integraciones conjuntas, ejecuciones, referencias y '
                                  'pendientes requiere una sesión completa del commit publicado y su reproducción.')
    lines.extend([
        '', f"Ambos archivos comparten {overlap} identidades. Hay {left['session'] - overlap} exclusivas "
        f"del primero y {right['session'] - overlap} del segundo.{pending}",
        '', f"El inventario del PR 119 verificó {right['sources']['complete']} fuentes directas. Las dos "
        f"transcripciones identifican {len(details)} revisiones. Se conservaron los 153 pines previos. "
        "La materialización de 141 gitlinks anidados y un objeto LFS, las licencias transitivas y la "
        "compatibilidad comercial siguen pendientes. Hallazgos originales confirmados en estos expedientes, cero. "
        "[Alcance de fuentes](SOURCE_CHECKOUT.md) · [Acta de adquisición](product_supply/source-completion-200.json)",
        '', 'El archivo de 99 identifica el árbol productor `efe9581f1647c0bb3f2aaad0f0a166b0f8768722`, '
        f"también presente en [el commit fc6e737]({repo}/commit/fc6e7375f832ee0a678eab9d940e547f61144201). El productor del archivo de 70 "
        "declaró cambios locales sobre su commit base. [Acta de 70](product_supply/native-acceptance-70.json) · "
        f"[Matriz anterior del PR 117]({repo}/blob/672c31392929b8efbd6b3d5983c44e8560232add/"
        'superhunter/INTEGRATION_STATUS_200.md)',
        '', 'Cada celda indica el rol, el campo del recibo y su SHA-256 en la sesión indicada. '
        'La raya indica ausencia de participación en ese archivo. Los enlaces a las fuentes apuntan a sus revisiones.',
        '', '| ID | Repositorio | Revisión Git | PR 118 histórico | PR 119 histórico |'
        + (' Sesión conjunta |' if current else ''), '|---:|---|---|---|---|' + ('---|' if current else ''),
        *details, '', 'Comprobación sin red desde la raíz del repositorio mediante '
        f"`python3.12 -B -m superhunter.tools.render_product_matrix --check-{'acceptance' if current else 'historical'}`.", '',
    ])
    return '\n'.join(lines)


def historical_markdown(**kwargs):
    components, native = verify_review_115.historical_archives()
    components = read_session(*components, verify_review_115.verify)
    native = read_session(*native, verify_native_session.verify)
    return render(components, native, **kwargs)


def digest(value, width=64):
    return isinstance(value, str) and re.fullmatch(f'[0-9a-f]{{{width}}}', value) is not None


def require_producer(commit, tree, inputs):
    if not digest(commit, 40) or not digest(tree, 40):
        raise EvidenceError('expected full Git commit and tree IDs')
    def git(*args):
        return subprocess.check_output(['git', '--no-replace-objects', '-C', str(ROOT), *args],
                                       stderr=subprocess.DEVNULL, timeout=30,
                                       env={**os.environ, 'GIT_NO_LAZY_FETCH': '1', 'GIT_ALLOW_PROTOCOL': ''})
    try:
        if git('cat-file', '-t', commit) != b'commit\n' or git('rev-parse', commit + '^{tree}').decode().strip() != tree:
            raise EvidenceError('producer Git tree differs from the run record')
        source_tree = git('rev-parse', commit + ':upstream').decode().strip()
        contract_sha = sha(git('show', commit + ':superhunter/product_supply/native-capability-contracts.json'))
    except subprocess.CalledProcessError as exc:
        raise EvidenceError('producer Git objects unavailable; fetch the published producer commit into this checkout') from exc
    if inputs['git_source_tree'] != source_tree or inputs['native_contract_sha256'] != contract_sha:
        raise EvidenceError('run source tree or native contract disagrees with the producer commit')


def run_evidence(record, run_id):
    if record.get('id') != run_id:
        raise EvidenceError('two distinct ordered execution dossiers are required')
    checkout = record.get('checkout')
    if not isinstance(checkout, str) or not checkout or PurePosixPath(checkout).is_absolute() or any(
            part in ('', '.', '..') for part in checkout.split('/')):
        raise EvidenceError('expected a relative checkout identifier')
    def artifact(filename, key):
        data = read_artifact(ROOT, f'{DOSSIER}/{run_id}/{filename}')
        if sha(data) != record.get(key):
            raise EvidenceError(f'{run_id} dossier digest differs for {filename}')
        return data
    inputs = strict_json(artifact('run-inputs.json', 'inputs_sha256'))
    result = strict_json(artifact('result.json', 'result_sha256'))
    raw = verify_review_115.unpack(artifact('session.json', 'archive_sha256'))
    if (inputs.get('checkout_clean_before') is not True or result.get('clean_after') is not True
            or type(result.get('returncode')) is not int or result['returncode'] != 0
            or type(result.get('responses')) is not int or result['responses'] != len(raw.splitlines())
            or result['responses'] != 222 or type(result.get('bytes')) is not int or result['bytes'] != len(raw) or result.get('sha256') != sha(raw)
            or (inputs.get('commit'), inputs.get('tree')) != (result.get('commit'), result.get('tree'))):
        raise EvidenceError('run result disagrees with the transcript, clean checkout or producer')
    if (not all(digest(inputs.get(k)) for k in ('raw_run_inputs_sha256', 'native_manifest_sha256', 'kit_manifest_sha256'))
            or set(inputs.get('prepared_files', {})) != {
                'product/COMPLETE.json', 'product/review.json', 'product/solver.json', 'product/syft.json',
                'supply/COMPLETE.json', 'supply/asvs-guides.md', 'supply/asvs.csv', 'supply/supply.json', 'supply/supply.link'}
            or not all(digest(d) for d in inputs['prepared_files'].values())):
        raise EvidenceError('missing or invalid original input receipts')
    argv = inputs.get('argv')
    if (not isinstance(argv, list) or not all(isinstance(arg, str) for arg in argv)
            or not {'--net', '--review-queries', '--native-kits', '--native-inputs'}.issubset(argv)
            or 'superhunter.tools.catalog_session' not in argv or '--component-controls' not in argv
            or argv[argv.index('--component-controls') + 1:][:1] != ['all']):
        raise EvidenceError('execution dossier lacks the reviewed offline query profile')
    require_producer(result['commit'], result['tree'], inputs)
    return inputs, result, raw


def accepted_markdown():
    act = strict_json(read_artifact(ROOT, DOSSIER + '/acceptance.json'))
    if (type(act.get('schema_version')) is not int or act['schema_version'] != 1 or act.get('same_host') is not True
            or not isinstance(act.get('runs'), list) or len(act['runs']) != 2
            or not all(isinstance(record, dict) for record in act['runs'])):
        raise EvidenceError('expected exactly two same-host execution records')
    first, second = act['runs']
    if first.get('checkout') == second.get('checkout'):
        raise EvidenceError('two distinct checkouts are required')
    left, result, raw = run_evidence(first, 'first')
    right, replay, other = run_evidence(second, 'second')
    if left['raw_run_inputs_sha256'] == right['raw_run_inputs_sha256'] and first['result_sha256'] == second['result_sha256']:
        raise EvidenceError('the same input and result record was used for both runs')
    if (result['commit'], result['tree']) != (replay['commit'], replay['tree']):
        raise EvidenceError('execution records identify different producer commits or trees')
    verified = verify_review_115.verify(raw, result['sha256'], require_consolidated=True)
    verify_review_115.verify(other, replay['sha256'], require_consolidated=True)
    if raw != other:
        raise EvidenceError('the full transcripts differ between the two checkout runs')
    keys = verify_review_115.response_keys(raw)
    rows = strict_json(raw.splitlines()[keys.index('integration-matrix')])['rows']
    producer = {**result, 'different_inputs': sorted(key for key, value in left['prepared_files'].items()
                                                    if right['prepared_files'][key] != value),
                'different_native_manifest': left['native_manifest_sha256'] != right['native_manifest_sha256']}
    return historical_markdown(current=(verified, rows), producer=producer)


def main():
    if {'--historical', '--check-historical', '--acceptance', '--check-acceptance'} & set(sys.argv[1:]):
        parser = argparse.ArgumentParser(description=__doc__)
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument('--historical', action='store_true', help='render the two frozen sessions')
        mode.add_argument('--check-historical', action='store_true', help='verify the tracked historical matrix')
        mode.add_argument('--acceptance', action='store_true', help='render the two verified checkout runs')
        mode.add_argument('--check-acceptance', action='store_true', help='check the matrix against both runs')
        args = parser.parse_args()
        if args.acceptance or args.check_acceptance:
            try:
                rendered = accepted_markdown()
            except (EvidenceError, ValueError, OSError, KeyError, TypeError) as error:
                print(f'acceptance unavailable: {error}', file=sys.stderr)
                return 2
        else:
            rendered = historical_markdown()
        if args.check_historical or args.check_acceptance:
            if MATRIX.read_bytes() != rendered.encode('utf-8'):
                raise SystemExit('tracked matrix differs from verified evidence')
        else:
            sys.stdout.write(rendered)
        return 0

    cmd = [sys.executable, '-B', '-m', 'superhunter.tools.catalog_session', *sys.argv[1:], 'integration-matrix']
    proc = subprocess.run(cmd, capture_output=True, timeout=600)
    if proc.returncode:
        sys.stderr.buffer.write(proc.stdout + proc.stderr)
        return proc.returncode
    sys.stdout.write(markdown(strict_json(proc.stdout)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
