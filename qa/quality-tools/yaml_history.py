"""Fixed public historical Python sources. Read as text, never import them."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.request

HERE = Path(__file__).resolve().parent


def load(path):
    return json.loads(path.read_text())


def save(path, obj):
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def name(case, side):
    return hashlib.sha256((case[side] + case["path"]).encode()).hexdigest()[:20] + ".py"


def prepare(directory):
    directory.mkdir(exist_ok=False, parents=True)
    cases = load(HERE / "yaml-cases.json")

    def fetch(pair):
        case, side = pair
        uri = f"https://raw.githubusercontent.com/{case['repo']}/{case[side]}/{case['path']}"
        with urllib.request.urlopen(uri, timeout=45) as response:
            raw = response.read(500_001)
        if len(raw) > 500_000:
            raise ValueError("fixture too large")
        if hashlib.sha256(raw).hexdigest() != case[side + "_sha256"]:
            raise ValueError("historical source differs from its frozen bytes")
        (directory / name(case, side)).write_bytes(raw)

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(fetch, [(c, s) for c in cases for s in ("before", "after")]))


def measure(directory, evidence):
    evidence.mkdir(parents=True, exist_ok=False)
    files = sorted(directory.glob("*.py"))
    if len(files) != 20:
        raise ValueError("expected twenty frozen inputs")
    run = subprocess.run([sys.executable, "-I", "-m", "bandit", "-q", "-t", "B506", "-f", "json",
                          *map(str, files)], capture_output=True, timeout=90)
    if run.returncode not in (0, 1):
        raise RuntimeError(run.stderr.decode())
    report = json.loads(run.stdout)
    if report["errors"] or set(report["metrics"]) != {"_totals", *map(str, files)}:
        raise ValueError("Bandit skipped or could not parse an input")
    predictions = {p.name: [] for p in files}
    for issue in report["results"]:
        if issue["test_id"] != "B506":
            raise ValueError("unexpected diagnostic")
        predictions[Path(issue["filename"]).name].append(issue["line_number"])
    save(evidence / "predictions.json", predictions)
    cases = load(HERE / "yaml-cases.json")
    rows = []
    for case in cases:
        before, after = (set(predictions[name(case, side)]) for side in ("before", "after"))
        expected = set(case["before_lines"])
        rows.append({"repo":case["repo"], "all_changed_lines_found":expected <= before,
                     "on_fixed_file":sorted(after), "other_before":sorted(before - expected)})
    score = {"rule":"B506", "cases":rows, "detected":sum(x["all_changed_lines_found"] for x in rows),
             "corrected_without_alert":sum(not x["on_fixed_file"] for x in rows)}
    save(evidence / "score.json", score)
    print(json.dumps(score))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("inputs", type=Path)
    p.add_argument("--evidence", type=Path)
    args = p.parse_args()
    if args.evidence:
        measure(args.inputs.resolve(), args.evidence)
    else:
        prepare(args.inputs)
