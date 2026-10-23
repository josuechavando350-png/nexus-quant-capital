#!/usr/bin/env python3
"""Compile exact collateral/fee excerpts with an explicitly synthetic token stub."""
import argparse
import gzip
import json
from pathlib import Path

import aave_runtime_identity as identity
from build_aave_amount_harness import SOURCE_PATH, SOURCE_SHA

NAME = "fixtures/AaveCollateralHarness.sol"
SIGNATURE = "calculate((uint256,uint256,uint256,uint256,uint256,uint8,uint256,uint256))"


def extracted_harness(source):
    original = source["sources"][SOURCE_PATH]["content"]
    identity.check(identity.sha(original.encode()) == SOURCE_SHA, "collateral source identity")

    def segment(start, end):
        identity.check(original.count(start) == 1, "ambiguous excerpt start")
        a = original.index(start)
        return original[a:original.index(end, a)]

    structure = segment("  struct LiquidationCallLocalVars {", "\n\n  /**")
    units = segment("    vars.collateralAssetUnit =", "    vars.debtAssetUnit =")
    consumption = segment("      uint256 scaledCollateralConsumed =", "      // Clear the collateral flag")
    fee = segment("    // Transfer fee to treasury", "    // burn bad debt")
    flag = "reserveFullyConsumed || hasNoCollateralLeft"
    identity.check(original.count("if (" + flag + ")") == 1, "collateral flag condition")
    prefix = identity.PREFIX
    imports = "\n".join(f'import {{{symbol}}} from "{prefix}{path}";' for symbol, path in [
        ("DataTypes", "protocol/libraries/types/DataTypes.sol"),
        ("ReserveConfiguration", "protocol/libraries/configuration/ReserveConfiguration.sol"),
        ("TokenMath", "protocol/libraries/helpers/TokenMath.sol"),
        ("IAToken", "interfaces/IAToken.sol"),
    ])
    harness = '''// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.27;
// GENERATED excerpt harness: post-transfer balance and token calls are synthetic.
''' + imports + '''
contract AaveCollateralHarness {
  using TokenMath for uint256;
  using ReserveConfiguration for DataTypes.ReserveConfigurationMap;
  uint256 private suppliedPostBalance;
  uint256 private capturedAmount;
  uint256 private capturedScaled;
  bool private capturedCall;
''' + structure + '''
  struct Input {
    uint256 index; uint256 scaledBalance; uint256 liquidatorAmount;
    uint256 feeAmount; uint256 price; uint8 decimals;
    uint256 totalCollateralBase; uint256 postLiquidatorScaledBalance;
  }
  function scaledBalanceOf(address) external view returns (uint256) { return suppliedPostBalance; }
  function RESERVE_TREASURY_ADDRESS() external pure returns (address) { return address(0xBEEF); }
  function transferOnLiquidation(address, address, uint256 amount, uint256 scaledAmount, uint256) external {
    capturedCall = true; capturedAmount = amount; capturedScaled = scaledAmount;
  }
  function calculate(Input memory input) external returns (uint256[8] memory) {
    LiquidationCallLocalVars memory vars;
    DataTypes.ExecuteLiquidationCallParams memory params;
    vars.collateralReserveCache.nextLiquidityIndex = input.index;
    vars.collateralReserveCache.reserveConfiguration.data = uint256(input.decimals) << 48;
    vars.collateralReserveCache.aTokenAddress = address(this);
    vars.borrowerScaledCollateralBalance = input.scaledBalance;
    vars.actualCollateralToLiquidate = input.liquidatorAmount;
    vars.liquidationProtocolFeeAmount = input.feeAmount;
    vars.collateralAssetPrice = input.price;
    vars.totalCollateralInBaseCurrency = input.totalCollateralBase;
    suppliedPostBalance = input.postLiquidatorScaledBalance;
    capturedCall = false; capturedAmount = 0; capturedScaled = 0;
''' + units + '''
    bool hasNoCollateralLeft;
''' + consumption + fee + '''
    return [scaledCollateralConsumed, consumedInBaseCurrency,
      reserveFullyConsumed ? 1 : 0, hasNoCollateralLeft ? 1 : 0,
      (''' + flag + ''') ? 1 : 0,
      capturedCall ? 1 : 0, capturedAmount, capturedScaled];
  }
}
'''
    segments = {name: identity.sha(text.encode()) for name, text in [
        ("structure", structure), ("units", units), ("consumption", consumption),
        ("fee_transfer", fee), ("clear_flag_expression", flag),
    ]}
    return harness, segments


def build(compiler, output):
    source = identity.read_json(identity.EVIDENCE / "source.json.gz")
    identity.verify_provenance(source)
    value = identity.compilation_input(source)
    harness, segments = extracted_harness(source)
    value["sources"][NAME] = {"content": harness}
    value["settings"]["outputSelection"] = {NAME: {"AaveCollateralHarness": [
        "evm.deployedBytecode", "evm.methodIdentifiers", "storageLayout"]}}
    raw, stderr = identity.compile_source(compiler, value)
    result = json.loads(raw)
    identity.check(not [e for e in result.get("errors", []) if e.get("severity") == "error"], str(result.get("errors")))
    contract = result["contracts"][NAME]["AaveCollateralHarness"]
    code = contract["evm"]["deployedBytecode"]
    identity.check(not code["linkReferences"] and not code["immutableReferences"], "deployment references")
    layout = contract["storageLayout"]
    slots = set()
    for var in layout["storage"]:
        start = int(var["slot"])
        size = int(layout["types"][var["type"]]["numberOfBytes"])
        slots.update(range(start, start + (size + 31) // 32))
    runtime = bytes.fromhex(code["object"])
    fixture = {
        "schema": "nqc-miner-aave-collateral-harness-v1", "kind": "synthetic_fixture",
        "reference_kind": "byte_exact_excerpts_with_synthetic_post_transfer_token",
        "compiler_sha256": identity.COMPILER_SHA, "compiler_version": identity.COMPILER_VERSION,
        "compiler_input_sha256": identity.sha(identity.encoded(value)),
        "compiler_output_sha256": identity.sha(raw),
        "harness_source_sha256": identity.sha(harness.encode()),
        "runtime_sha256": identity.sha(runtime), "runtime_code": "0x" + runtime.hex(),
        "selector": "0x" + contract["evm"]["methodIdentifiers"][SIGNATURE],
        "storage_layout": layout, "explicit_zero_slots": sorted(slots),
        "source_path": SOURCE_PATH, "source_sha256": SOURCE_SHA,
        "extracted_segments": segments,
        "original_sources": {p: identity.sha(v["content"].encode()) for p, v in source["sources"].items()},
        "post_liquidator_balance_supplied": True, "token_implementation_verified": False,
        "executable_eligibility_verified": False, "activation_allowed": False,
    }
    output.mkdir(parents=True, exist_ok=False)
    (output / "input.json.gz").write_bytes(gzip.compress(identity.encoded(value), mtime=0))
    (output / "output.json.gz").write_bytes(gzip.compress(raw, mtime=0))
    (output / "compiler.stderr").write_bytes(stderr)
    (identity.MODULE / NAME).write_text(harness)
    (identity.MODULE / "fixtures/aave_collateral_harness.json").write_bytes(identity.encoded(fixture))
    print(json.dumps({"runtime_bytes": len(runtime), "runtime_sha256": fixture["runtime_sha256"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.compiler, args.output)
