"""Render a product session or independently verify the two frozen historical sessions."""
import argparse
from collections import Counter
import os
from pathlib import PurePosixPath
import re
import subprocess
import sys

from superhunter.acceptance_paths import PROFILE_DIRECTORIES
from superhunter.product_matrix import markdown
from superhunter.product_native_capabilities import CORE_EIGHT

from superhunter.product_reasoning import EvidenceError
from superhunter.product_review import ROOT, sha
from superhunter.safe_io import canonical, read_artifact, strict_json
from superhunter.tools import verify_native_session, verify_review_115

MATRIX = ROOT / 'superhunter/INTEGRATION_STATUS_200.md'
DOSSIER = 'superhunter/' + PROFILE_DIRECTORIES['core-eight']
ACCOUNTING_DOSSIER = 'superhunter/' + PROFILE_DIRECTORIES['accounting']
HEADER_DOSSIER = 'superhunter/' + PROFILE_DIRECTORIES['canonical-header']
GRPC_SCHEMA_DOSSIER = 'superhunter/' + PROFILE_DIRECTORIES['grpc-schema']
HTML_REVIEW_DOSSIER = 'superhunter/' + PROFILE_DIRECTORIES['html-review']
REPORT_INTEROP_DOSSIER = 'superhunter/' + PROFILE_DIRECTORIES['report-interop']
# A later default native registry must never redefine an archived nine-group acceptance.
ACCOUNTING_SHA = '4dfec613c3f4ad64084a7487d4f4d5ecadea8f177f1bcc7283637c4a8adcdefa'
HEADER_SHA = 'c3b7c10d1c72aacae73e09c5b96b521baeb9a8e6f4b15b03886ddcb8a16395c3'
GRPC_SCHEMA_SHA = 'ae4a0e3a7026cd08083e144e92abb19f334ef816bfefeb4f4d79a48abf4dc003'
HTML_REVIEW_SHA = '1b0c5ecf4ec91e9f0a0ec45a0984c60ad615e37f9d0512474ed30dd2e3e19add'
PROFILES = {'core-eight': (DOSSIER, CORE_EIGHT[1], 'require_core_eight'),
            'accounting': (ACCOUNTING_DOSSIER, ACCOUNTING_SHA, 'require_accounting'),
            'canonical-header': (HEADER_DOSSIER, HEADER_SHA, 'require_canonical_header'),
            'grpc-schema': (GRPC_SCHEMA_DOSSIER, GRPC_SCHEMA_SHA, 'require_grpc_schema'),
            'html-review': (HTML_REVIEW_DOSSIER, HTML_REVIEW_SHA, 'require_html_review'),
            'report-interop': (REPORT_INTEROP_DOSSIER, HTML_REVIEW_SHA, 'require_report_interop')}
REQUIRED_MUTATIONS = frozenset({
    'inflated_count', 'unsupported_credit', 'replaced_historical_digest', 'changed_native_result',
    'changed_license', 'changed_git_tree', 'erased_domain_selection', 'erased_shared_results',
    'erased_corroboration', 'changed_role_totals', 'changed_source_distribution', 'changed_commercial_total',
    'erased_excerpt_inventory', 'changed_group_result', 'changed_operation_total', 'changed_coverage_total',
    'discarded_secondary_operation', 'forged_secondary_digest', 'invented_discovery', 'changed_native_report',
})
PORTABLE_ARGV = (
    'unshare', '--user', '--map-current-user', '--net', 'python3.12', '-B', '-m',
    'superhunter.tools.catalog_session', '--review-queries', '--native-inputs', '<native-inputs>',
    '--native-kits', '<native-kits>', '--source-inventory', '--source-references', '<source-references>',
    '--embedded-root-manifests', '--owned-source-kit', '<owned-source-kit>', '--score-kit', '<score-kit>',
    '--fork-headers', '--geth-header', '<geth-header>', '--gosec-kit', '<gosec-kit>',
    '--component-controls', 'all', '<prepared-bundles>',
)
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
        op_roles = Counter(op['role'] for row in current_rows for op in row['session_operations'])
        mixed = sum(len({op['role'] for op in row['session_operations']}) == 2 for row in current_rows)
        lines.extend(['', f"**{result['session']}/{result['catalog']} identidades** participaron en ambas ejecuciones "
                      f"del producto. Hubo {result['executables']} de ejecución, {result['reference_data']} de referencia, "
                      f"{result['operations']} operaciones y {result['catalog'] - result['session']} identidades pendientes.",
                      '', f"Al contar todos los recibos, hubo {op_roles['executable']} operaciones de ejecución "
                      f"y {op_roles['reference_data']} de referencia. Las {mixed} identidades con ambos roles "
                      "figuran una sola vez en el total de ejecución.",
                      '', f"Los expedientes registran dos checkouts limpios en el mismo host, código de salida cero "
                      f"y {result['responses']} respuestas iguales por ejecución. El productor fue el "
                      f"[commit {producer['commit']}]({repo}/commit/{producer['commit']}) con árbol "
                      f"`{producer['tree']}` y la transcripción tiene SHA-256 `{result['transcript_sha256']}`. "
                      f"[Acta y huellas de los dos expedientes]({producer['dossier'].removeprefix('superhunter/')}/acceptance.json)",
                      '', "Archivos preparados con huellas distintas entre los expedientes: "
                      + (', '.join(f'`{path}`' for path in producer['different_inputs']) or 'ninguno') + '. '
                      + ('Los manifiestos nativos tienen huellas distintas.' if producer['different_native_manifest']
                         else 'Coincide la huella de los manifiestos nativos.')])
        if producer['profile'] in ('accounting', 'canonical-header', 'grpc-schema', 'html-review', 'report-interop'):
            lines.extend(['', 'Esta aceptación incluye el noveno grupo de controles contables. '
                          'El [expediente de ocho grupos](product_supply/consolidated-acceptance/acceptance.json) '
                          'se comprueba con `--verify-dossier --profile core-eight`.'])
        if producer['profile'] in ('canonical-header', 'grpc-schema', 'html-review', 'report-interop'):
            lines.extend(['', 'El décimo grupo comprueba la interoperabilidad de encabezados RLP. '
                          'El [expediente de nueve grupos](product_supply/consolidated-acceptance-accounting/acceptance.json) '
                          'se comprueba con `--verify-dossier --profile accounting`.'])
        if producer['profile'] in ('grpc-schema', 'html-review', 'report-interop'):
            lines.extend(['', 'El undécimo grupo comprueba esquemas gRPC. '
                          'El [expediente de diez grupos](product_supply/consolidated-acceptance-header/acceptance.json) '
                          'se comprueba con `--verify-dossier --profile canonical-header`.'])
        if producer['profile'] in ('html-review', 'report-interop'):
            lines.extend(['', 'El duodécimo grupo comprueba el informe HTML en el navegador. '
                          'El [expediente de once grupos](product_supply/consolidated-acceptance-grpc-schema/acceptance.json) '
                          'se comprueba con `--verify-dossier --profile grpc-schema`.'])
            lines.extend(['', 'En el corte publicado `52ea24ad`, las 451 pruebas focalizadas pasaron sin '
                          'fallos ni omisiones. El cotejo independiente confirmó los cinco expedientes y los '
                          '642 archivos históricos. El control global encontró 666 archivos y su máximo es 500. '
                          '[Pruebas y controles por árbol](product_supply/acceptance-120/qa-twelve-final.json) · '
                          '[Licencias y bloqueos de dependencias](SOURCE_MATERIALIZATION.md)'])
        if producer['profile'] == 'report-interop':
            lines.extend(['', f"Se preservaron las {result['prior_operations_preserved']} operaciones de las "
                          f"{result['prior_identities_preserved']} identidades del "
                          '[expediente anterior](product_supply/consolidated-acceptance-html-review/acceptance.json). '
                          'El perfil incluye comprobaciones de interoperabilidad de informes existentes.'])
            lines.extend(['', 'En el productor `f1eea76f` pasaron las 512 pruebas de los 49 módulos '
                          'ejecutados, sin omisiones. Se cotejaron contenido y modo de los 642 archivos históricos. '
                          'La migración ampliada pasó 8/9. El inventario global seleccionó 684 archivos '
                          'frente al límite de 500. [Resultados y controles de QA](product_supply/acceptance-120/qa-report-interop.json).'])
    if current:
        lines.extend(['', 'Una revisión posterior del PR 119 archivó 139 identidades en un perfil distinto. '
                      'Su transcripción, los dos registros de ejecución declarados y el cruce con el perfil contable '
                      'se documentan en el [contraste de evidencias](product_supply/acceptance-120/pr119-139-comparison.json).'])
    pending = '' if current else (' El conteo actual de integraciones conjuntas, ejecuciones, referencias y '
                                  'pendientes requiere una sesión completa del commit publicado y su reproducción.')
    lines.extend([
        '', f"Ambos archivos comparten {overlap} identidades. Hay {left['session'] - overlap} exclusivas "
        f"del primero y {right['session'] - overlap} del segundo.{pending}",
        '', f"El inventario del PR 119 verificó {right['sources']['complete']} fuentes directas. Las dos "
        f"transcripciones identifican {len(details)} revisiones. Se conservaron los 153 pines previos. "
        "Ese inventario inicial dejó fuera 141 gitlinks y un payload LFS. "
        "Adquisiciones y estado posterior en [SOURCE_MATERIALIZATION.md](SOURCE_MATERIALIZATION.md). "
        "Las licencias transitivas y la "
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
    native = read_session(*native, lambda raw, expected: verify_native_session.verify(
        raw, expected, contract_version=70))
    return render(components, native, **kwargs)


def digest(value, width=64):
    return isinstance(value, str) and re.fullmatch(f'[0-9a-f]{{{width}}}', value) is not None


def require_producer(commit, tree, inputs, profile):
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
        components_sha = sha(git('show', commit + ':superhunter/product_supply/component-control-contracts.json'))
    except subprocess.CalledProcessError as exc:
        raise EvidenceError('producer Git objects unavailable; fetch the published producer commit into this checkout') from exc
    expected_components = verify_review_115.COMPONENTS_THROUGH_HTML
    if profile == 'report-interop':
        expected_components = verify_review_115.HISTORICAL_COMPONENTS['report-interop']
    if contract_sha != PROFILES[profile][1] or components_sha != expected_components:
        raise EvidenceError('producer contract does not match selected acceptance profile')
    if profile == 'report-interop' and inputs.get('component_contract_sha256') != components_sha:
        raise EvidenceError('run component contract disagrees with the producer commit')
    if inputs['git_source_tree'] != source_tree or inputs['native_contract_sha256'] != contract_sha:
        raise EvidenceError('run source tree or native contract disagrees with the producer commit')


def run_evidence(record, run_id, profile='core-eight'):
    if record.get('id') != run_id:
        raise EvidenceError('two distinct ordered execution dossiers are required')
    checkout = record.get('checkout')
    if not isinstance(checkout, str) or not checkout or PurePosixPath(checkout).is_absolute() or any(
            part in ('', '.', '..') for part in checkout.split('/')):
        raise EvidenceError('expected a relative checkout identifier')
    def artifact(filename, key):
        data = read_artifact(ROOT, f'{PROFILES[profile][0]}/{run_id}/{filename}')
        if sha(data) != record.get(key):
            raise EvidenceError(f'{run_id} dossier digest differs for {filename}')
        return data
    inputs = strict_json(artifact('run-inputs.json', 'inputs_sha256'))
    if inputs.get('argv') != list(PORTABLE_ARGV):
        raise EvidenceError('execution dossier differs from the reviewed portable argv')
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
    require_producer(result['commit'], result['tree'], inputs, profile)
    return inputs, result, raw


def selected_profile(profile):
    if profile == 'latest':
        # A partial directory or a dangling symlink must fail its evidence checks.
        for name in reversed(PROFILES):
            if os.path.lexists(ROOT / PROFILES[name][0]):
                return name
        return 'core-eight'
    if profile not in PROFILES:
        raise EvidenceError('unknown acceptance profile')
    return profile


def check_act_verdict(act, verified, raw, *, verification_options=None):
    if canonical(act.get('independent_verification')) != canonical(verified):
        raise EvidenceError('independent verification in the acceptance act differs from the recomputed verdict')
    controls = verify_review_115.negative_controls(raw, **(verification_options or {}))
    if set(controls) != REQUIRED_MUTATIONS or canonical(act.get('refuted_mutations')) != canonical(controls):
        raise EvidenceError('refuted mutations in the acceptance act differ from the recomputed controls')


def accepted_markdown(profile='latest'):
    profile = selected_profile(profile)
    dossier = PROFILES[profile][0]
    act = strict_json(read_artifact(ROOT, dossier + '/acceptance.json'))
    if (type(act.get('schema_version')) is not int or act['schema_version'] != 1 or act.get('same_host') is not True
            or not isinstance(act.get('runs'), list) or len(act['runs']) != 2
            or not all(isinstance(record, dict) for record in act['runs'])):
        raise EvidenceError('expected exactly two same-host execution records')
    first, second = act['runs']
    if first.get('checkout') == second.get('checkout'):
        raise EvidenceError('two distinct checkouts are required')
    left, result, raw = run_evidence(first, 'first', profile)
    right, replay, other = run_evidence(second, 'second', profile)
    if left['raw_run_inputs_sha256'] == right['raw_run_inputs_sha256'] and first['result_sha256'] == second['result_sha256']:
        raise EvidenceError('the same input and result record was used for both runs')
    if (result['commit'], result['tree']) != (replay['commit'], replay['tree']):
        raise EvidenceError('execution records identify different producer commits or trees')
    strict_profile = {PROFILES[profile][2]: True}
    verified = verify_review_115.verify(raw, result['sha256'], **strict_profile)
    verify_review_115.verify(other, replay['sha256'], **strict_profile)
    if profile == 'report-interop' and result['commit'] != verify_review_115.REPORT_INTEROP_PRODUCER:
        raise EvidenceError('report interoperability dossier names a different audited producer')
    if raw != other:
        raise EvidenceError('the full transcripts differ between the two checkout runs')
    check_act_verdict(act, verified, raw, verification_options=strict_profile)
    keys = verify_review_115.response_keys(raw)
    rows = strict_json(raw.splitlines()[keys.index('integration-matrix')])['rows']
    producer = {**result, 'profile': profile, 'dossier': dossier,
                'different_inputs': sorted(key for key, value in left['prepared_files'].items()
                                                    if right['prepared_files'][key] != value),
                'different_native_manifest': left['native_manifest_sha256'] != right['native_manifest_sha256']}
    return historical_markdown(current=(verified, rows), producer=producer)


def main():
    if {'--historical', '--check-historical', '--acceptance', '--check-acceptance', '--verify-dossier', '--profile'} & set(sys.argv[1:]):
        parser = argparse.ArgumentParser(description=__doc__)
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument('--historical', action='store_true', help='render the two frozen sessions')
        mode.add_argument('--check-historical', action='store_true', help='verify the tracked historical matrix')
        mode.add_argument('--acceptance', action='store_true', help='render the two verified checkout runs')
        mode.add_argument('--check-acceptance', action='store_true', help='check the matrix against both runs')
        mode.add_argument('--verify-dossier', action='store_true', help='verify both runs independently of the current matrix')
        parser.add_argument('--profile', choices=('latest', *PROFILES), help='dossier to verify (default: latest)')
        args = parser.parse_args()
        if args.profile and (args.historical or args.check_historical):
            parser.error('--profile selects a two-checkout acceptance dossier')
        if args.acceptance or args.check_acceptance or args.verify_dossier:
            try:
                rendered = accepted_markdown(args.profile or 'latest')
            except (EvidenceError, ValueError, OSError, KeyError, TypeError) as error:
                print(f'acceptance unavailable: {error}', file=sys.stderr)
                return 2
        else:
            rendered = historical_markdown()
        if args.verify_dossier:
            return 0
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
