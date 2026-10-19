"""Build a deterministic zipapp from unchanged prior verifier source and inputs."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent
EXPERIMENTS = ROOT.parent
FILES = [
    'nqc-037-historical-state/src/verify.py',
    'nqc-037-historical-state/src/intake.py',
    'nqc-037-historical-state/vendor/nqc031/storage_proof.py',
    'nqc-037-historical-state/vendor/nqc031/util.py',
    'nqc-037-historical-state/inputs/TARGET.json',
    'nqc-037-historical-state/inputs/parent-header.json',
    'nqc-037-historical-state/inputs/target-header.json',
    'nqc-037-historical-state/inputs/l1-observations.json',
    'nqc-038-archive-access/triport_intake.py',
    'nqc-039-authenticated-intake/local_export.py',
]
BOOTSTRAP = '''import hashlib, json, pathlib, sys, tempfile, zipfile
with tempfile.TemporaryDirectory(prefix="nqc039-") as directory:
    base = pathlib.Path(directory)
    with zipfile.ZipFile(sys.argv[0]) as package:
        manifest = json.loads(package.read("PACKAGE_MANIFEST.json"))
        for row in manifest:
            name = pathlib.PurePosixPath(row["path"])
            if name.is_absolute() or ".." in name.parts:
                raise SystemExit("Invalid package path")
            data = package.read(row["path"])
            if hashlib.sha256(data).hexdigest() != row["sha256"]:
                raise SystemExit("Package integrity mismatch")
            path = base.joinpath(*name.parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    sys.path.insert(0, str(base / "nqc-039-authenticated-intake"))
    from local_export import run
    raise SystemExit(run(base))
'''


def build():
    manifest = []
    entries = {}
    for name in FILES:
        data = (EXPERIMENTS / name).read_bytes()
        entries[name] = data
        manifest.append({'path': name, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)})
    entries['PACKAGE_MANIFEST.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    entries['__main__.py'] = BOOTSTRAP.encode()
    out = ROOT / 'NQC039_EXPORTADOR.pyz'
    with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED) as package:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 19, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            package.writestr(info, data)
    (ROOT / 'PACKAGE_MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'artifact': out.name, 'bytes': out.stat().st_size,
                      'sha256': hashlib.sha256(out.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    build()
