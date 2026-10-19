"""Exact native ABI parity with saved R1 corpus and unchanged R1 process evaluator."""
import argparse
import concurrent.futures
import gzip
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from native_math import NativeMath, Rejected


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--library", type=Path, required=True)
    p.add_argument("--eval", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    native = NativeMath(a.library, hashlib.sha256(a.library.read_bytes()).hexdigest())
    evidence = ROOT.parent / "r1-morpho/evidence/differential"
    old = gzip.decompress((evidence / "corpus.txt.gz").read_bytes()).decode().splitlines()
    expected_old = gzip.decompress((evidence / "outputs.txt.gz").read_bytes()).decode().splitlines()
    corpus = [(line, result) for line, result in zip(old, expected_old) if line.startswith("H ")]
    r = random.Random(666401)
    extra = []
    for i in range(8192):
        v = [r.getrandbits(128) for _ in range(6)]
        v[4] = r.getrandbits([128, 192, 256][i % 3])
        if i % 4 == 0:
            v = [r.randrange(10**25), r.randrange(10**31), r.randrange(10**30),
                 r.randrange(10**25), r.randrange(10**38), r.randrange(10**18)]
        extra.append("H " + " ".join(f"{x:064x}" for x in v))
    extra_expected = subprocess.check_output([str(a.eval)], input=("\n".join(extra) + "\n").encode()).decode().splitlines()
    corpus += list(zip(extra, extra_expected))
    def evaluate(line):
        args = [int(x, 16) for x in line.split()[1:]]
        try:
            debt, cap, eligible = native.health(args)
            return "OK " + " ".join(f"{x:064x}" for x in (debt, cap, int(eligible)))
        except Rejected as e:
            code = str(e).removeprefix("native math rejected: ")
            assert code in ("17", "18"), str(e)
            return "ERR " + code
    outcomes = [evaluate(line) for line, _ in corpus]
    for i, ((line, expected), actual) in enumerate(zip(corpus, outcomes)):
        assert actual == expected, (i, line, expected, actual)
    # Fresh by-value requests must remain independent when the C ABI releases the GIL.
    concurrent_rows = corpus[:1024] * 4
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        actual = list(pool.map(evaluate, [line for line, _ in concurrent_rows]))
    assert actual == [expected for _, expected in concurrent_rows]
    raw = ("\n".join(line for line, _ in corpus) + "\n").encode()
    results = ("\n".join(outcomes) + "\n").encode()
    (a.out / "inputs.txt.gz").write_bytes(gzip.compress(raw, mtime=0))
    (a.out / "outputs.txt.gz").write_bytes(gzip.compress(results, mtime=0))
    result = {"cases": len(corpus), "saved_r1_cases": len(corpus) - len(extra),
              "new_r1_parity_cases": len(extra), "concurrent_calls": len(concurrent_rows),
              "all_equal": True, "inputs_sha256": hashlib.sha256(raw).hexdigest(),
              "outputs_sha256": hashlib.sha256(results).hexdigest(),
              "library_sha256": hashlib.sha256(a.library.read_bytes()).hexdigest()}
    (a.out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__": main()
