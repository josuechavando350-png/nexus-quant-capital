"""Copia una carpeta de resultados a la rama `census-dinero/resultados` y la empuja.

Solo se usa dentro de GitHub Actions. La rama de resultados no comparte historia
con el código: contiene únicamente salidas del census. Varios jobs pueden
empujar a la vez porque cada uno escribe en su propia ruta; si el push choca,
se reintenta sobre la punta nueva (con espera aleatoria: hasta 20 tramos
terminan casi juntos).
"""

import argparse
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time

BRANCH = "census-dinero/resultados"
ATTEMPTS = 20


def git(*args, cwd, check=True):
    return subprocess.run(["git", *args], cwd=cwd, check=check, text=True, capture_output=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dest", required=True, help="ruta dentro de la rama de resultados")
    ap.add_argument("--message", required=True)
    args = ap.parse_args()

    token = os.environ["GH_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    remote = f"https://x-access-token:{token}@github.com/{repo}.git"
    work = tempfile.mkdtemp()
    git("init", "-q", cwd=work)
    git("config", "user.name", "github-actions[bot]", cwd=work)
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com", cwd=work)
    git("remote", "add", "origin", remote, cwd=work)

    for attempt in range(ATTEMPTS):
        exists = git("ls-remote", "--exit-code", "--heads", "origin", BRANCH, cwd=work, check=False).returncode == 0
        if exists:
            git("fetch", "-q", "--depth=1", "origin", BRANCH, cwd=work)
            git("checkout", "-q", "-B", "res", "FETCH_HEAD", cwd=work)
        else:
            git("checkout", "-q", "--orphan", "res", cwd=work)
            with open(os.path.join(work, "README.md"), "w") as fh:
                fh.write("# Resultados del Census del dinero\n\nSalidas generadas por GitHub Actions. "
                         "Cada carpeta en `corridas/` es una ejecución.\n")
        target = os.path.join(work, args.dest)
        if os.path.isdir(target):
            shutil.rmtree(target)
        shutil.copytree(args.src, target)
        git("add", "-A", cwd=work)
        if git("diff", "--cached", "--quiet", cwd=work, check=False).returncode == 0:
            print("sin cambios que publicar")
            return 0
        git("commit", "-q", "-m", args.message, cwd=work)
        push = git("push", "-q", "origin", f"res:refs/heads/{BRANCH}", cwd=work, check=False)
        if push.returncode == 0:
            print(f"publicado en {BRANCH}:{args.dest}")
            return 0
        print(f"push rechazado (intento {attempt + 1}), reintentando: {push.stderr.strip()[:200]}", file=sys.stderr)
        git("reset", "-q", "--hard", cwd=work, check=False)
        time.sleep(2 + random.uniform(0, 4 + 2 * attempt))
    print(f"no se pudo publicar tras {ATTEMPTS} intentos", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
