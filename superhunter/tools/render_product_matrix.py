"""Render the matrix from one freshly executed product session."""
import subprocess
import sys

from superhunter.product_matrix import markdown
from superhunter.safe_io import strict_json


def main():
    cmd = [sys.executable, '-B', '-m', 'superhunter.tools.catalog_session', *sys.argv[1:], 'integration-matrix']
    proc = subprocess.run(cmd, capture_output=True, timeout=600)
    if proc.returncode:
        sys.stderr.buffer.write(proc.stdout + proc.stderr)
        return proc.returncode
    sys.stdout.write(markdown(strict_json(proc.stdout)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
