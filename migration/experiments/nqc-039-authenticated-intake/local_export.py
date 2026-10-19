"""Run the authorized eight-read acquisition locally; export public evidence only."""
import argparse
from datetime import datetime, timezone
import getpass
import json
from pathlib import Path
import sys
import zipfile


def public_response_fetch(transport, secret, validation_error):
    def fetch(operation):
        response = transport(operation)
        if secret in json.dumps(response, ensure_ascii=False):
            raise validation_error('Response echoed a credential; not persisted')
        return response
    return fetch


def run(base):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', action='store_true', help='Show fixed requests offline; no key needed')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(base / 'nqc-038-archive-access'))
    try:
        import triport_intake as t
    except ImportError:
        print('Faltan dependencias. En tu entorno Python ejecuta:')
        print('python -m pip install rlp==5.0.0 pycryptodome==4.0.1')
        return 2
    if args.plan:
        print(json.dumps(t.specification(), indent=2))
        return 0
    if not sys.stdin.isatty():
        print('Ejecuta este archivo en una terminal interactiva para introducir la clave de forma oculta.')
        return 2
    out = args.out or Path('nqc039-evidencia-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    archive = out.with_name(out.name + '.zip')
    if out.exists() or archive.exists():
        print('La carpeta o ZIP ya existe. Elige una ruta nueva con --out.')
        return 2
    print('Hasta ocho lecturas a Triport. Cada respuesta se verifica antes de continuar.')
    key = getpass.getpass('Clave API de Triport (entrada oculta): ').strip()
    try:
        transport = t.TriportTransport(key)
        fetch = public_response_fetch(transport, key, t.v.ValidationError)
        report = t.intake.execute(fetch, out)
        t.intake.save(out / 'TRANSPORT.json', t.specification())
        t.intake.save(out / 'WIRE_REQUESTS.json', t.wire_plan())
        files = sorted(out.glob('*.json'))
        # The folder is new and contains only collector-generated JSON. Check
        # again before packaging, including error and metadata files.
        if any(key.encode() in p.read_bytes() for p in files):
            raise t.v.ValidationError('Credential detected in export; ZIP refused')
        with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as z:
            for p in files:
                z.write(p, p.name)
        print('Estado:', report['status'])
        print('Archivo de evidencia:', archive)
        print('Comparte ese ZIP para revisar el resultado. Admisión comercial: false.')
        return 0 if report['status'] != 'BLOCKED_OR_REJECTED' else 2
    except Exception as exc:
        # Do not display arbitrary exception text, tracebacks or credentials.
        print('Adquisición detenida:', type(exc).__name__)
        return 2
    finally:
        key = None


if __name__ == '__main__':
    raise SystemExit(run(Path(__file__).resolve().parent.parent))
