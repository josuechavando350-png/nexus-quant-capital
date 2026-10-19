"""Follow-up to measured full-ingress regression; no runtime code changes."""
import argparse
import array
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from benchmark import stats, packed, sha, R3, NativeMath, Gateway, StableGateway, policy_from, Rejected


def main():
    p = argparse.ArgumentParser(); p.add_argument("--library", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args(); a.out.mkdir(parents=True, exist_ok=False)
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    native = NativeMath(a.library, sha(a.library))
    index = json.loads((R3 / "fixtures/synthetic-index.json").read_text())
    cases = [((R3 / "fixtures" / r["packet"]).read_bytes(), policy_from(r["policy"])) for r in index]
    now = max(p.anchor.timestamp for _, p in cases)
    gateways = {"r3_native": Gateway(cases[0][1]), "r4_native": StableGateway(cases[0][1], native)}
    sequence = list(range(16)) * 768
    random.Random(666405).shuffle(sequence)
    values = {k: [] for k in gateways}
    statuses = {k: bytearray() for k in gateways}
    checks = {k: hashlib.sha256() for k in gateways}
    clocks = []; drops = []
    clock = lambda: time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)
    def call(name, i):
        raw, policy = cases[i % 16]; g = gateways[name]
        g.reset(policy); ticket = g.ingest(raw, now)
        price = (1 + i % 13) * 10**35
        result = (g.scenario(ticket, now, price) if name == "r4_native"
                  else g.scenario(ticket, now, price, native))
        return result, g.authorize(ticket, now)
    for i in range(64):
        call("r3_native", i); call("r4_native", i)
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for pair, i in enumerate(sequence):
        order = ("r3_native", "r4_native") if pair % 2 == 0 else ("r4_native", "r3_native")
        output = {}
        for name in order:
            c0 = clock(); c1 = clock(); clocks.append(c1 - c0)
            start = clock()
            try:
                result = call(name, i); reason = None
            except Rejected as e:
                result = None; reason = str(e)
            elapsed = clock() - start
            values[name].append(elapsed)
            if reason is None:
                statuses[name].append(0); checks[name].update(repr(result).encode())
                output[name] = result
            else:
                assert name == "r4_native" and any(x in reason for x in ("deadline exceeded", "expired during", "monotonic snapshot expiry"))
                statuses[name].append(1); drops.append({"pair": pair, "variant": name, "reason": reason, "elapsed_ns": elapsed})
                # The next pair resets/reverifies before using this gateway.
        if len(output) == 2: assert output["r3_native"] == output["r4_native"]
        if (pair + 1) % 4096 == 0: print(json.dumps({"pairs": pair + 1}), flush=True)
    delta = [b - a for a, b in zip(values["r3_native"], values["r4_native"])]
    with zipfile.ZipFile(a.out / "raw.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for name in values:
            z.writestr(name + ".bin", packed(values[name]))
            z.writestr(name + "-status.bin", statuses[name])
        z.writestr("clock.bin", packed(clocks))
    files = [ROOT / "python/stable_gateway.py", ROOT / "python/native_math.py", ROOT / "src/lib.rs",
             ROOT / "scripts/paired_ingress.py", ROOT / "PAIRED_ADDENDUM.md"]
    result = {"started_utc": started, "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "pairs": len(sequence), "stats_ns": {k: stats(v) for k, v in values.items()},
              "clock_ns": stats(clocks), "paired_delta_r4_minus_r3_ns": stats(delta),
              "r4_faster_pairs": sum(d < 0 for d in delta), "drops": drops,
              "output_sha256": {k: v.hexdigest() for k, v in checks.items()},
              "sample_sha256": {k: hashlib.sha256(packed(v)).hexdigest() for k, v in values.items()},
              "source_sha256": {str(f.relative_to(ROOT)): sha(f) for f in files},
              "library_sha256": sha(a.library), "affinity": sorted(os.sched_getaffinity(0)),
              "scope": "PAIRED_SYNTHETIC_INGRESS_SAME_NATIVE_ARITHMETIC_NO_RUNTIME_CHANGE"}
    (a.out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__": main()
