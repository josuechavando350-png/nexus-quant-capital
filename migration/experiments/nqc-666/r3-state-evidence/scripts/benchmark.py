"""Paired offline ingress benchmark. Includes parsing and all verification checks.

The input byte buffers, policy pins and installed Rust worker already exist.
No external communication, archive access, consensus or EVM simulation is timed.
"""
import argparse
import array
import gc
import hashlib
from importlib.metadata import distribution, version
import json
import math
import os
from pathlib import Path
import platform
import random
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from fixtures import policy_from
from gateway import Gateway, MathWorker
from state_evidence import verify


def stats(v):
    s = sorted(v)
    n = len(s)
    return {"n": n, **{k: s[math.ceil(n * q) - 1] for k, q in
                       (("p50", .5), ("p95", .95), ("p99", .99), ("p99_9", .999))},
            "max": s[-1], "min": s[0]}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dependencies():
    result = {}
    for name in ("trie", "rlp", "eth-hash", "pycryptodome", "py-evm"):
        dist = distribution(name)
        files = {str(f): sha(Path(dist.locate_file(f))) for f in dist.files
                 if str(f).endswith((".py", ".so")) and Path(dist.locate_file(f)).is_file()}
        result[name] = {"version": version(name), "files_sha256": files}
    return result


def observable(facts, prediction=None, gate=None):
    # Observable complete financial-relevant state, consumed outside the timer.
    # Objects and prediction creation are inside; diagnostic serialization is not.
    fields = (facts.anchor, facts.address, facts.market_id, facts.borrower,
              facts.code_hash, facts.storage_root, facts.words, facts.canonicality,
              facts.layout_assurance, facts.oracle_price, facts.observed_eligibility,
              facts.commercial_admission, prediction, gate)
    return repr(fields).encode()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--eval", type=Path, required=True)
    parser.add_argument("--count", type=int, default=4096)
    parser.add_argument("--reps", type=int, default=3)
    a = parser.parse_args()
    assert a.count >= 16 and a.count % 16 == 0 and a.reps > 0
    a.out.mkdir(parents=True, exist_ok=False)
    original_affinity = sorted(os.sched_getaffinity(0))
    os.sched_setaffinity(0, {min(original_affinity)})
    index = json.loads((ROOT / "fixtures/synthetic-index.json").read_text())
    cases = [((ROOT / "fixtures" / r["packet"]).read_bytes(), policy_from(r["policy"])) for r in index]
    now = max(p.anchor.timestamp for _, p in cases)
    clock = lambda: time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)
    source_paths = sorted(p for name in ("src", "scripts", "tests", "reference", "fixtures")
                          for p in (ROOT / name).rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    parent_paths = sorted(p for name in ("src", "r1-morpho/src", "r2-event-pressure/src")
                          for p in (ROOT.parent / name).rglob("*.rs"))
    metadata = {"scope": "SYNTHETIC_BUFFERED_POST_BLOCK_PROOF_INGRESS_NO_CANONICALITY_OR_ORACLE",
                "clock": "CLOCK_MONOTONIC_RAW; no subtraction, trimming or batch division",
                "count_per_run": a.count, "repetitions": a.reps,
                "python": sys.version, "platform": platform.platform(),
                "cpu": subprocess.check_output(["lscpu"], text=True),
                "cpuinfo": Path("/proc/cpuinfo").read_text(),
                "affinity": sorted(os.sched_getaffinity(0)), "original_affinity": original_affinity,
                "frequency": "Uncontrolled virtual host; no CPU isolation, IRQ, turbo, NUMA or governor changes",
                "gc_enabled": gc.isenabled(), "gc_thresholds": gc.get_threshold(),
                "dependencies": dependencies(), "rust_eval_sha256": sha(a.eval),
                "source_sha256": {str(p.relative_to(ROOT)): sha(p) for p in source_paths},
                "parent_source_sha256": {str(p.relative_to(ROOT.parent)): sha(p) for p in parent_paths},
                "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "runs": []}
    tasks = [(rep, mode, shared) for rep in range(a.reps) for mode in ("verify", "ingress_scenario")
             for shared in (False, True)]
    random.Random(666304).shuffle(tasks)
    grouped = {}
    worker = MathWorker(a.eval.resolve())
    try:
        with zipfile.ZipFile(a.out / "raw.zip", "w", zipfile.ZIP_DEFLATED) as archive:
            for rep, mode, shared in tasks:
                label = f"{mode}-shared{int(shared)}-rep{rep}"
                gateway = Gateway(cases[0][1])
                def invoke(i):
                    raw, policy = cases[i % len(cases)]
                    if mode == "verify":
                        return verify(raw, policy, now, shared=shared), None, None
                    # Include anchor reset, invalidation, verification, ticket, IPC,
                    # conditional math and explicit authorization denial.
                    gateway.reset(policy)
                    ticket = gateway.ingest(raw, now, shared=shared)
                    f = gateway.facts(ticket, now)
                    prediction = gateway.scenario(ticket, now, (1 + i % 13) * 10**35, worker)
                    gate = gateway.authorize(ticket, now)
                    return f, prediction, gate
                for i in range(64): invoke(i)
                samples = []
                controls = []
                checksum = hashlib.sha256()
                for i in range(a.count):
                    c0 = clock(); c1 = clock(); controls.append(c1 - c0)
                    start = clock()
                    output = invoke(i)
                    stop = clock()
                    samples.append(stop - start)
                    checksum.update(observable(*output))
                def packed(values):
                    ar = array.array("Q", values)
                    if sys.byteorder != "little": ar.byteswap()
                    return ar.tobytes()
                raw = packed(samples)
                archive.writestr(label + ".bin", raw)
                archive.writestr(label + "-clock.bin", packed(controls))
                result = {"label": label, "mode": mode, "shared": shared, "rep": rep,
                          "stats_ns": stats(samples), "clock_control_ns": stats(controls),
                          "sample_sha256": hashlib.sha256(raw).hexdigest(),
                          "observable_sha256": checksum.hexdigest()}
                metadata["runs"].append(result)
                grouped.setdefault(f"{mode}|shared{int(shared)}", []).extend(samples)
                print(json.dumps(result), flush=True)
    finally:
        worker.close()
    for mode in ("verify", "ingress_scenario"):
        assert len({r["observable_sha256"] for r in metadata["runs"] if r["mode"] == mode}) == 1
    metadata["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (a.out / "benchmark.json").write_text(json.dumps(metadata, indent=2) + "\n")
    (a.out / "summary.json").write_text(json.dumps({k: stats(v) for k, v in grouped.items()}, indent=2) + "\n")


if __name__ == "__main__":
    main()
