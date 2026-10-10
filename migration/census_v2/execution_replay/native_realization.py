"""Additional offline-only native realization tests over the pinned bid scenario."""
import argparse
import json
import os
from pathlib import Path
import subprocess
from funding_scenarios import apply_scenario, SCENARIO_SHAS
from rpc_witness import Witness, serve, canonical, sha, now, PREVIOUS, WINNER
from run_fork import checksum_overlay, TEST_PATH, FORGE_SHA, SOLC_SHA
from run_comparison import INPUTS_SHA

NATIVE_SOURCE_SHA = "70598c5eef11034d1813be1304aac6c60808e18cf49d17df4e9cb4110b1b1d5b"
WITNESS_SHA = "c22600f671c009c53dd94ee8a1c546aaca40b017119c8c69414a60cefcec305f"
NATIVE_TEST = '''

/// Research operator harness only; no production authorization or gas funding.
contract NqcNativeRealizationForkTest is NqcFundingComparisonForkTest {
    receive() external payable {
        require(msg.sender == WETH, "NATIVE_REALIZATION_ONLY_WETH");
    }

    function settleToNative(NqcFlashFundingExecutor.FlashExecutionPlan calldata p, bytes calldata payload)
        external returns (uint256 output)
    {
        require(msg.sender == address(this), "HARNESS_SELF_CALL_ONLY");
        uint256 wethBefore = IERC20FlashMinimal(WETH).balanceOf(address(this));
        uint256 nativeBefore = address(this).balance;
        output = flashExecutor.execute(p, payload);
        require(IERC20FlashMinimal(WETH).balanceOf(address(this)) == wethBefore + output,
                "FRESH_OUTPUT_NOT_RECEIVED");
        IWethSettlementScenario(WETH).withdraw(output);
        require(IERC20FlashMinimal(WETH).balanceOf(address(this)) == wethBefore,
                "EXISTING_OPERATOR_WETH_SPENT");
        require(address(this).balance == nativeBefore + output, "NATIVE_REALIZATION_DELTA");
    }

    function testAtomicNativeRealizationPreservesPriorInventory() public {
        _advanceClockOnly();
        bytes memory payload = hex"163703";
        NqcFlashFundingExecutor.FlashExecutionPlan memory p = _plan(payload, _fee(REPAY_PRINCIPAL), 1);
        uint256 wethBefore = IERC20FlashMinimal(WETH).balanceOf(address(this));
        uint256 nativeBefore = address(this).balance;
        uint256 recipientBefore = HISTORICAL_FEE_RECIPIENT.balance;
        bytes memory encoded = abi.encodeWithSelector(this.settleToNative.selector, p, payload);
        uint256 zeroBytes;
        for (uint256 i; i < encoded.length; ++i) if (encoded[i] == 0) ++zeroBytes;
        uint256 gasBefore = gasleft();
        uint256 output = this.settleToNative(p, payload);
        uint256 measured = gasBefore - gasleft();
        require(output == 240390311727552, "NATIVE_OUTPUT_DIFFERS_FROM_PAIRED_FORK");
        require(address(this).balance == nativeBefore + output, "OPERATOR_NATIVE_NOT_CREDITED");
        require(IERC20FlashMinimal(WETH).balanceOf(address(this)) == wethBefore, "PRIOR_WETH_DRIFT");
        require(HISTORICAL_FEE_RECIPIENT.balance == recipientBefore + HISTORICAL_PAYMENT, "ATOMIC_BID_NOT_PAID");
        require(IERC20FlashMinimal(WETH).balanceOf(address(strategy)) == 0, "STRATEGY_REMAINDER");
        require(IERC20FlashMinimal(WETH).balanceOf(address(flashExecutor)) == 0, "EXECUTOR_REMAINDER");
        emit log_named_uint("NQC_NATIVE_REALIZED_WEI", output);
        emit log_named_uint("NQC_NATIVE_SETTLEMENT_CALL_GAS", measured);
        emit log_named_uint("NQC_NATIVE_CALLDATA_BYTES", encoded.length);
        emit log_named_uint("NQC_NATIVE_ZERO_BYTES", zeroBytes);
        emit log_named_uint("NQC_NATIVE_NONZERO_BYTES", encoded.length - zeroBytes);
        emit log_named_uint("NQC_NATIVE_INTRINSIC_4_16", 21000 + 4 * zeroBytes + 16 * (encoded.length - zeroBytes));
    }

    function testNativeRealizationRevertPreservesAllBalances() public {
        _advanceClockOnly();
        bytes memory payload = hex"163704";
        NqcFlashFundingExecutor.FlashExecutionPlan memory p = _plan(payload, _fee(REPAY_PRINCIPAL), type(uint96).max);
        uint256 wethBefore = IERC20FlashMinimal(WETH).balanceOf(address(this));
        uint256 nativeBefore = address(this).balance;
        uint256 recipientBefore = HISTORICAL_FEE_RECIPIENT.balance;
        uint256 strategyNativeBefore = address(strategy).balance;
        uint256 lenderBefore = IERC20FlashMinimal(WETH).balanceOf(BALANCER);
        uint256 hfBefore = _hf();
        (bool ok,) = address(this).call(abi.encodeWithSelector(this.settleToNative.selector, p, payload));
        require(!ok, "IMPOSSIBLE_NATIVE_OUTPUT_ACCEPTED");
        require(address(this).balance == nativeBefore, "REVERT_NATIVE_INVENTORY_DRIFT");
        require(IERC20FlashMinimal(WETH).balanceOf(address(this)) == wethBefore, "REVERT_WETH_INVENTORY_DRIFT");
        require(HISTORICAL_FEE_RECIPIENT.balance == recipientBefore, "REVERT_BID_NOT_ROLLED_BACK");
        require(address(strategy).balance == strategyNativeBefore, "REVERT_STRATEGY_NATIVE_DRIFT");
        require(IERC20FlashMinimal(WETH).balanceOf(BALANCER) == lenderBefore, "REVERT_LENDER_DRIFT");
        require(IERC20FlashMinimal(WETH).balanceOf(address(strategy)) == 0, "REVERT_STRATEGY_REMAINDER");
        require(IERC20FlashMinimal(WETH).balanceOf(address(flashExecutor)) == 0, "REVERT_EXECUTOR_REMAINDER");
        require(_hf() == hfBefore, "REVERT_BORROWER_DRIFT");
        require(!flashExecutor.consumedExecutionIdentity(p.executionIdentityHash), "REVERT_IDENTITY_CONSUMED");
    }
}
'''


def run(args):
    root, inputs = Path(args.out), Path(args.inputs)
    root.mkdir(parents=True, exist_ok=False)
    report = {"schema": "nqc-native-realization-v1", "started_at": now(),
        "parent_commit": "d6fcf7206b82e8e78a6104a89acb699a3c9aa0ad",
        "mode": "OFFLINE_ONLY", "runs": [], "status": "FAILED",
        "original_executor_modified": False, "production_operator_implemented": False,
        "gas_financing_proven": False, "complete_profit_wei": None, "census_closed": False,
        "independent_certification": False, "live_transaction_sent": False,
        "producer_sources": {n: sha((Path(__file__).parent / n).read_bytes()) for n in
            ["native_realization.py", "funding_scenarios.py", "run_comparison.py", "run_fork.py", "rpc_witness.py"]}}
    server = witness = None
    try:
        manifest_raw = (inputs / "sources.json").read_bytes()
        if sha(manifest_raw) != INPUTS_SHA or sha(Path(args.replay).read_bytes()) != WITNESS_SHA:
            raise ValueError("historical inputs differ")
        if sha(Path(args.forge).read_bytes()) != FORGE_SHA or sha(Path(args.solc).read_bytes()) != SOLC_SHA:
            raise ValueError("toolchain differs")
        manifest = json.loads(manifest_raw)
        source = root / "source"
        for name, pin in manifest["files"].items():
            raw = (inputs / name).read_bytes()
            if sha(raw) != pin["sha256"]:
                raise ValueError("original source differs")
            dst = source / name; dst.parent.mkdir(parents=True, exist_ok=True); dst.write_bytes(raw)
        report["checksum_overlay"] = checksum_overlay(source)
        report["funding_overlay"] = apply_scenario(source, "balancer_bid", SCENARIO_SHAS["balancer_bid"])
        test = source / TEST_PATH
        modified = test.read_bytes() + NATIVE_TEST.encode()
        if sha(modified) != NATIVE_SOURCE_SHA:
            raise ValueError("native scenario postimage differs")
        test.write_bytes(modified)
        report.update(native_source_sha256=sha(modified), witness_sha256=WITNESS_SHA,
                      forge_sha256=FORGE_SHA, solc_sha256=SOLC_SHA, input_manifest_sha256=INPUTS_SHA)
        for mode in ["build", "normal", "isolated"]:
            cmd = [args.forge, "build" if mode == "build" else "test", "--root", str(source), "--use", args.solc, "--offline"]
            env = dict(os.environ)
            if mode != "build":
                if witness is None:
                    witness = Witness(root / "rpc", replay=args.replay, provider="nodies")
                    server = serve(witness)
                previous = witness.call("eth_getBlockByNumber", [hex(PREVIOUS), False])
                winner = witness.call("eth_getBlockByNumber", [hex(WINNER), False])
                env.update(NQC_RMC016_RANK1_BORROWER=manifest["borrower"],
                           NQC_RMC016_RANK1_PREVIOUS_TIMESTAMP=str(int(previous["timestamp"], 16)),
                           NQC_RMC016_RANK1_WINNER_TIMESTAMP=str(int(winner["timestamp"], 16)))
                cmd += ["--fork-url", "http://127.0.0.1:" + str(server.server_address[1]),
                    "--fork-block-number", str(PREVIOUS), "--fork-retries", "0", "--no-storage-caching",
                    "--gas-price", "0", "--threads", "1", "--color", "never", "--match-contract", "NqcNativeRealizationForkTest", "-vvvv"]
                if mode == "isolated": cmd += ["--isolate"]
            log = root / (mode + ".log")
            with log.open("w") as f:
                result = subprocess.run(cmd, cwd=source, env=env, stdout=f, stderr=subprocess.STDOUT, timeout=180, check=False)
            report["runs"].append({"mode": mode, "command": cmd, "exit_code": result.returncode, "log_sha256": sha(log.read_bytes())})
            if result.returncode: raise RuntimeError("failed: " + mode)
        report["status"] = "NATIVE_REALIZATION_PASSED_NOT_ECONOMIC_ADMISSION"
    except Exception as error:
        report["failure"] = str(error)
    finally:
        if server: server.shutdown(); server.server_close()
        report.update(finished_at=now(), upstream_requests=witness.count if witness else 0)
        (root / "report.json").write_text(canonical(report) + "\n")
    print(canonical(report), flush=True)
    return int(report["status"] == "FAILED")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["out", "inputs", "forge", "solc", "replay"]: parser.add_argument("--" + name, required=True)
    raise SystemExit(run(parser.parse_args()))
