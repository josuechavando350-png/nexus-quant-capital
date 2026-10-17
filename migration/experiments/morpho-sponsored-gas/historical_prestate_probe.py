"""Fail-closed, canonical-block read-only probe for a real Morpho market.

All RPC calls are eth_call with EIP-1898 blockHash + requireCanonical.
No fallback to a mutable height/latest. No signing, gas, transactions, or profits.
Even a PASS only establishes the *parent-block* state; original tx index 226
means 226 prior transactions could have changed the exact pretransaction state.
"""
from __future__ import annotations

import json
import urllib.error
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

FATAL = "BLOCKED_NO_EVIDENCE"
PINNED_TX = "0x0a2f442acfb350d6d93002038b454ead40ffcf28a777b291cbaec1746d8aa2f1"
MORPHO = "0xbbbbbbbbbb9cc5e90e3b3af64bdaf62c37eeffcb"
MARKET_FIELDS = ("loan_token", "collateral_token", "oracle", "irm", "lltv")
ADDRESS_FIELDS = MARKET_FIELDS[:-1]


def canonical_hex(value: object, width: int, field: str) -> str:
    if not isinstance(value, str) or len(value) != 2 + 2*width or not value.startswith("0x"):
        raise ValueError(f"invalid {field}")
    try:
        int(value[2:], 16)
    except ValueError as exc:
        raise ValueError(f"invalid hexadecimal {field}") from exc
    return value.lower()


def bounded_uint(value: object, field: str) -> int:
    if isinstance(value, bool) or not (
        type(value) is int or (isinstance(value, str) and value.isascii() and value.isdecimal())
    ):
        raise ValueError(f"invalid integer {field}")
    n = int(value)
    if not 0 <= n < 2**256:
        raise ValueError(f"out of range {field}")
    return n


def keccak256(value: bytes) -> bytes:
    # OpenSSL KECCAK-256 (not NIST SHA3-256). Intentionally no insecure fallback.
    try:
        result = subprocess.run(
            ["openssl", "dgst", "-keccak-256", "-binary"],
            input=value, capture_output=True, check=True, timeout=5,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("OpenSSL with KECCAK-256 is required") from exc
    if len(result.stdout) != 32:
        raise RuntimeError("OpenSSL KECCAK-256 output invalid")
    return result.stdout


def market_id(record: dict) -> str:
    words = [int(canonical_hex(record[x], 20, x), 16).to_bytes(32, "big")
             for x in ADDRESS_FIELDS]
    words.append(bounded_uint(record["lltv"], "lltv").to_bytes(32, "big"))
    return "0x" + keccak256(b"".join(words)).hex()


def selector(signature: str) -> str:
    return keccak256(signature.encode())[:4].hex()


def words(data: object, expected: int, label: str) -> list[int]:
    if not isinstance(data, str) or not data.startswith("0x") or len(data) != 2 + 64*expected:
        raise ValueError(f"{label} ABI output is missing or malformed")
    try:
        return [int(data[2+64*i:2+64*(i+1)], 16) for i in range(expected)]
    except ValueError as exc:
        raise ValueError(f"{label} invalid ABI response") from exc


def check_fixture(record: dict) -> None:
    if record.get("scope") != "HISTORICAL_EXTERNAL_WINNER_PARENT_BLOCK_ONLY":
        raise ValueError("noncanonical fixture scope")
    if record.get("chain_id") != 1 or record.get("transaction_block") != 25402186:
        raise ValueError("wrong chain or historical block")
    if record.get("transaction_index") != 226 or record.get("parent_block") != 25402185:
        raise ValueError("wrong parent-block boundary")
    if canonical_hex(record.get("parent_block_hash"), 32, "parent_block_hash") != "0x976caf9ddb8d59e24460f7aabe760d96e2dc96f56b3ff0d89d6c1d7359dce670":
        raise ValueError("untrusted parent block hash")
    if canonical_hex(record.get("transaction_hash"), 32, "transaction_hash") != PINNED_TX:
        raise ValueError("untrusted historical transaction hash")
    if canonical_hex(record.get("morpho_contract"), 20, "morpho_contract") != MORPHO:
        raise ValueError("Morpho contract identity changed")
    if record.get("callback_data") != "0x":
        raise ValueError("original historical callback did not exist")
    if record.get("market_id") != market_id(record):
        raise ValueError("market parameters do not hash to the expected market id")
    canonical_hex(record["borrower"], 20, "borrower")
    if bounded_uint(record["repaid_shares"], "repaid_shares") == 0:
        raise ValueError("zero repaid shares")


def calldata(signature: str, *arguments: int) -> str:
    return "0x" + selector(signature) + "".join(n.to_bytes(32, "big").hex() for n in arguments)


def build_calls(record: dict) -> list[dict]:
    check_fixture(record)
    market_key = int(record["market_id"], 16)
    borrower = int(record["borrower"], 16)
    block = {"blockHash": record["parent_block_hash"], "requireCanonical": True}
    return [{"jsonrpc": "2.0", "id": idx, "method": "eth_call", "params": [
        {"to": record["morpho_contract"], "data": calldata(signature, *args)}, block
    ]} for idx,(signature,args) in enumerate((
        ("idToMarketParams(bytes32)", (market_key,)),
        ("market(bytes32)", (market_key,)),
        ("position(bytes32,address)", (market_key, borrower)),
    ), 1)]


def parse_response(record: dict, responses: list[dict]) -> dict:
    if len(responses) != 3:
        raise ValueError("three independent archive calls required")
    ordered = []
    for idx, response in enumerate(responses, 1):
        if not isinstance(response, dict) or response.get("id") != idx or "error" in response:
            raise ValueError(f"eth_call #{idx} failed or mismatched response id")
        ordered.append(response.get("result"))
    mp, market, position = (words(ordered[0], 5, "market params"),
                            words(ordered[1], 6, "market"),
                            words(ordered[2], 3, "position"))
    expected = [int(record[x], 16) for x in ADDRESS_FIELDS] + [int(record["lltv"])]
    if mp != expected:
        raise ValueError("blockHash-pinned Morpho market configuration mismatch")
    if not market[4] or not position[1] or not position[2]:
        raise ValueError("parent state shows no active market/debt/collateral")
    return {
        "status": "PARENT_STATE_ONLY_NOT_PRETRANSACTION",
        "market_id": record["market_id"],
        "block_hash": record["parent_block_hash"],
        "market_total_borrow_assets_raw": str(market[2]),
        "market_total_borrow_shares_raw": str(market[3]),
        "borrower_borrow_shares_raw": str(position[1]),
        "borrower_collateral_raw": str(position[2]),
        "original_tx_index": record["transaction_index"],
        "blockers": ["NOT_EXACT_PRETX_STATE_226_PRIOR_TXS_UNREPLAYED",
                     "NO_DEX_EXECUTION", "NO_BUILDER_SPONSOR_PROOF",
                     "NO_NQC_CAPTURE_OR_PROFIT_PROOF"],
        "certified": False,
        "live_executable": False,
    }


def run_probe(fixture: Path, rpc_url: str | None) -> tuple[int, dict]:
    record = json.loads(fixture.read_text(encoding="utf-8"))
    calls = build_calls(record)
    if not rpc_url:
        return 2, {"status": "BLOCKED_NO_ARCHIVE_RPC", "market_id": record["market_id"],
                   "parent_hash": record["parent_block_hash"], "certified": False}
    responses = []
    for call in calls:
        data = json.dumps(call).encode()
        req = urllib.request.Request(rpc_url, data=data,
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=12) as result:
                responses.append(json.load(result))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            # Never expose a URL that might contain a private RPC token.
            raise RuntimeError("archive RPC unavailable or does not support historical blockHash reads") from exc
    return 2, parse_response(record, responses)  # Never emit certified/PASS from these reads.


def main() -> int:
    try:
        path = Path(sys.argv[1]) if len(sys.argv) >= 2 else (
            Path(__file__).parent / "observations/ethereum_morpho_2026-06-26_market_params.json")
        code, output = run_probe(path, os.getenv("NQC_ARCHIVE_RPC_URL"))
        print(json.dumps(output, indent=2, sort_keys=True))
        return code
    except (ValueError, OSError, RuntimeError, KeyError, TypeError) as exc:
        # Do not echo request URL (may contain an API key).
        print(json.dumps({"status": FATAL, "reason": str(exc)[:150], "certified": False}))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
