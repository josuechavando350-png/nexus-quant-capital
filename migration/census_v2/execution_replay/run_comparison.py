#!/usr/bin/env python3
"""Compare new funding scenarios over one retained, read-only historical witness."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from funding_scenarios import apply_scenario, SCENARIO_SHAS
from rpc_witness import Witness, serve, canonical, sha, now, PREVIOUS, WINNER
from run_fork import checksum_overlay, FORGE_SHA, SOLC_SHA

INPUTS_SHA = "a526cf190d81664f796363aa31b640aa23d1830ca99294f08022ba4db17616ae"
SOURCES = ["rpc_witness.py", "run_fork.py", "funding_scenarios.py", "run_comparison.py"]


def run(args):
    root, inputs = Path(args.out), Path(args.inputs)
    root.mkdir(parents=True, exist_ok=False)
    manifest_raw = (inputs / "sources.json").read_bytes()
    if sha(manifest_raw) != INPUTS_SHA:
        raise ValueError("input manifest differs")
    manifest = json.loads(manifest_raw)
    scenarios = args.scenarios or list(SCENARIO_SHAS)
    if len(scenarios) != len(set(scenarios)):
        raise ValueError("duplicate scenario")
    forge, solc = Path(args.forge), Path(args.solc)
    if sha(forge.read_bytes()) != FORGE_SHA or sha(solc.read_bytes()) != SOLC_SHA:
        raise ValueError("toolchain differs")
    version = subprocess.check_output([str(forge), "--version"], text=True)
    if not version.startswith("forge Version: 1.7.1\n"):
        raise ValueError("Foundry version differs")
    (root / "forge-version.txt").write_text(version)
    report = {"schema": "nqc-funding-comparison-v1", "started_at": now(),
              "producer_parent_commit": "0ed99812e4e1e6f0b9b03fffdab0b90f21cb5d39",
              "source_manifest_sha256": INPUTS_SHA, "provider": "nodies",
              "mode": "OFFLINE_REPLAY" if args.replay else "NEW_RPC_ACQUISITION",
              "forge_sha256": FORGE_SHA, "solc_sha256": SOLC_SHA,
              "producer_sources": {n: sha((Path(__file__).parent / n).read_bytes()) for n in SOURCES},
              "original_state_modified": False, "live_transaction_sent": False,
              "capital_admission_changed": False, "independent_certification": False,
              "census_closed": False, "historical_decision_time_observation_proven": False,
              "earlier_winner_block_transactions_replayed": False,
              "test_gas_price_wei": "0", "production_gas_quote_proven": False,
              "evm_revision": "cancun", "scenarios": {}, "runs": []}
    witness = server = None
    try:
        for variant in scenarios:
            digest = SCENARIO_SHAS[variant]
            source = root / variant / "source"
            source.mkdir(parents=True)
            for name, pin in manifest["files"].items():
                raw = (inputs / name).read_bytes()
                if sha(raw) != pin["sha256"]:
                    raise ValueError("source drift: " + name)
                dst = source / name
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(raw)
            checksum = checksum_overlay(source)
            overlay = apply_scenario(source, variant, digest)
            cmd = [str(forge), "build", "--root", str(source), "--use", str(solc), "--offline"]
            logfile = root / variant / "build.log"
            with logfile.open("w") as log:
                result = subprocess.run(cmd, cwd=source, stdout=log, stderr=subprocess.STDOUT,
                                        timeout=180, check=False)
            report["scenarios"][variant] = {"checksum_overlay": checksum, "research_overlay": overlay,
                "build_command": cmd, "build_exit_code": result.returncode, "build_log_sha256": sha(logfile.read_bytes())}
            if result.returncode:
                raise RuntimeError("offline compilation failed: " + variant)
        witness = Witness(root / "rpc", replay=args.replay, provider="nodies", interval=2.2)
        if args.seed:
            seed_raw = Path(args.seed).read_bytes()
            seed_path = root / "seed-upstream.jsonl"
            seed_path.write_bytes(seed_raw)
            seed_witness = Witness(root / "seed-validation", replay=seed_path, provider="nodies")
            witness.cache.update(seed_witness.cache)
            report["seed"] = {"sha256": sha(seed_raw), "retained_requests": len(seed_witness.cache),
                              "purpose": "EXPLICIT_VALIDATED_CACHE_REUSE_SAME_PROVIDER_AND_BLOCK_HASH"}
        witness.call("eth_chainId", [])
        previous = witness.call("eth_getBlockByNumber", [hex(PREVIOUS), False])
        winner = witness.call("eth_getBlockByNumber", [hex(WINNER), False])
        server = serve(witness)
        env = dict(os.environ)
        env.update(NQC_RMC016_RANK1_BORROWER=manifest["borrower"],
                   NQC_RMC016_RANK1_PREVIOUS_TIMESTAMP=str(int(previous["timestamp"], 16)),
                   NQC_RMC016_RANK1_WINNER_TIMESTAMP=str(int(winner["timestamp"], 16)))
        for variant in scenarios:
            source = root / variant / "source"
            for mode in (["normal", "isolated"] if args.replay else ["normal"]):
                cmd = [str(forge), "test", "--root", str(source), "--use", str(solc), "--offline",
                       "--fork-url", "http://127.0.0.1:" + str(server.server_address[1]),
                       "--fork-block-number", str(PREVIOUS), "--fork-retries", "0", "--no-storage-caching",
                       "--gas-price", "0", "--threads", "1", "--color", "never",
                       "--match-contract", "NqcFundingComparisonForkTest", "-vvvv"]
                if mode == "isolated":
                    cmd.append("--isolate")
                logfile = root / variant / (mode + ".log")
                started = time.monotonic()
                with logfile.open("w") as log:
                    result = subprocess.run(cmd, cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT,
                                            timeout=1800, check=False)
                report["runs"].append({"scenario": variant, "mode": mode, "command": cmd,
                    "exit_code": result.returncode, "elapsed_seconds": time.monotonic() - started,
                    "log_sha256": sha(logfile.read_bytes())})
                if result.returncode:
                    raise RuntimeError("fork failed: " + variant + "/" + mode)
        report["status"] = "FUNDING_SCENARIOS_PASSED_NOT_ECONOMIC_ADMISSION"
    except Exception as error:
        report.update(status="FAILED", failure=str(error))
    finally:
        if server:
            server.shutdown()
            server.server_close()
        report.update(finished_at=now(), upstream_requests=witness.count if witness else 0,
                      rpc_failure=witness.failed if witness else None)
        if not args.replay and witness:
            previous_raw = (root / "seed-upstream.jsonl").read_bytes() if args.seed else b""
            upstream = root / "rpc/upstream.jsonl"
            combined = previous_raw + (upstream.read_bytes() if upstream.exists() else b"")
            (root / "combined-upstream.jsonl").write_bytes(combined)
            report["combined_witness_sha256"] = sha(combined)
        if args.replay:
            report["replay_witness_sha256"] = sha(Path(args.replay).read_bytes())
        (root / "report.json").write_text(canonical(report) + "\n")
    print(canonical(report), flush=True)
    return 1 if report["status"] == "FAILED" else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ["out", "inputs", "solc", "forge"]:
        parser.add_argument("--" + arg, required=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--replay")
    group.add_argument("--seed")
    parser.add_argument("--scenarios", nargs="+", choices=sorted(SCENARIO_SHAS))
    raise SystemExit(run(parser.parse_args()))
