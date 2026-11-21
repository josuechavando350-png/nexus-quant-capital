"""Render a product session or independently verify the two frozen historical sessions."""
import argparse
from collections import Counter
import subprocess
import sys

from superhunter.product_matrix import markdown

from superhunter.product_reasoning import EvidenceError
from superhunter.product_review import ROOT, sha
from superhunter.safe_io import read_artifact, strict_json
from superhunter.tools import verify_native_session, verify_review_115

SUPPLY = ROOT / 'superhunter/product_supply'
MATRIX = ROOT / 'superhunter/INTEGRATION_STATUS_200.md'
ARCHIVE_99_SHA = 'c4d9f671093a88aa25be658c583361da7c7abadee5ac582de4e5f723a8375c1b'
ACCEPTANCE_70_SHA = 'd826d1ead698a870ac978d732b943d7aed1d49a14adffaad30295867356ee6ae'
ROLE = {'executable': 'Ejecución', 'reference_data': 'Referencia', 'pending': '—'}


def pinned_file(name, expected_sha):
    raw = read_artifact(SUPPLY, name)
    if sha(raw) != expected_sha:
        raise EvidenceError('historical file differs from reviewed bytes: ' + name)
    return raw


def read_session(archive, verify, expected_sha):
    raw = verify_review_115.unpack(archive)
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


def render(components, native):
    left, component_rows, component_ops = components
    right, native_rows, native_ops = native
    counts = Counter()
    overlap = 0
    details = []
    for a, b in zip(component_rows, native_rows, strict=True):
        if any(a[key] != b[key] for key in ('id', 'repository', 'commit', 'tree')):
            raise EvidenceError('historical sessions disagree on identity, revision or tree')
        roles = (a['session'], b['session'])
        overlap += 'pending' not in roles
        role = next(r for r in ROLE if r in roles)
        counts[role] += 1
        name, commit = a['repository'], a['commit']
        details.append(f"| {a['id']} | [{name}](https://github.com/{name}/tree/{commit}) | `{commit}` | "
                       f"{receipt(a, component_ops)} | {receipt(b, native_ops)} |")
    union = counts['executable'] + counts['reference_data']
    repo = 'https://github.com/josuechavando350-png/nexus-quant-capital'
    lines = [
        '# SUPERHUNTER · Matriz de integración', '',
        f"**Aceptación conjunta pendiente.** Los dos archivos históricos contienen {union} identidades distintas. "
        f"De ellas, {counts['executable']} ejecutaron código y {counts['reference_data']} aportaron referencias. "
        f"Hay {counts['pending']} identidades sin participación en estos archivos.", '',
        '| Evidencia histórica | Respuestas | Identidades | Ejecución | Referencias |',
        '|---|---:|---:|---:|---:|',
    ]
    for label, result in (('[PR 118](product_supply/component-session-99.json)', left),
                          ('[PR 119](product_supply/native-session-70.json)', right)):
        lines.append(f"| {label} | {result['responses']} | {result['session']} | {result['executables']} | "
                     f"{result['reference_data']} |")
    lines.extend([
        '', f"Ambos archivos comparten {overlap} identidades. Hay {left['session'] - overlap} exclusivas "
        f"del primero y {right['session'] - overlap} del segundo. El conteo actual de integraciones conjuntas, "
        "ejecuciones, referencias y pendientes requiere una sesión completa del commit publicado y su reproducción.",
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
        '', '| ID | Repositorio | Revisión Git | PR 118 histórico | PR 119 histórico |', '|---:|---|---|---|---|',
        *details, '', 'Comprobación sin red desde la raíz del repositorio mediante '
        '`python3.12 -B -m superhunter.tools.render_product_matrix --check-historical`.', '',
    ])
    return '\n'.join(lines)


def historical_markdown():
    record = strict_json(pinned_file('native-acceptance-70.json', ACCEPTANCE_70_SHA))
    components = read_session(pinned_file('component-session-99.json', ARCHIVE_99_SHA),
                              verify_review_115.verify, verify_review_115.INTERIM_99)
    native = read_session(pinned_file('native-session-70.json', record['archive_sha256']),
                          verify_native_session.verify, record['independent_verification']['transcript_sha256'])
    return render(components, native)


def main():
    if {'--historical', '--check-historical'} & set(sys.argv[1:]):
        parser = argparse.ArgumentParser(description=__doc__)
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument('--historical', action='store_true', help='render the two frozen sessions')
        mode.add_argument('--check-historical', action='store_true', help='verify the tracked historical matrix')
        args = parser.parse_args()
        rendered = historical_markdown()
        if args.check_historical:
            if MATRIX.read_bytes() != rendered.encode('utf-8'):
                raise SystemExit('tracked matrix differs from verified historical evidence')
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
