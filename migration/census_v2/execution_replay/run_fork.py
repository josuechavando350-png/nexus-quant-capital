#!/usr/bin/env python3
"""Run pinned historical tests in a fresh directory, through a retained RPC witness."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from rpc_witness import HASHES, PREVIOUS, WINNER, Witness, canonical, now, serve, sha

SOLC_SHA = "fb03a29a517452b9f12bcf459ef37d0a543765bb3bbc911e70a87d6a37c30d5f"
FORGE_SHA = "4f77da0810de94325734855d0ad58d70640aa8a5b2a837608ddf8c26da34355c"


def run(args):
    root, inputs = Path(args.out), Path(args.inputs)
    root.mkdir(parents=True, exist_ok=False)
    manifest_raw = (inputs / "sources.json").read_bytes()
    manifest = json.loads(manifest_raw)
    source = root / "source"
    source.mkdir()
    for name, pin in manifest["files"].items():
        raw = (inputs / name).read_bytes()
        if sha(raw) != pin["sha256"]:
            raise ValueError("source drift: " + name)
        dst = source / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(raw)
    solc = Path(args.solc)
    if sha(solc.read_bytes()) != SOLC_SHA:
        raise ValueError("compiler digest differs")
    forge = Path(args.forge)
    if sha(forge.read_bytes()) != FORGE_SHA:
        raise ValueError("Foundry binary digest differs")
    forge_version = subprocess.check_output([str(forge), "--version"], text=True)
    if not forge_version.startswith("forge Version: 1.7.1\n"):
        raise ValueError("Foundry version differs")
    (root / "forge-version.txt").write_text(forge_version)
    witness = Witness(root / "rpc", replay=args.replay)
    report = {"schema": "nqc-rank1-new-fork-v1", "started_at": now(),
              "mode": "OFFLINE_REPLAY" if args.replay else "NEW_RPC_ACQUISITION",
              "source_manifest_sha256": sha(manifest_raw),
              "forge_sha256": sha(forge.read_bytes()), "solc_sha256": SOLC_SHA,
              "producer_sources": {n: sha((Path(__file__).parent / n).read_bytes())
                                   for n in ["rpc_witness.py", "run_fork.py"]},
              "original_state_modified": False, "live_transaction_sent": False,
              "original_intrablock_transactions_replayed": False,
              "historical_decision_time_observation_proven": False,
              "capital_admission_changed": False, "census_closed": False,
              "independent_certification": False, "runs": []}
    server = None
    try:
        witness.call("eth_chainId", [])
        previous = witness.call("eth_getBlockByNumber", [hex(PREVIOUS), False])
        winner = witness.call("eth_getBlockByNumber", [hex(WINNER), False])
        report["anchors"] = [{"number": b["number"], "hash": b["hash"],
                              "timestamp": b["timestamp"], "baseFeePerGas": b["baseFeePerGas"]}
                             for b in [previous, winner]]
        server = serve(witness)
        env = dict(os.environ)
        env.update(NQC_RMC016_RANK1_BORROWER=manifest["borrower"],
                   NQC_RMC016_RANK1_PREVIOUS_TIMESTAMP=str(int(previous["timestamp"], 16)),
                   NQC_RMC016_RANK1_WINNER_TIMESTAMP=str(int(winner["timestamp"], 16)))
        modes = ["original"] if not args.replay else ["original", "isolated"]
        for mode in modes:
            cmd = [str(forge), "test", "--root", str(source), "--use", str(solc), "--offline",
                   "--fork-url", "http://127.0.0.1:" + str(server.server_address[1]),
                   "--fork-block-number", str(PREVIOUS), "--fork-retries", "0",
                   "--no-storage-caching", "--threads", "1", "--color", "never",
                   "--match-contract", "NqcRmc016RankOneSelfFinancingForkTest", "-vvvv"]
            if mode == "isolated":
                cmd.append("--isolate")
            started = time.monotonic()
            with (root / (mode + ".log")).open("w") as log:
                result = subprocess.run(cmd, cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT,
                                        timeout=1800, check=False)
            report["runs"].append({"mode": mode, "command": cmd, "exit_code": result.returncode,
                                   "elapsed_seconds": time.monotonic() - started,
                                   "log_sha256": sha((root / (mode + ".log")).read_bytes())})
            if result.returncode:
                raise RuntimeError("forge failed in " + mode)
        report["status"] = "SCOPED_FORK_TESTS_PASSED_NOT_ECONOMIC_ADMISSION"
    except Exception as error:
        report.update(status="FAILED", failure=str(error))
    finally:
        if server:
            server.shutdown()
            server.server_close()
        report.update(finished_at=now(), upstream_requests=witness.count, rpc_failure=witness.failed)
        (root / "report.json").write_text(canonical(report) + "\n")
    print(canonical(report), flush=True)
    return 0 if report["status"] != "FAILED" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["out", "inputs", "solc", "forge"]:
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--replay")
    raise SystemExit(run(parser.parse_args()))
