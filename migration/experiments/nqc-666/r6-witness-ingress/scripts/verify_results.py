"""Recompute all distributions/gates from raw individual samples; no trimming."""
import argparse
import array
import hashlib
import json
from pathlib import Path
import random
import sys
import zipfile

from corpus import ROOT, cases
VARIANTS = ("baseline", "object", "optimized")


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
    assert result["wire_input_sha256"] == [hashlib.sha256(raw).hexdigest() for raw,_ in cases()]
    n = result["pairs_per_run"]
    reps = result["repetitions"]
    assert (n, reps) == ((256,1) if result["pilot"] else (2048,3))
    assert len(result["runs"]) == 2 * reps
    combined = {m: {v: [] for v in VARIANTS} for m in ("wire_verify", "full_ingress")}
    median_checks = {v: [] for v in VARIANTS[1:]}
    drops_by_variant = {v: 0 for v in VARIANTS}
    seen = set()
    with zipfile.ZipFile(path / "raw.zip") as z:
        assert len(z.namelist()) == 16 * reps
        for run in result["runs"]:
            mode, rep, label = run["mode"], run["rep"], run["label"]
            assert (mode,rep) not in seen and 0 <= rep < reps
            seen.add((mode,rep))
            assert label == f"{mode}-rep{rep}"
            assert run["seed"] == 666602 + rep * 2 + (mode == "full_ingress")
            sequence = [i % 208 for i in range(n)]; random.Random(run["seed"]).shuffle(sequence)
            assert unpack(z.read(label + "-indices.bin")) == sequence
            clocks = unpack(z.read(label + "-clock.bin"))
            assert len(clocks) == n and distribution(clocks) == run["clock_ns"]
            values = {}; statuses = {}
            for variant in VARIANTS:
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
            for v,_ in drops: drops_by_variant[v] += 1
            if not drops: assert len(set(run["output_sha256"].values())) == 1
            assert run["distinct_outputs"] > 1
            for v in VARIANTS[1:]:
                assert distribution([b-a for a,b in zip(values["baseline"], values[v])]) == run["paired_delta_ns"][v]
                median_checks[v].append(run["stats_ns"][v]["p50"] * 100 <= run["stats_ns"]["baseline"]["p50"] * 95)
    aggregate = {m: {v: distribution(x) for v,x in variants.items()} for m,variants in combined.items()}
    assert aggregate == result["aggregate_ns"]
    tail_checks = {v: {m: {k: variants[v][k] * 100 <= variants["baseline"][k] * 105
                            for k in ("p99", "p99_9", "max")} for m,variants in aggregate.items()}
                   for v in VARIANTS[1:]}
    eligible = {v: (not result["pilot"] and all(median_checks[v]) and
                     all(all(c.values()) for c in tail_checks[v].values()) and
                     drops_by_variant[v] <= drops_by_variant["baseline"]) for v in VARIANTS[1:]}
    object_tail_guard = all(variants["optimized"][k] * 100 <= variants["object"][k] * 105
                           for variants in aggregate.values() for k in ("p99", "p99_9", "max"))
    if eligible["optimized"] and (not eligible["object"] or (object_tail_guard and
        aggregate["full_ingress"]["optimized"]["p50"] < aggregate["full_ingress"]["object"]["p50"])):
        selected = "optimized"
    elif eligible["object"]: selected = "object"
    else: selected = "baseline"
    return {"raw_distributions_verified": True, "individual_windows": n * reps * 6,
            "all_attempts_retained": True, "late_drops_by_variant": drops_by_variant,
            "median_5pct_all_repetitions": {v: all(c) for v,c in median_checks.items()},
            "tail_checks_105pct": tail_checks, "optimized_vs_object_tail_guard": object_tail_guard,
            "local_sample_eligible": eligible, "selected_experimental_variant": selected,
            "api_and_cli_default": "baseline", "whole_bot_stabilized": False,
            "authentic_witness_integrated": False, "network_builder_e2e_measured": False,
            "commercial_admission": False,
            "blockers": ["no_authenticated_real_Morpho_account_storage_witness",
                         "NQC031_capture_chain4663_incomplete_no_pretransaction_root",
                         "canonical_chain_and_runtime_layout_not_attested",
                         "oracle_IRM_EVM_and_financial_authorization_external"]}



if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("path", type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.path), indent=2))
