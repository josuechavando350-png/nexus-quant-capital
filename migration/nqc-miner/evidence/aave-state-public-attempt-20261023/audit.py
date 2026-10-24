#!/usr/bin/env python3
"""Offline review of this retained capture, not cryptographic state attestation.

Replays preparation with actual Rust/Polars, then independently decodes every
retained ABI response and binds report, config, original event and run artifacts.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile

MODULE = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(MODULE / "research"), str(MODULE / "scripts")]
from bind_run_config import bind, validate_about, write_new_atomic
from export_parquet import _bounded_read, _json
from prepare_aave_reads import prepare

ZERO = "0x" + "0" * 40
PLAN_FIELDS = "schema_version scope_id borrower assets from_block to_block event_block event_block_hash".split()
CONFIG_FIELDS = "schema_version namespace producer run_id data_class code_commit cargo_lock_sha256 build_identity_sha256 observer_bridge_enabled signing_enabled gas_budget_mxn_centavos scopes".split()
SCOPE_FIELDS = "id chain_id protocol contract event_topics from_block to_block chunk_blocks providers deployment_source".split()
ACCOUNT_FIELDS = "total_collateral_base total_debt_base available_borrows_base liquidation_threshold_bps ltv_bps health_factor_wad".split()


def require(value, message):
    if not value:
        raise ValueError(message)


def packed(value, sort=False):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=sort, allow_nan=False).encode()


def same(a, b):
    return packed(a, True) == packed(b, True)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load(path):
    return _json(_bounded_read(path, 2 * 1024 * 1024))


def files(root):
    require(not any(p.is_symlink() for p in root.rglob("*")), "symlink in evidence")
    return {str(p.relative_to(root)): sha(p.read_bytes()) for p in sorted(root.rglob("*")) if p.is_file()}


def header(h):
    require(set(h) == {"number", "hash", "parent_hash", "timestamp"}, "header fields")
    for k in ("number", "timestamp"):
        require(type(h[k]) is int and 0 <= h[k] < 2**64, "header integer")
    for k in ("hash", "parent_hash"):
        require(isinstance(h[k], str) and re.fullmatch(r"0x[0-9a-f]{64}", h[k])
                and int(h[k], 16) != 0, "header hash")


def decode_call(call, providers, block, target, data, count):
    params = [{"from": ZERO, "to": target, "data": data, "value": "0x0", "gas": "0x1e8480"},
              {"blockHash": block, "requireCanonical": True}]
    require(set(call) == {"params", "replies"} and same(call["params"], params), "call not expected pinned getter")
    replies = call["replies"]
    require([r["provider_id"] for r in replies] == providers, "provider identities/order")
    raw = replies[0]["result"]
    require(isinstance(raw, str) and re.fullmatch(r"0x[0-9a-f]{" + str(count * 64) + "}", raw), "ABI length/hex")
    require(all(set(r) == {"provider_id", "result"} and r["result"] == raw for r in replies), "provider disagreement")
    return [int(raw[i:i + 64], 16) for i in range(2, len(raw), 64)]


def address(word, allow_zero=False):
    require(0 <= word < 2**160 and (allow_zero or word != 0), "ABI address")
    return f"0x{word:040x}"


def audit_report(report, config, plan, source_record):
    canonical_config = {k: config[k] for k in CONFIG_FIELDS}
    canonical_config["scopes"] = [{k: s[k] for k in SCOPE_FIELDS} for s in config["scopes"]]
    for s in canonical_config["scopes"]:
        s["providers"] = [{k: p[k] for k in ("id", "url_env")} for p in s["providers"]]
    owner = {"schema": "nqc-miner-owner-v2", **{k: config[k] for k in
             ("namespace", "producer", "run_id", "data_class", "code_commit", "cargo_lock_sha256", "build_identity_sha256")},
             "config_sha256": sha(packed(canonical_config))}
    require(same(report["owner"], owner) and same(report["plan"], plan), "report owner/plan binding")
    require(report["plan_sha256"] == sha(packed({k: plan[k] for k in PLAN_FIELDS})), "canonical plan hash")
    require(report["schema"] == "nqc-miner-aave-state-v1", "schema")
    for k in ("source_journal_binding_verified", "executable_eligibility_verified", "prices_freshness_verified",
              "economic_certification", "activation_allowed"):
        require(report[k] is False, "unsupported claim")
    require(report["provider_agreement_is_not_state_authentication"] is True, "authentication disclaimer")
    require(report["first_eligible_block"] is None and report["liquidation_delay_blocks"] is None, "invented eligibility")
    require(report["state_timing"] == "end_of_block_before_event_block; no intra-block reconstruction", "state timing")
    scope = next(s for s in config["scopes"] if s["id"] == plan["scope_id"])
    providers = [p["id"] for p in scope["providers"]]
    require(report["providers"] == providers and len(set(providers)) >= 2, "report providers")
    event, finalized = report["event_anchor"], report["finalized_anchor"]
    header(event); header(finalized)
    require(event["number"] == plan["event_block"] and event["hash"] == plan["event_block_hash"]
            and event["timestamp"] == source_record["block_timestamp"], "event anchor/source")
    require(finalized["number"] >= event["number"] and finalized["timestamp"] >= event["timestamp"], "finality order")
    samples = report["samples"]
    require(len(samples) == plan["to_block"] - plan["from_block"] + 1, "incomplete interval")
    previous, episodes, oracle_configs = None, [], []
    for i, sample in enumerate(samples):
        block = sample["block"]; header(block)
        require(block["number"] == plan["from_block"] + i, "block sequence")
        if previous:
            require(block["parent_hash"] == previous["hash"] and block["timestamp"] >= previous["timestamp"], "parent continuity")
        previous = block
        calls = sample["calls"]
        require(len(calls) == 5 + len(plan["assets"]), "missing/extra calls")
        get = lambda n, to, data, count=1: decode_call(calls[n], providers, block["hash"], to, data, count)
        provider = address(get(0, scope["contract"], "0x0542975c")[0])
        oracle = address(get(1, provider, "0xfca513a8")[0])
        base = address(get(2, oracle, "0xe19f4700")[0], True)
        unit = get(3, oracle, "0x8c89b64f")[0]
        require(unit > 0, "zero oracle unit")
        words = get(4, scope["contract"], "0xbf92857c" + "0" * 24 + plan["borrower"][2:], 6)
        require(words[3] <= 10000 and words[4] <= 10000, "account basis points")
        breach = words[1] != 0 and words[5] < 10**18
        account = dict(zip(ACCOUNT_FIELDS, map(str, words)))
        account["health_factor_below_one_with_debt"] = breach
        prices = []
        for n, asset in enumerate(plan["assets"], 5):
            price = get(n, oracle, "0xb3596f07" + "0" * 24 + asset[2:])[0]
            require(price > 0, "zero price")
            prices.append({"asset": asset, "price_base": str(price)})
        expected = {"block": block, "addresses_provider": provider, "oracle": oracle,
                    "base_currency": base, "base_currency_unit": str(unit), "base_currency_is_usd_by_interface": base == ZERO,
                    "account": account, "prices": prices, "calls": calls}
        require(same(sample, expected), "decoded values differ from raw ABI")
        oracle_configs.append((provider, oracle, base, unit))
        if breach:
            if i and samples[i - 1]["account"]["health_factor_below_one_with_debt"]:
                episodes[-1].update(last_sampled_block=block["number"], right_censored=i + 1 == len(samples))
            else:
                episodes.append({"first_sampled_block": block["number"], "last_sampled_block": block["number"],
                                 "left_censored": i == 0, "right_censored": i + 1 == len(samples)})
    require(event["parent_hash"] == previous["hash"] and event["timestamp"] >= previous["timestamp"], "event parent")
    require(same(report["breach_episodes"], episodes), "health episodes")
    require(report["oracle_configuration_changed"] is (len(set(oracle_configs)) > 1), "oracle change flag")
    return {"samples": len(samples), "agreed_getters": sum(len(s["calls"]) for s in samples),
            "raw_provider_replies": sum(len(c["replies"]) for s in samples for c in s["calls"]),
            "event_identity": source_record["decoded"]["payload"]["identity"], "breach_episodes": episodes,
            "last_health_factor_wad": samples[-1]["account"]["health_factor_wad"],
            "last_prices": samples[-1]["prices"], "last_oracle": samples[-1]["oracle"],
            "last_base_currency": samples[-1]["base_currency"], "last_base_currency_unit": samples[-1]["base_currency_unit"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    initial = files(root)
    binary_sha = sha(args.binary.read_bytes())
    source = MODULE / "evidence/public-capture-v2-20261022/state"
    source_hashes = files(source)
    replays, results = [], []
    with tempfile.TemporaryDirectory(prefix="nqc-aave-evidence-audit-") as work:
        for lookback, name, runs in [(1, "aave-state-smoke-plan-20261023", [("run-001", 0)]),
                                   (16, "aave-state-plans-20261023", [(f"history-{i:03d}", i) for i in range(3)])]:
            original = MODULE / "evidence" / name
            replay = Path(work) / name
            manifest = prepare(source, replay, args.binary, lookback)
            require(files(original) == files(replay), "plan/export replay is not byte identical")
            replays.append({"directory": str(original.relative_to(MODULE)), "files_matched": len(files(original))})
            lines = (source / "events.jsonl").read_bytes().splitlines(keepends=True)
            for run_name, index in runs:
                run = root / run_name
                execution = load(run / "execution.json")
                require(execution["binary_sha256"] == binary_sha and execution["binary_and_inputs_unchanged"] is True, "capture executable")
                require(execution["report_returned"] is True, "capture did not return report")
                for name_, digest in execution["files"].items():
                    require(sha((run / name_).read_bytes()) == digest, "capture file changed")
                require(set(execution["files"]) == {p.name for p in run.iterdir() if p.name != "execution.json"}, "capture file coverage")
                require([c["name"] for c in execution["checks"]] == ["about-before", "validate-plan", "read-state", "about-after"], "missing step")
                require(all(type(c["exit_code"]) is int and c["exit_code"] == 0 and c["timed_out"] is False for c in execution["checks"]), "failed capture step")
                about = load(run / "about-before.stdout"); validate_about(about)
                require(same(about, load(run / "about-after.stdout")), "build changed")
                config = load(run / "config.json")
                require(same(config, bind(load(original / "config.template.json"), about)), "config/template mismatch")
                entry = manifest["events"][index]
                plan = load(original / entry["plan_file"])
                require(same(load(run / "plan.json"), plan), "captured plan mismatch")
                require(same(execution["input_sha256"], {"template": sha((original / "config.template.json").read_bytes()),
                                                        "plan": sha((original / entry["plan_file"]).read_bytes())}), "capture input hashes")
                source_line = lines[entry["sequence"]]
                require(sha(source_line) == entry["source_line_sha256"], "event raw line")
                record = json.loads(source_line)["record"]
                result = audit_report(load(run / "read-state.stdout"), config, plan, record)
                results.append({"run": run_name, "source_binding_verified_in_this_audit": True, **result})
    require(source_hashes == files(source) and binary_sha == sha(args.binary.read_bytes()) and initial == files(root), "input mutated during audit")
    full = [r for r in results if r["run"].startswith("history-")]
    summary = {"schema": "nqc-miner-aave-public-audit-v1", "status": "pass", "completed_at_utc": datetime.now(timezone.utc).isoformat(),
               "audit_script_sha256": sha(Path(__file__).read_bytes()), "verifier_sha256": binary_sha,
               "source_files": source_hashes, "source_unchanged": True, "plan_replays": replays, "runs": results,
               "unique_historical_states": sum(r["samples"] for r in full), "distinct_source_events": len(full),
               "smoke_state_repeats_first_history": True, "source_journal_binding_verified": True,
               "state_authentication_verified": False, "provider_independence_verified": False,
               "executable_eligibility_verified": False, "prices_freshness_verified": False,
               "economic_certification": False, "observer_bridge_enabled": False, "activation_allowed": False,
               "files": initial}
    write_new_atomic(args.output, summary)
    print(json.dumps({k: summary[k] for k in ("status", "unique_historical_states", "distinct_source_events", "source_journal_binding_verified")}))


if __name__ == "__main__":
    main()
