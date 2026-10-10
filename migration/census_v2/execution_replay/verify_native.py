#!/usr/bin/env python3
"""Bind the offline native realization run; retain all economic non-claims."""
import argparse
import json
from pathlib import Path
import re
import tempfile
import zipfile
from native_realization import NATIVE_SOURCE_SHA, WITNESS_SHA, NATIVE_TEST
from rpc_witness import Witness, canonical, sha, WINNER
from run_fork import TEST_PATH, FORGE_SHA, SOLC_SHA
from run_comparison import INPUTS_SHA
from verify_funding import need, ARCHIVE_SHA as FUNDING_ARCHIVE_SHA

HERE = Path(__file__).resolve().parent
ARCHIVE_SHA = "46bdc3d97787154e286a8c210bdfdf07d2faf4788dc0fd8d52dc58357dd0643a"


def metrics(raw):
    need(b"4 passed; 0 failed; 0 skipped" in raw, "four successful tests missing")
    pairs = re.findall(r"^  NQC_NATIVE_([A-Z_0-9]+): ([0-9]+)$", raw.decode(), re.M)
    need(len(pairs) == len(dict(pairs)) == 6, "native metrics missing or duplicated")
    m = {k:int(v) for k,v in pairs}
    need(m["CALLDATA_BYTES"] == m["ZERO_BYTES"] + m["NONZERO_BYTES"], "calldata counts")
    need(m["INTRINSIC_4_16"] == 21000 + 4*m["ZERO_BYTES"] + 16*m["NONZERO_BYTES"], "intrinsic component")
    need(m["REALIZED_WEI"] == 240390311727552, "native residual differs")
    return m


def verify(path):
    need(sha(Path(path).read_bytes()) == ARCHIVE_SHA, "native archive digest")
    funding = HERE / "inputs/funding-scenarios.zip"
    need(sha(funding.read_bytes()) == FUNDING_ARCHIVE_SHA, "parent funding evidence differs")
    with zipfile.ZipFile(path) as z, zipfile.ZipFile(funding) as parent:
        manifest = json.loads(z.read("manifest.json"))
        names = z.namelist()
        need(len(names) == len(set(names)) == 20 and set(names) == set(manifest["files"]) | {"manifest.json"}, "archive membership")
        for name,pin in manifest["files"].items():
            raw = z.read(name)
            need((len(raw),sha(raw)) == (pin["bytes"],pin["sha256"]), "archive member binding")
        report = json.loads(z.read("offline-001/report.json"))
        need(report["status"] == "NATIVE_REALIZATION_PASSED_NOT_ECONOMIC_ADMISSION", "native run failed")
        need(report["mode"] == "OFFLINE_ONLY" and report["upstream_requests"] == 0, "offline claim")
        for key in ["original_executor_modified", "production_operator_implemented", "gas_financing_proven",
                    "census_closed", "independent_certification", "live_transaction_sent"]:
            need(report[key] is False, "unsupported authority")
        need(report["complete_profit_wei"] is None, "unsupported complete profit")
        for name,digest in report["producer_sources"].items():
            need(sha(z.read("producer-v1/" + name)) == sha((HERE / name).read_bytes()) == digest, "producer source identity")
        need(report["forge_sha256"] == FORGE_SHA and report["solc_sha256"] == SOLC_SHA, "toolchain identity")
        need(sha(z.read("inputs/sources.json")) == report["input_manifest_sha256"] == INPUTS_SHA, "input manifest")
        for name,pin in json.loads(z.read("inputs/sources.json"))["files"].items():
            need(sha(z.read("inputs/" + name)) == pin["sha256"], "original source bytes")
            expected = NATIVE_SOURCE_SHA if name == TEST_PATH else pin["sha256"]
            need(sha(z.read("offline-001/source/" + name)) == expected, "effective source bytes")
        need(z.read("offline-001/source/" + TEST_PATH) ==
             parent.read("bid-offline-002/balancer_bid/source/" + TEST_PATH) + NATIVE_TEST.encode(), "parent scenario assertions changed")
        need(report["native_source_sha256"] == NATIVE_SOURCE_SHA, "native postimage")
        need(sha(z.read("witness.jsonl")) == report["witness_sha256"] == WITNESS_SHA, "witness digest")
        need(z.read("witness.jsonl") == parent.read("bid-capture-001/combined-upstream.jsonl"), "new state substituted")
        measured = {}
        need([r["mode"] for r in report["runs"]] == ["build","normal","isolated"], "run inventory")
        for run in report["runs"]:
            raw = z.read("offline-001/" + run["mode"] + ".log")
            need(run["exit_code"] == 0 and sha(raw) == run["log_sha256"], "log binding")
            if run["mode"] != "build": measured[run["mode"]] = metrics(raw)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d); (p / "witness.jsonl").write_bytes(z.read("witness.jsonl"))
            w = Witness(p / "offline", replay=p / "witness.jsonl", provider="nodies")
            need(len(w.cache) == 127, "witness population")
            rows = [json.loads(x) for x in z.read("offline-001/rpc/requests.jsonl").splitlines()]
            for row in rows:
                result = w.call(row["method"],row["params"])
                need(row["source"] == "retained_response" and sha(canonical(result).encode()) == row["result_sha256"], "response binding")
            header = w.call("eth_getBlockByNumber",[hex(WINNER),False])
            need(w.count == 0, "consumer opened network")
    profiles = []
    for mode,m in measured.items():
        units = m["SETTLEMENT_CALL_GAS"] + m["INTRINSIC_4_16"]
        profiles.append({"mode":mode,"illustrative_gas_component_units":units,
            "remaining_for_other_costs_at_historical_base_fee_wei": str(m["REALIZED_WEI"]-units*int(header["baseFeePerGas"],16)),
            "remaining_for_other_costs_at_1_gwei_wei":str(m["REALIZED_WEI"]-units*1000000000)})
    return {"schema":"nqc-native-realization-readback-v1", "archive_sha256":ARCHIVE_SHA,
        "consumer_sha256":sha(Path(__file__).read_bytes()),"metrics":measured,
        "offline_served_responses_verified":len(rows),"upstream_requests":0,
        "native_recipient":"RESEARCH_OPERATOR_HARNESS_NOT_AUTHENTICATED_GAS_WALLET",
        "operator_native_increase_wei":"240390311727552", "existing_inventory_spent":False,
        "gas_profiles":profiles,"transaction_gas_quote_proven":False,
        "production_operator_implemented":False,"native_wallet_authority_and_upfront_gas_proven":False,
        "deployment_failure_inclusion_and_all_costs_resolved":False,
        "complete_profit_wei":None,"census_closed":False,"independent_certification":False}


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive",required=True);p.add_argument("--output",required=True)
    args=p.parse_args();Path(args.output).write_text(canonical(verify(args.archive))+"\n")
