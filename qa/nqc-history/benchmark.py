"""Export the six first-party trees, collect predictions and check repeatability."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent
PRODUCT = "05002c36c12a1b572b5d425b7b0714189c448109"


def git(product, *args):
    return subprocess.check_output(["git", "-C", str(product), *args])


def export(product, revision, checkout):
    with tempfile.TemporaryFile() as archive:
        subprocess.run(["git", "-C", str(product), "archive", revision], stdout=archive, check=True)
        archive.seek(0)
        with tarfile.open(fileobj=archive) as tree:
            tree.extractall(checkout, filter="data")


def measure(product, checkout):
    raw = subprocess.check_output(
        [sys.executable, "-I", "-B", str(HERE / "review.py"), str(product)],
        cwd=checkout, timeout=240
    )
    return json.loads(raw)


def save(path, value):
    with path.open("x", encoding="utf-8") as out:
        json.dump(value, out, indent=2, sort_keys=True, ensure_ascii=False)
        out.write("\n")


def run(product, evidence):
    if git(product, "rev-parse", "HEAD").decode().strip() != PRODUCT:
        raise ValueError("unexpected product revision")
    if git(product, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("a clean product checkout is required")
    cases = json.loads((HERE / "cases.json").read_text())
    keys = {}
    for case in cases:
        if git(product, "rev-parse", case["after"] + "^").decode().strip() != case["before"]:
            raise ValueError("fixture is not the immediate parent")
        for side in ("before", "after"):
            rev = case[side]
            keys[hashlib.sha256(rev.encode()).hexdigest()[:12]] = rev
    if len(keys) != 2 * len(cases):
        raise ValueError("non-unique fixtures")
    evidence.mkdir(parents=True, exist_ok=False)
    save(evidence / "keys.json", keys)
    orders = [sorted(keys), sorted(keys, reverse=True)]
    passes = []
    for number, order in enumerate(orders, 1):
        predictions = {}
        for name in order:
            with tempfile.TemporaryDirectory() as temp:
                checkout = Path(temp)
                export(product, keys[name], checkout)
                predictions[name] = measure(product, checkout)
        save(evidence / f"predictions-{number}.json", predictions)
        passes.append(predictions)
    if passes[0] != passes[1]:
        raise ValueError("predictions changed in the reverse replay")
    print("Six snapshots reviewed twice with identical diagnostics.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("product", type=Path)
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    run(args.product.resolve(), args.evidence.resolve())
