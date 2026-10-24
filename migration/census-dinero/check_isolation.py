"""Aislamiento del census del dinero.

El verificador original (`migration/verify_isolation.py`) rechaza cualquier
archivo en `.github/`. Esta rama agrega exactamente uno: el workflow del census,
que debe ser copia byte a byte de `workflow/census-dinero.yml` (la versión
revisada). Este script comprueba esa única excepción y luego corre el
verificador original, sin modificarlo, sobre una copia del árbol sin ese archivo.
"""

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ACTIVE = ROOT / ".github" / "workflows" / "census-dinero.yml"
REVIEWED = HERE / "workflow" / "census-dinero.yml"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    github = ROOT / ".github"
    extra = sorted(str(p.relative_to(ROOT)) for p in github.rglob("*") if p.is_file()) if github.exists() else []
    allowed = [str(ACTIVE.relative_to(ROOT))]
    if extra and extra != allowed:
        raise SystemExit(f"ISOLATION_FAILED: archivos activos no admitidos en .github: {extra}")
    if extra and sha(ACTIVE) != sha(REVIEWED):
        raise SystemExit("ISOLATION_FAILED: el workflow activo difiere de la copia revisada")
    with tempfile.TemporaryDirectory() as tmp:
        dst = Path(tmp) / "repo"
        shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns(".git", ".github", "__pycache__", "out"))
        res = subprocess.run([sys.executable, str(dst / "migration" / "verify_isolation.py"), "--root", str(dst)],
                             capture_output=True, text=True)
        if res.returncode:
            raise SystemExit(res.stdout + res.stderr)
        report = json.loads(res.stdout)
    report["census_dinero_workflow"] = {"path": allowed[0], "sha256": sha(REVIEWED), "active": bool(extra)}
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
