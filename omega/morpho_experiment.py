"""Offline H25 research checkpoint. Never admits a fork, trade or gas payment.

The retained partial capture is immutable. New evidence needs a separately
reviewed pin and verifier; resealing transport hashes cannot upgrade this report.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path

from integrity import canonical, digest, read_regular, strict_json

HERE = Path(__file__).resolve().parent
CAPTURE_SHA256 = "223ec00e267aad6b0bfe17a00b6b1b55f75f641d61150d4c1f5a31269f402303"
TX = "0x6313fb267755f3cfa48214bf74309505984306129ee09a558efe4801006dcbba"
WINNER = "0xf143f9988199037938e4dff57aaf24301a4c26770aefc0ec64774954cbf2dbe4"
PARENT = "0x42cf44b75185587327a1aa8fc859cc5f49a639e7256547511430d6068b6f09ab"
PRECEDING = "0xa5fb6c8b75e2d8f68542c4fd49a0fcc60c679bfb5db2269d899f07742509af50"
MORPHO = "0xbbbbbbbbbb9cc5e90e3b3af64bdaf62c37eeffcb"
POOL = "0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2"
WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
BORROWER = "0x7a0575018b57cb64434fcd794f4f0c624fd0fbd3"
LIQUIDATOR = "0x9e3e25dcc3ed4a97e6fdcb166280a248d8c42219"
SLOT = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
PRINCIPAL = 10684013854557827871
COLLATERAL = 10780169979248848321
LIQUIDATION_TOPIC = "0xe413a321e8681d831f4dbccbca790d2952b56f977908e45be37335533e005286"
PROVIDERS = {"blastapi": "https://eth-mainnet.public.blastapi.io",
             "mevblocker": "https://rpc.mevblocker.io"}
TAG = {"blockHash": PARENT, "requireCanonical": True}
CALLS = {
    "chain": (1, "eth_chainId", []),
    "winner": (2, "eth_getBlockByHash", [WINNER, False]),
    "parent": (3, "eth_getBlockByHash", [PARENT, False]),
    "transaction": (4, "eth_getTransactionByHash", [TX]),
    "receipt": (5, "eth_getTransactionReceipt", [TX]),
    "morpho-code": (6, "eth_getCode", [MORPHO, TAG]),
    "pool-code": (7, "eth_getCode", [POOL, TAG]),
    "weth-code": (8, "eth_getCode", [WETH, TAG]),
    "pool-implementation": (9, "eth_getStorageAt", [POOL, SLOT, TAG]),
}
COMMON = tuple(CALLS)[:7]
COMPLETED = frozenset(f"{p}-{label}" for p in PROVIDERS for label in COMMON) | {"blastapi-weth-code"}
INCOMPLETE = {"blastapi-pool-implementation-request.json": "pool-implementation",
              "mevblocker-weth-code-request.json": "weth-code"}
CODE_SHA256 = {
    "morpho-code": "fd5aa16eea01735e0e33e51e913a27f7d5ed998adc0cec2bf1f9ea368d9e1bdf",
    "pool-code": "bf8a408a1f5440c167d91fa2d972deb23bb4d809e8dd089009885ec88a826f88",
    "weth-code": "5566bf50796faf93c9b6f6adacd3b32c70bfe16b48ffc59db6cd144cbdc89739",
}
SOURCE_LAYOUT = {
    "morpho_liquidation_probe.sol": "src/morpho_liquidation_probe.sol",
    "morpho_liquidation_test.sol": "test/morpho_liquidation_test.sol",
    # Abstract, compile-only harness: deliberately outside Forge's test directory.
    "morpho_liquidation_fork.sol": "src/morpho_liquidation_fork.sol",
}
CONFIG = ('[profile.default]\nsrc="src"\ntest="test"\nevm_version="paris"\n'
          'optimizer=true\noptimizer_runs=200\nvia_ir=true\n[fuzz]\nruns=256\n')


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def expected_request(label: str) -> dict:
    identifier, method, params = CALLS[label]
    return {"jsonrpc": "2.0", "id": identifier, "method": method, "params": params}


def _validate_capture(data: dict) -> dict:
    """Semantic checks after the public entry point's immutable byte pin."""
    require(set(data) == {"schema", "entries", "incomplete_requests", "acquisition_status"}, "capture_fields")
    require(data["schema"] == "nqc.omega.h25.partial-capture.v1", "capture_schema")
    require(data["acquisition_status"] == "BLOCKED_BY_NETWORK_POLICY", "capture_scope")
    require(set(data["entries"]) == COMPLETED, "completed_inventory")
    require(set(data["incomplete_requests"]) == set(INCOMPLETE), "incomplete_inventory")
    for name, label in INCOMPLETE.items():
        require(canonical(strict_json(data["incomplete_requests"][name].encode())) == canonical(expected_request(label)), "incomplete_request")
    results = {}
    for name, entry in data["entries"].items():
        provider, label = name.split("-", 1)
        require(set(entry) == {"request", "response", "metadata"}, "entry_fields")
        raw_request, raw_response = entry["request"].encode(), entry["response"].encode()
        request, response, meta = [strict_json(entry[k].encode()) for k in ("request", "response", "metadata")]
        require(canonical(request) == canonical(expected_request(label)), "request_identity")
        require(set(meta) == {"url", "retrieved_at", "http_status", "returncode", "stderr", "request_sha256", "response_sha256"}, "metadata_fields")
        require(meta["url"] == PROVIDERS[provider], "provider_identity")
        require(meta["http_status"] == "200" and type(meta["returncode"]) is int and meta["returncode"] == 0 and meta["stderr"] == "", "transport_failed")
        require(meta["request_sha256"] == digest(raw_request) and meta["response_sha256"] == digest(raw_response), "transport_digest")
        stamp = datetime.fromisoformat(meta["retrieved_at"].replace("Z", "+00:00"))
        require(stamp.tzinfo is not None and stamp.date().isoformat() == "2026-10-24", "capture_time")
        require(set(response) == {"id", "jsonrpc", "result"} and response["jsonrpc"] == "2.0"
                and type(response["id"]) is int and response["id"] == CALLS[label][0]
                and response["result"] is not None, "response_identity")
        results[name] = response["result"]
    for label in COMMON:
        require(canonical(results["blastapi-"+label]) == canonical(results["mevblocker-"+label]), "provider_disagreement")
    r = {label: results["blastapi-"+label] for label in (*COMMON, "weth-code")}
    require(r["chain"] == "0x1", "wrong_chain")
    winner, parent, transaction, receipt = [r[k] for k in ("winner", "parent", "transaction", "receipt")]
    require((winner["hash"], winner["number"], winner["parentHash"], winner["timestamp"])
            == (WINNER, "0x18bc880", PARENT, "0x6aa0fdbf"), "winner_anchor")
    require((parent["hash"], parent["number"], parent["timestamp"])
            == (PARENT, "0x18bc87f", "0x6aa0fdb3"), "parent_anchor")
    require(winner["transactions"][:2] == [PRECEDING, TX] and winner["transactions"].count(TX) == 1, "transaction_order")
    for item in (transaction, receipt):
        require((item["blockHash"], item["blockNumber"], item["transactionIndex"])
                == (WINNER, "0x18bc880", "0x1"), "transaction_anchor")
    require(transaction["hash"] == receipt["transactionHash"] == TX and receipt["status"] == "0x1", "receipt_identity")
    require(transaction["from"] == receipt["from"] and transaction["to"] == receipt["to"] == LIQUIDATOR, "receipt_parties")
    logs = receipt["logs"]
    require(len(logs) == 17, "receipt_log_count")
    for index, log in enumerate(logs, 7):
        require((log["blockHash"], log["blockNumber"], log["transactionHash"], log["transactionIndex"], log["logIndex"])
                == (WINNER, "0x18bc880", TX, "0x1", hex(index)) and log["removed"] is False, "log_anchor")
    legs = [log for log in logs if log["address"] == POOL and log["topics"][0] == LIQUIDATION_TOPIC]
    require(len(legs) == 1, "liquidation_cardinality")
    topic_address = lambda address: "0x" + "0"*24 + address[2:]
    require(legs[0]["topics"] == [LIQUIDATION_TOPIC, topic_address(WETH), topic_address(WETH), topic_address(BORROWER)], "liquidation_parties")
    expected = "0x" + f"{PRINCIPAL:064x}{COLLATERAL:064x}" + "0"*24 + LIQUIDATOR[2:] + "0"*64
    require(legs[0]["data"] == expected, "liquidation_amounts")
    for label, expected_sha in CODE_SHA256.items():
        require(r[label].startswith("0x") and digest(bytes.fromhex(r[label][2:])) == expected_sha, "runtime_digest")
    return {"schema": "nqc.omega.h25.offline-checkpoint.v1", "decision": "NO-GO",
            "status": "PARTIAL_CAPTURE_VERIFIED_FORK_PENDING", "capture_sha256": CAPTURE_SHA256,
            "completed_rpc_captures": 15, "two_provider_categories": list(COMMON),
            "historical_transaction": TX, "transaction_index": 1,
            "preceding_transaction": PRECEDING, "receipt_logs": len(logs),
            "historical_principal_wei": str(PRINCIPAL), "historical_collateral_wei": str(COLLATERAL),
            "missing": ["mevblocker-weth-code", "both-pool-implementation", "both-implementation-code", "both-preceding-transaction"],
            "historical_fork_executed": False, "receipt_replay_verified": False,
            "aave_implementation_pinned": False, "receipt_trie_proof_verified": False,
            "gas_provider": "Titan", "operator_gas_budget_wei": "0", "own_gas_fallback": False,
            "titan_execution_coverage_proven": False, "all_in_profit_proven": False,
            "signing_authorized": False, "broadcast_authorized": False,
            "spending_authorized": False, "phase_advance_authorized": False}


def verify_partial_capture(path: Path = HERE / "evidence/h25-morpho-partial.json") -> dict:
    raw = read_regular(path)
    require(digest(raw) == CAPTURE_SHA256, "capture_pin_mismatch")
    report = _validate_capture(strict_json(raw))
    report["report_commitment_sha256"] = digest(canonical(report))
    return report


def prepare_offline(destination: Path) -> dict:
    """Create a new local build copy; no tool execution, RPC or source edits."""
    report = verify_partial_capture()
    destination = Path(destination).absolute()
    root = HERE.parent
    require(not any(p.is_symlink() for p in (destination, *destination.parents)), "destination_symlink")
    destination = destination.resolve()
    require(not destination.is_relative_to(root) and not root.is_relative_to(destination), "destination_overlaps_repository")
    require(not destination.exists(), "destination_exists")
    files = {target: read_regular(HERE/source) for source, target in SOURCE_LAYOUT.items()}
    files["foundry.toml"] = CONFIG.encode()
    destination.mkdir(parents=True, exist_ok=False)
    for name, raw in files.items():
        target = destination / name
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(raw)
    manifest = {"schema": "nqc.omega.h25.offline-build.v1", "capture_report": report,
                "files_sha256": {name: digest(raw) for name, raw in files.items()},
                "historical_harness": "ABSTRACT_COMPILE_ONLY_MISSING_REVIEWED_IMPLEMENTATION_PINS",
                "executed": False, "network_used": False}
    (destination/"manifest.json").write_bytes(canonical(manifest))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-offline", type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare_offline(args.prepare_offline) if args.prepare_offline else verify_partial_capture(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
