"""Pre-registered follow-up for the observed wire p99.9 increase. Every individual window, including drops, retained."""
import argparse
import array
import gc
import hashlib
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import platform
import random
import resource
import subprocess
import sys
import time
import zipfile

from corpus import ROOT, R3, R4, R5, cases
from native_math import NativeMath
from state_evidence import Rejected
from witness_gateway import StableGateway
from wire_evidence import verify_wire_baseline, verify_wire_object, verify_wire

VARIANTS = {"baseline": verify_wire_baseline, "optimized": verify_wire}


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
    p.add_argument("--library-sha256", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--pilot", action="store_true")
    a = p.parse_args(); a.out.mkdir(parents=True, exist_ok=False)
    allowed = sorted(os.sched_getaffinity(0)); os.sched_setaffinity(0, {allowed[0]})
    assert gc.isenabled()
    assert {n: version(n) for n in ("trie", "rlp", "eth-hash", "pycryptodome")} == {
        "trie": "4.0.0", "rlp": "5.0.0", "eth-hash": "0.8.0", "pycryptodome": "3.24.1"}
    native = NativeMath(a.library, a.library_sha256)
    inputs = cases()
    now = max(p.anchor.timestamp for _, p in inputs)
    count, repetitions = (256, 1) if a.pilot else (8192, 3)
    files = sorted(f for d in ("python", "scripts", "tests") for f in (ROOT / d).rglob("*.py"))
    files += [ROOT / "PRE_REGISTER.md", ROOT / "CONFIRMATION_PLAN.md"]
    before = {str(f.relative_to(ROOT)): sha(f) for f in files}
    meta = {"scope": "SYNTHETIC_WIRE_BYTES_TO_LOCAL_SCENARIO_NO_NETWORK_OR_REAL_STATE",
            "pilot": a.pilot, "pairs_per_run": count, "repetitions": repetitions,
            "cpu": subprocess.check_output(["lscpu"], text=True),
            "cpuinfo": Path("/proc/cpuinfo").read_text(), "platform": platform.platform(),
            "python": sys.version, "gc_enabled": gc.isenabled(),
            "affinity": sorted(os.sched_getaffinity(0)), "allowed_affinity": allowed,
            "conditions": "KVM host frequency/load/IRQ uncontrolled; no governor/priority/NUMA changes",
            "clock": "CLOCK_MONOTONIC_RAW; no overhead subtraction or trimming",
            "clock_info": str(time.get_clock_info("monotonic")),
            "dependencies": {n: version(n) for n in ("trie", "rlp", "eth-hash", "pycryptodome")},
            "source_sha256": before, "library_sha256": sha(a.library),
            "baseline_sha256": {str(f.relative_to(ROOT.parent)): sha(f) for f in
                (R5 / "python/proof_traversal.py", R5 / "python/state_evidence_fast.py", R5 / "python/fast_gateway.py", R3 / "src/state_evidence.py", R3 / "src/gateway.py", R4 / "python/stable_gateway.py",
                 R4 / "python/native_math.py", R4 / "src/lib.rs")},
            "wire_input_sha256": [hashlib.sha256(raw).hexdigest() for raw, _ in inputs],
            "budgets_ns": {"ingress": 50_000_000, "scenario": 5_000_000},
            "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "runs": []}
    aggregated = {mode: {v: [] for v in VARIANTS} for mode in ("wire_verify", "full_ingress")}
    clock = lambda: time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)
    with zipfile.ZipFile(a.out / "raw.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for rep in range(repetitions):
            modes = ("wire_verify", "full_ingress") if rep % 2 == 0 else ("full_ingress", "wire_verify")
            for mode in modes:
                seed = 666612 + rep * 2 + (mode == "full_ingress")
                sequence = [i % 208 for i in range(count)]
                random.Random(seed).shuffle(sequence)
                gateways = {v: StableGateway(inputs[0][1], native, verifier=f) for v, f in VARIANTS.items()}
                def call(variant, i):
                    raw, policy = inputs[i // 13]
                    if mode == "wire_verify":
                        return VARIANTS[variant](raw, policy, now)
                    g = gateways[variant]; g.reset(policy)
                    t = g.ingest(raw, now)
                    return g.scenario(t, now, (1 + i % 13) * 10**35), g.authorize(t, now)
                for i in range(64):
                    assert call("baseline", i) == call("optimized", i)
                values = {v: [] for v in gateways}; statuses = {v: bytearray() for v in gateways}
                checks = {v: hashlib.sha256() for v in gateways}
                clocks = []; drops = []; outputs_seen = set()
                usage0 = resource.getrusage(resource.RUSAGE_SELF)
                for pair, i in enumerate(sequence):
                    c0 = clock(); c1 = clock(); clocks.append(c1 - c0)
                    names = tuple(VARIANTS)
                    offset = pair % 2
                    order = names[offset:] + names[:offset]
                    outputs = {}
                    for variant in order:
                        start = clock()
                        try:
                            result = call(variant, i); reason = None
                        except Rejected as e:
                            result = None; reason = str(e)
                        elapsed = clock() - start
                        values[variant].append(elapsed)
                        if reason is None:
                            statuses[variant].append(0)
                            encoded = repr(result).encode()
                            checks[variant].update(encoded); outputs_seen.add(hashlib.sha256(encoded).hexdigest())
                            outputs[variant] = result
                        else:
                            assert mode == "full_ingress" and any(s in reason for s in
                                ("deadline exceeded", "expired during", "monotonic snapshot expiry")), reason
                            statuses[variant].append(1)
                            drops.append({"pair": pair, "variant": variant, "reason": reason, "elapsed_ns": elapsed})
                    if outputs:
                        first = next(iter(outputs.values()))
                        assert all(value == first for value in outputs.values())
                    if (pair + 1) % 1024 == 0: print(f"{mode} rep{rep}: {pair + 1} pairs", flush=True)
                usage1 = resource.getrusage(resource.RUSAGE_SELF)
                label = f"{mode}-rep{rep}"
                z.writestr(label + "-indices.bin", packed(sequence))
                z.writestr(label + "-clock.bin", packed(clocks))
                for variant in values:
                    z.writestr(label + "-" + variant + ".bin", packed(values[variant]))
                    z.writestr(label + "-" + variant + "-status.bin", statuses[variant])
                    aggregated[mode][variant].extend(values[variant])
                meta["runs"].append({"label": label, "mode": mode, "rep": rep, "seed": seed,
                    "stats_ns": {v: stats(x) for v, x in values.items()}, "clock_ns": stats(clocks),
                    "paired_delta_ns": {v: stats([b-a for a,b in zip(values["baseline"], values[v])]) for v in ("optimized",)},
                    "drops": drops, "distinct_outputs": len(outputs_seen),
                    "output_sha256": {v: h.hexdigest() for v,h in checks.items()},
                    "context_switches": {"voluntary": usage1.ru_nvcsw-usage0.ru_nvcsw,
                                         "involuntary": usage1.ru_nivcsw-usage0.ru_nivcsw},
                    "sample_sha256": {v: hashlib.sha256(packed(x)).hexdigest() for v,x in values.items()}})
    assert before == {str(f.relative_to(ROOT)): sha(f) for f in files}
    meta["aggregate_ns"] = {m: {v: stats(x) for v,x in variants.items()} for m,variants in aggregated.items()}
    meta["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    meta["raw_sha256"] = sha(a.out / "raw.zip")
    (a.out / "result.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps({"aggregate_ns": meta["aggregate_ns"], "drops": sum(len(r["drops"]) for r in meta["runs"])}))


if __name__ == "__main__": main()
