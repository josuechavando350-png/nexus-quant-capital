#!/usr/bin/env python3
"""Run pinned historical tests in a fresh directory, through a retained RPC witness."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from rpc_witness import HASHES, PREVIOUS, WINNER, PROVIDERS, Witness, canonical, now, serve, sha

SOLC_SHA = "fb03a29a517452b9f12bcf459ef37d0a543765bb3bbc911e70a87d6a37c30d5f"
FORGE_SHA = "4f77da0810de94325734855d0ad58d70640aa8a5b2a837608ddf8c26da34355c"
TEST_PATH = "test/NqcRmc016RankOneSelfFinancingFork.t.sol"
TEST_SHA = "dd7e15646a3dc45e826fb2fc572fcb276e995045b984323faff3b119a45538c2"
PATCHED_TEST_SHA = "31ebec2fd2d1cc084bd1f1f781ffc97705a50fe65b61a2d5e849ead30f1b6b5b"


def checksum_overlay(source):
    """Change one case character in a fresh copy; the address value is identical."""
    path = source / TEST_PATH
    raw = path.read_bytes()
    old = b"0x87870Bca3F3fD6335C3F4ce8392D69350B4fa4E2"
    new = b"0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2"
    if sha(raw) != TEST_SHA or raw.count(old) != 1 or int(old, 16) != int(new, 16):
        raise ValueError("checksum overlay preimage differs")
    patched = raw.replace(old, new)
    if sha(patched) != PATCHED_TEST_SHA:
        raise ValueError("checksum overlay postimage differs")
    path.write_bytes(patched)
    return {"path": TEST_PATH, "before_sha256": TEST_SHA, "after_sha256": PATCHED_TEST_SHA,
            "changed_bytes": 1, "address_value_changed": False,
            "scope": "FRESH_BUILD_COPY_ONLY"}


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
    overlay = checksum_overlay(source)
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
    witness = Witness(root / "rpc", replay=args.replay, provider=args.provider,
                      interval=2.2 if args.provider == "nodies" else 1.1)
    report = {"schema": "nqc-rank1-new-fork-v1", "started_at": now(),
              "mode": "OFFLINE_REPLAY" if args.replay else "NEW_RPC_ACQUISITION",
              "provider": args.provider, "endpoint": PROVIDERS[args.provider],
              "source_manifest_sha256": sha(manifest_raw),
              "compatibility_overlay": overlay,
              "simulated_transaction_gas_price_wei": 0,
              "gas_price_scope": "EXPLICIT_TEST_PARAMETER_NOT_A_COST_ESTIMATE",
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
        build_command = [str(forge), "build", "--root", str(source), "--use", str(solc), "--offline"]
        with (root / "build.log").open("w") as log:
            build = subprocess.run(build_command, cwd=source, stdout=log,
                                   stderr=subprocess.STDOUT, timeout=180, check=False)
        report["build"] = {"command": build_command, "exit_code": build.returncode,
                           "log_sha256": sha((root / "build.log").read_bytes())}
        if build.returncode:
            raise RuntimeError("offline compilation failed before RPC acquisition")
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
                   "--no-storage-caching", "--gas-price", "0", "--threads", "1", "--color", "never",
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
    parser.add_argument("--provider", choices=sorted(PROVIDERS), default="drpc")
    raise SystemExit(run(parser.parse_args()))
