"""Recompute all distributions/gates from raw individual samples; no trimming."""
import argparse
import array
import hashlib
import json
from pathlib import Path
import random
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def unpack(raw):
    a = array.array("Q"); a.frombytes(raw)
    if sys.byteorder != "little": a.byteswap()
    return list(a)


def distribution(values):
    v = sorted(values); n = len(v)
    return {"n": n, "min": v[0], "max": v[-1], **{k: v[(n * p + q - 1) // q - 1]
            for k,p,q in (("p50",1,2), ("p95",95,100), ("p99",99,100), ("p99_9",999,1000))}}


def check(path):
    result = json.loads((path / "result.json").read_text())
    assert result["raw_sha256"] == sha(path / "raw.zip")
    for name, digest in result["source_sha256"].items(): assert sha(ROOT / name) == digest, name
    for name, digest in result["baseline_sha256"].items(): assert sha(ROOT.parent / name) == digest, name
    for name, digest in result["fixture_sha256"].items():
        assert sha(ROOT.parent / "r3-state-evidence/fixtures" / name) == digest, name
    n = result["pairs_per_run"]
    reps = result["repetitions"]
    assert (n, reps) == ((256,1) if result["pilot"] else (4096,3))
    assert len(result["runs"]) == 2 * reps
    combined = {m: {v: [] for v in ("r4", "r5")} for m in ("proof", "full_ingress")}
    median_checks = []; drop_count = 0
    seen = set()
    with zipfile.ZipFile(path / "raw.zip") as z:
        assert len(z.namelist()) == 12 * reps
        for run in result["runs"]:
            mode, rep, label = run["mode"], run["rep"], run["label"]
            assert (mode,rep) not in seen and 0 <= rep < reps
            seen.add((mode,rep))
            assert label == f"{mode}-rep{rep}"
            assert run["seed"] == 666502 + rep * 2 + (mode == "full_ingress")
            sequence = [i % 208 for i in range(n)]; random.Random(run["seed"]).shuffle(sequence)
            assert unpack(z.read(label + "-indices.bin")) == sequence
            clocks = unpack(z.read(label + "-clock.bin"))
            assert len(clocks) == n and distribution(clocks) == run["clock_ns"]
            values = {}; statuses = {}
            for variant in ("r4", "r5"):
                raw = z.read(label + "-" + variant + ".bin")
                values[variant] = unpack(raw)
                statuses[variant] = z.read(label + "-" + variant + "-status.bin")
                assert len(values[variant]) == len(statuses[variant]) == n
                assert set(statuses[variant]) <= {0,1}
                assert hashlib.sha256(raw).hexdigest() == run["sample_sha256"][variant]
                assert distribution(values[variant]) == run["stats_ns"][variant]
                combined[mode][variant].extend(values[variant])
            drops = {(v,i) for v in statuses for i,s in enumerate(statuses[v]) if s}
            assert len(drops) == len(run["drops"])
            assert drops == {(d["variant"],d["pair"]) for d in run["drops"]}
            for d in run["drops"]:
                assert mode == "full_ingress"
                assert d["elapsed_ns"] == values[d["variant"]][d["pair"]]
                assert any(x in d["reason"] for x in
                           ("deadline exceeded", "expired during", "monotonic snapshot expiry"))
            drop_count += len(drops)
            if not drops: assert run["output_sha256"]["r4"] == run["output_sha256"]["r5"]
            assert run["distinct_outputs"] > 1
            assert distribution([b-a for a,b in zip(values["r4"], values["r5"])]) == run["paired_delta_r5_minus_r4_ns"]
            median_checks.append(run["stats_ns"]["r5"]["p50"] * 10 <= run["stats_ns"]["r4"]["p50"] * 9)
    aggregate = {m: {v: distribution(x) for v,x in variants.items()} for m,variants in combined.items()}
    assert aggregate == result["aggregate_ns"]
    tail_checks = {m: {k: variants["r5"][k] * 100 <= variants["r4"][k] * 105
                      for k in ("p99", "p99_9", "max")} for m,variants in aggregate.items()}
    performance_pass = (not result["pilot"] and all(median_checks) and
                        all(all(checks.values()) for checks in tail_checks.values()))
    return {"raw_distributions_verified": True, "individual_windows": n * reps * 4,
            "all_attempts_retained": True, "late_drops": drop_count,
            "median_10pct_all_repetitions": all(median_checks), "tail_checks_105pct": tail_checks,
            "local_sample_performance_gate": performance_pass,
            "whole_bot_stabilized": False, "commercial_admission": False,
            "blockers": ["no_authenticated_real_account_storage_witness",
                         "canonical_chain_and_runtime_layout_not_attested",
                         "oracle_IRM_and_EVM_execution_unvalidated",
                         "financial_nonrecourse_authorization_external",
                         "no_host_execution_latency_bound_or_live_end_to_end_test"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("path", type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.path), indent=2))
