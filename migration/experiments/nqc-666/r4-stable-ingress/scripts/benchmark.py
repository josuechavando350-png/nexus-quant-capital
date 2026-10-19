"""Paired stage-specific experiment; all attempts, including late drops, retained."""
import argparse
import array
from dataclasses import asdict
import gc
import hashlib
from importlib.metadata import version
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
R3 = ROOT.parent / "r3-state-evidence"
sys.path[:0] = [str(ROOT / "python"), str(R3 / "src"), str(R3 / "scripts")]
from fixtures import policy_from
from gateway import Gateway, MathWorker
from native_math import NativeMath
from stable_gateway import StableGateway
from state_evidence import Rejected


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def stats(v):
    s = sorted(v); n = len(s)
    return {"n": n, **{k: s[math.ceil(n * q) - 1] for k, q in
                       (("p50", .5), ("p95", .95), ("p99", .99), ("p99_9", .999))},
            "min": s[0], "max": s[-1]}


def packed(values):
    a = array.array("Q", values)
    if sys.byteorder != "little": a.byteswap()
    return a.tobytes()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--library", type=Path, required=True)
    p.add_argument("--eval", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args(); a.out.mkdir(parents=True, exist_ok=False)
    allowed = sorted(os.sched_getaffinity(0)); os.sched_setaffinity(0, {allowed[0]})
    native = NativeMath(a.library, sha(a.library))
    worker = MathWorker(a.eval.resolve())
    index = json.loads((R3 / "fixtures/synthetic-index.json").read_text())
    cases = [((R3 / "fixtures" / r["packet"]).read_bytes(), policy_from(r["policy"]), r["words"]) for r in index]
    now = max(policy.anchor.timestamp for _, policy, _ in cases)
    inputs = []
    expected_math = []
    expected_scenario = []
    for raw, policy, v in cases:
        for price_i in range(13):
            price = (1 + price_i) * 10**35
            args = [v["borrow"] % 2**128, v["borrow"] >> 128, v["position"] % 2**128,
                    v["position"] >> 128, price, v["lltv"]]
            inputs.append(args)
            expected_math.append(worker.health(args))
            g = Gateway(policy); t = g.ingest(raw, now)
            s = g.scenario(t, now, price, worker)
            expected_scenario.append((s, g.authorize(t, now)))
    files = sorted(f for d in ("src", "python", "scripts", "tests") for f in (ROOT / d).rglob("*")
                   if f.is_file() and "__pycache__" not in f.parts)
    files += [ROOT / n for n in ("Cargo.toml", "Cargo.lock", "PRE_REGISTER.md", "PROVENANCE.json")]
    dep = sorted(f for base in (ROOT.parent, ROOT.parent / "r1-morpho", R3)
                 for d in ("src", "scripts") for f in (base / d).rglob("*")
                 if f.is_file() and f.suffix in (".rs", ".py"))
    meta = {"scope": "SYNTHETIC_PREPARED_AND_BUFFERED_INGRESS_ONLY_NO_LIVE_ADMISSION",
            "cpu": subprocess.check_output(["lscpu"], text=True), "cpuinfo": Path("/proc/cpuinfo").read_text(),
            "platform": platform.platform(), "python": sys.version, "affinity": sorted(os.sched_getaffinity(0)),
            "allowed_affinity": allowed, "gc_enabled": gc.isenabled(),
            "frequency": "Uncontrolled KVM host, no IRQ/NUMA/governor/priority changes",
            "clock": "CLOCK_MONOTONIC_RAW, individual calls, no trimming or subtraction",
            "library_sha256": sha(a.library), "r1_eval_sha256": sha(a.eval),
            "dependencies": {n: version(n) for n in ("trie", "rlp", "eth-hash", "pycryptodome")},
            "source_sha256": {str(f.relative_to(ROOT)): sha(f) for f in files},
            "parent_source_sha256": {str(f.relative_to(ROOT.parent)): sha(f) for f in dep},
            "budgets_ns": {"ingress": 50_000_000, "scenario": 5_000_000},
            "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "runs": []}
    tasks = [(rep, "math", variant, 16384) for rep in range(3) for variant in ("ipc", "native")]
    tasks += [(rep, mode, variant, count) for rep in range(3)
              for mode, count in (("hot_scenario", 8192), ("full_ingress", 4096))
              for variant in ("r3_ipc", "r3_native", "r4_native")]
    random.Random(666404).shuffle(tasks)
    grouped = {}
    clock = lambda: time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)
    try:
        with zipfile.ZipFile(a.out / "raw.zip", "w", zipfile.ZIP_DEFLATED) as archive:
            for rep, mode, variant, count in tasks:
                label = f"{mode}-{variant}-rep{rep}"
                gateways, tickets = [], []
                if mode != "math":
                    for raw, policy, _ in cases:
                        g = StableGateway(policy, native) if variant == "r4_native" else Gateway(policy)
                        t = g.ingest(raw, now)
                        gateways.append(g); tickets.append(t)
                selected_math = worker if variant in ("ipc", "r3_ipc") else native
                def invoke(i):
                    if mode == "math": return selected_math.health(inputs[i % len(inputs)])
                    j = i % 16; raw, policy, _ = cases[j]; g = gateways[j]
                    if mode == "full_ingress":
                        g.reset(policy); tickets[j] = g.ingest(raw, now)
                    t = tickets[j]
                    price = (1 + i % 13) * 10**35
                    s = (g.scenario(t, now, price) if variant == "r4_native"
                         else g.scenario(t, now, price, selected_math))
                    return s, g.authorize(t, now)
                for i in range(64): invoke(i)
                samples, control, statuses, drops = [], [], bytearray(), []
                checksum = hashlib.sha256()
                for i in range(count):
                    c0 = clock(); c1 = clock(); control.append(c1 - c0)
                    start = clock()
                    try:
                        result = invoke(i)
                        reason = None
                    except Rejected as e:
                        result = None
                        reason = str(e)
                    end = clock()
                    samples.append(end - start)
                    if reason is None:
                        expected = (expected_math[i % len(inputs)] if mode == "math"
                                    else expected_scenario[(i % 16) * 13 + i % 13])
                        assert result == expected, (label, i, result, expected)
                        checksum.update(repr(result).encode()); statuses.append(0)
                    else:
                        assert variant == "r4_native" and any(s in reason for s in
                            ("deadline exceeded", "expired during", "monotonic snapshot expiry")), (label, i, reason)
                        statuses.append(1); drops.append({"index": i, "reason": reason, "elapsed_ns": end - start})
                        # Recovery is outside the failed attempt window, measured explicitly below.
                        recovery_start = clock()
                        j = i % 16; tickets[j] = gateways[j].ingest(cases[j][0], now)
                        drops[-1]["recovery_ns"] = clock() - recovery_start
                raw = packed(samples)
                archive.writestr(label + ".bin", raw)
                archive.writestr(label + "-clock.bin", packed(control))
                archive.writestr(label + "-status.bin", statuses)
                record = {"label": label, "rep": rep, "mode": mode, "variant": variant,
                          "stats_ns": stats(samples), "clock_ns": stats(control),
                          "sample_sha256": hashlib.sha256(raw).hexdigest(),
                          "status_sha256": hashlib.sha256(statuses).hexdigest(),
                          "accepted_output_sha256": checksum.hexdigest(), "rejected": len(drops), "drops": drops}
                meta["runs"].append(record)
                grouped.setdefault(mode + "|" + variant, []).extend(samples)
                print(json.dumps(record), flush=True)
    finally:
        worker.close()
    meta["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (a.out / "benchmark.json").write_text(json.dumps(meta, indent=2) + "\n")
    (a.out / "summary.json").write_text(json.dumps({k: stats(v) for k, v in grouped.items()}, indent=2) + "\n")


if __name__ == "__main__": main()
