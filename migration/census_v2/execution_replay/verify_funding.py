#!/usr/bin/env python3
"""Offline provenance, response binding and conditional cost analysis; no admission."""
import argparse
import json
from pathlib import Path, PurePosixPath
import re
import tempfile
import zipfile
from funding_scenarios import SCENARIO_SHAS, OBSERVED_PAYMENT_WEI, FEE_RECIPIENT
from rpc_witness import Witness, canonical, sha, WINNER
from run_comparison import INPUTS_SHA
from run_fork import FORGE_SHA, SOLC_SHA, TEST_PATH, PATCHED_TEST_SHA

HERE = Path(__file__).resolve().parent
ARCHIVE_SHA = "bd9e850c0b53db8b951fdd09ff1ac9b279fc78f2d8ee31acf5462dc120a2c2e4"
FAILED_BID_SHA = "cff8a0763a69a61de6623a65c39b9d8ec6dbd7fc75fea67f3d3ebe85282fc57b"
PASSED = "FUNDING_SCENARIOS_PASSED_NOT_ECONOMIC_ADMISSION"
ATTEMPTS = {"capture-001": "producer-v1", "offline-001": "producer-v1",
            "bid-capture-001": "producer-v2", "bid-offline-002": "producer-v3"}


def need(condition, message):
    if not condition:
        raise ValueError(message)


def metrics(raw):
    text = raw.decode()
    need("2 passed; 0 failed; 0 skipped" in text, "missing successful test summary")
    pairs = re.findall(r"^  NQC_RANK1_FORK_([A-Z_0-9]+): ([0-9]+)$", text, re.M)
    need(len(pairs) == len(dict(pairs)), "duplicate metric")
    result = {k: int(v) for k, v in pairs}
    need(result["CALLDATA_BYTES"] == result["CALLDATA_ZERO_BYTES"] + result["CALLDATA_NONZERO_BYTES"], "calldata counts")
    need(result["INTRINSIC_GAS_4_16"] == 21000 + 4 * result["CALLDATA_ZERO_BYTES"] + 16 * result["CALLDATA_NONZERO_BYTES"], "intrinsic component")
    need(result["PRODUCTION_GAS_SPONSORED"] == 0, "gas sponsorship unsupported")
    return result


def economics(all_metrics, base_fee):
    aave = all_metrics["offline-001"]["aave/normal"]
    vault = all_metrics["offline-001"]["balancer/normal"]
    bid = all_metrics["bid-offline-002"]["balancer_bid/normal"]
    need(vault["FLASH_FEE_WEI"] == vault["VAULT_FEE_WAD"] == 0, "historical vault fee")
    need(vault["VAULT_LIQUIDITY_WEI"] >= 10684013854557827871, "vault principal unavailable")
    need(aave["WETH_SURPLUS_WEI"] + aave["FLASH_FEE_WEI"] == vault["WETH_SURPLUS_WEI"], "funding comparison does not reconcile")
    need(bid["SETTLED_NATIVE_PAYMENT_WEI"] == OBSERVED_PAYMENT_WEI, "settled payment mismatch")
    need(bid["WETH_SURPLUS_WEI"] + OBSERVED_PAYMENT_WEI == vault["WETH_SURPLUS_WEI"], "bid double counted or not funded")
    residual = bid["WETH_SURPLUS_WEI"]
    profiles = []
    for mode in ["normal", "isolated"]:
        m = all_metrics["bid-offline-002"]["balancer_bid/" + mode]
        need({k:v for k,v in m.items() if k != "EXECUTE_CALL_GAS_UNITS"} ==
             {k:v for k,v in bid.items() if k != "EXECUTE_CALL_GAS_UNITS"}, "mode changed economic result")
        units = m["EXECUTE_CALL_GAS_UNITS"] + m["INTRINSIC_GAS_4_16"]
        profiles.append({"mode": mode, "measured_call_gas": m["EXECUTE_CALL_GAS_UNITS"],
            "calldata_intrinsic_component": m["INTRINSIC_GAS_4_16"], "illustrative_gas_units_sum": units,
            "component_only_break_even_price_floor_wei": residual // units,
            "stress": [{"gas_price_wei": str(price), "component_cost_wei": str(units * price),
                        "remaining_for_all_other_costs_wei": str(residual - units * price)}
                       for price in [base_fee, 100000000, 1000000000, 10000000000]]})
    return {"conditional_observed_payment_wei": str(OBSERVED_PAYMENT_WEI),
        "historical_payment_is_minimum_inclusion_price_proven": False,
        "aave_residual_if_matching_payment_before_gas_wei": str(aave["WETH_SURPLUS_WEI"] - OBSERVED_PAYMENT_WEI),
        "balancer_residual_after_atomic_payment_before_gas_wei": str(residual),
        "preexisting_strategy_native_wei_preserved": str(bid["NATIVE_BASELINE_WEI"]),
        "gas_component_profiles": profiles, "complete_profit_wei": None,
        "gas_budget_mxn": "2000", "gas_budget_spent": False, "own_principal_permitted": False,
        "actual_transaction_gas_quote": False, "deployment_amortization_included": False,
        "refunds_cold_state_and_current_fork_rules_fully_modeled": False,
        "gas_financing_and_weth_to_native_realization_proven": False,
        "capture_probability_and_competitive_bid_proven": False,
        "historical_winner_receipt_gas_subtracted_from_new_scenario": False,
        "economic_profit_admitted": False}


def verify(path):
    need(sha(Path(path).read_bytes()) == ARCHIVE_SHA, "archive digest")
    all_metrics, reports = {}, {}
    with zipfile.ZipFile(path) as z:
        manifest = json.loads(z.read("manifest.json"))
        names = z.namelist()
        need(len(names) == len(set(names)) and set(names) == set(manifest["files"]) | {"manifest.json"}, "archive members")
        need(manifest["attempt_producers"] == ATTEMPTS, "attempt population")
        for name, pin in manifest["files"].items():
            need(not PurePosixPath(name).is_absolute() and ".." not in PurePosixPath(name).parts, "unsafe member")
            raw = z.read(name)
            need((len(raw), sha(raw)) == (pin["bytes"], pin["sha256"]), "member digest")
        source_raw = z.read("inputs/sources.json")
        need(sha(source_raw) == INPUTS_SHA, "original input manifest")
        source_manifest = json.loads(source_raw)
        for name, producer in ATTEMPTS.items():
            report = reports[name] = json.loads(z.read(name + "/report.json"))
            need(report["source_manifest_sha256"] == INPUTS_SHA, "source manifest binding")
            need(report["forge_sha256"] == FORGE_SHA and report["solc_sha256"] == SOLC_SHA, "toolchain binding")
            for key in ["capital_admission_changed", "census_closed", "independent_certification", "live_transaction_sent",
                        "historical_decision_time_observation_proven", "production_gas_quote_proven"]:
                need(report[key] is False, "unsupported authority")
            need(report["provider"] == "nodies" and report["rpc_failure"] is None, "provider or RPC failure")
            for f, digest in report["producer_sources"].items():
                need(sha(z.read(producer + "/" + f)) == digest, "producer binding")
                if producer == "producer-v3":
                    need(sha((HERE / f).read_bytes()) == digest, "current producer drift")
            for variant, scenario in report["scenarios"].items():
                expected = FAILED_BID_SHA if name == "bid-capture-001" else SCENARIO_SHAS[variant]
                need(scenario["research_overlay"]["before_sha256"] == PATCHED_TEST_SHA and
                     scenario["research_overlay"]["after_sha256"] == expected, "overlay binding")
                for f, pin in source_manifest["files"].items():
                    need(sha(z.read("inputs/" + f)) == pin["sha256"], "original source bytes")
                    need(sha(z.read(name + "/" + variant + "/source/" + f)) ==
                         (expected if f == TEST_PATH else pin["sha256"]), "effective source bytes")
                need(scenario["build_exit_code"] == 0 and sha(z.read(name + "/" + variant + "/build.log")) == scenario["build_log_sha256"], "build binding")
            all_metrics[name] = {}
            for run in report["runs"]:
                key = run["scenario"] + "/" + run["mode"]
                raw = z.read(name + "/" + key + ".log")
                need(sha(raw) == run["log_sha256"], "run log binding")
                if run["exit_code"] == 0:
                    all_metrics[name][key] = metrics(raw)
                else:
                    need(name == "bid-capture-001" and b"PREEXISTING_NATIVE_BALANCE" in raw and b"FAILED_OPERATION_NATIVE_DRIFT" in raw, "unexpected failure")
            need(report["status"] == ("FAILED" if name == "bid-capture-001" else PASSED), "attempt status")
        need(reports["capture-001"]["upstream_requests"] == 124 and reports["bid-capture-001"]["upstream_requests"] == 3, "acquisition population")
        seed = z.read("capture-001/rpc/upstream.jsonl")
        extra = z.read("bid-capture-001/rpc/upstream.jsonl")
        combined = z.read("bid-capture-001/combined-upstream.jsonl")
        need(z.read("bid-capture-001/seed-upstream.jsonl") == seed and combined == seed + extra, "seed or combined bytes")
        need(reports["bid-capture-001"]["seed"]["sha256"] == sha(seed) and reports["bid-capture-001"]["combined_witness_sha256"] == sha(combined), "witness manifest")
        need(reports["bid-offline-002"]["replay_witness_sha256"] == sha(combined), "replay witness binding")
        counts = {}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            for name, raw in [("offline-001", seed), ("bid-offline-002", combined)]:
                witness_file = p / (name + ".jsonl")
                witness_file.write_bytes(raw)
                witness = Witness(p / name, replay=witness_file, provider="nodies")
                need(len(witness.cache) == (124 if name == "offline-001" else 127), "witness population")
                requests = [json.loads(x) for x in z.read(name + "/rpc/requests.jsonl").splitlines()]
                for row in requests:
                    value = witness.call(row["method"], row["params"])
                    need(row["source"] == "retained_response" and sha(canonical(value).encode()) == row["result_sha256"], "served result binding")
                need(witness.count == reports[name]["upstream_requests"] == 0, "offline network opened")
                counts[name] = len(requests)
            header = witness.call("eth_getBlockByNumber", [hex(WINNER), False])
            need(header["miner"].lower() == FEE_RECIPIENT.lower(), "fee recipient header binding")
        for variant in ["aave", "balancer"]:
            need(all_metrics["capture-001"][variant + "/normal"] == all_metrics["offline-001"][variant + "/normal"], "normal replay differs")
        need(len(all_metrics["offline-001"]) == 4 and len(all_metrics["bid-offline-002"]) == 2, "replay test population")
    return {"schema": "nqc-funding-readback-v1", "archive_sha256": ARCHIVE_SHA,
        "consumer_sha256": sha(Path(__file__).read_bytes()), "metrics": all_metrics,
        "offline_served_requests_checked": counts, "distinct_retained_rpc_requests": 127,
        "failed_attempts_preserved": ["bid-capture-001"], "census_closed": False,
        "independent_certification": False, "merkle_state_proofs_verified": False,
        "economics": economics(all_metrics, int(header["baseFeePerGas"], 16))}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    Path(args.output).write_text(canonical(verify(args.archive)) + "\n")
