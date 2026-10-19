"""Offline JSON-RPC capture adapter. No network, credentials, signing or sending.

Accepts exactly one pinned end-of-block read set. Requests are documentary, not
evidence of canonicality; the independent policy pin and all R5 proof checks
remain mandatory. This does not authenticate Nitro or intermediate tx state.
"""
import json
from pathlib import Path
import sys

R5 = Path(__file__).resolve().parents[2] / "r5-proof-traversal"
R3 = R5.parent / "r3-state-evidence"
sys.path[:0] = [str(R5 / "python"), str(R3 / "src")]
from state_evidence import (Policy, Rejected, require, exact, load_packet, data,
                            quantity, slots, MAX_PACKET)
from proof_traversal import ProofDecoder as R5Decoder
from state_evidence_fast import verify as verify_r5
from object_evidence import verify_object


def encode(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def request_plan(policy):
    require(type(policy) is Policy and type(policy.anchor.chain) is int and
            policy.anchor.chain == 1, "Ethereum policy required; Nitro unsupported")
    require(type(policy.anchor.block_hash) is bytes and len(policy.anchor.block_hash) == 32 and
            type(policy.address) is bytes and len(policy.address) == 20, "request identity")
    block = "0x" + policy.anchor.block_hash.hex()
    address = "0x" + policy.address.hex()
    keys = ["0x" + slot.to_bytes(32, "big").hex() for slot in slots(policy.market_id, policy.borrower).values()]
    pin = {"blockHash": block, "requireCanonical": True}
    return [{"jsonrpc": "2.0", "id": i, "method": method, "params": params}
            for i,method,params in (
                (1, "eth_chainId", []), (2, "eth_getBlockByHash", [block, False]),
                (3, "eth_getCode", [address, pin]), (4, "eth_getProof", [address, keys, pin]))]


def storage_key(value):
    # EIP-1186 quantity and execution-api bytesMax32 representations normalize
    # only the key width. Values, proof bodies, code and header remain untouched.
    try:
        n = quantity(value)
    except Rejected:
        b = data(value)
        require(1 <= len(b) <= 32, "storage key width")
        n = int.from_bytes(b, "big")
    return "0x" + n.to_bytes(32, "big").hex()


def packet_from_wire(raw, policy):
    try:
        return _packet_from_wire(raw, policy)
    except Rejected:
        raise
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, RecursionError) as e:
        raise Rejected("malformed wire capture") from e


def _packet_from_wire(raw, policy):
    w = load_packet(raw)  # 2 MiB, duplicate-key and nonfinite-number rejection.
    exact(w, ("schema", "statePoint", "requests", "responses"))
    require(w["schema"] == "nqc666-rpc-capture-v1" and w["statePoint"] == "end_of_block",
            "unsupported capture/state point")
    expected = request_plan(policy)
    require(type(w["requests"]) is list and len(w["requests"]) == 4, "request coverage")
    # Canonical JSON compares bool/int/float distinctly, unlike Python ==.
    require(encode(w["requests"]) == encode(expected), "request pin/method/order mismatch")
    require(type(w["responses"]) is list and len(w["responses"]) == 4, "response coverage")
    answers = {}
    for response in w["responses"]:
        exact(response, ("jsonrpc", "id", "result"))
        i = response["id"]
        require(response["jsonrpc"] == "2.0" and type(i) is int and i in (1,2,3,4)
                and i not in answers, "response identity/duplicate")
        require(response["result"] is not None, "missing RPC result")
        answers[i] = response["result"]
    require(quantity(answers[1]) == policy.anchor.chain, "chain response mismatch")
    account = answers[4]
    exact(account, ("address", "nonce", "balance", "storageHash", "codeHash", "accountProof", "storageProof"))
    require(type(account["storageProof"]) is list and len(account["storageProof"]) == 9,
            "storage proof coverage")
    rows = []
    for row in account["storageProof"]:
        exact(row, ("key", "value", "proof"))
        rows.append(dict(row, key=storage_key(row["key"])))
    return {"schema": "nqc666-eip1186-v1", "statePoint": "end_of_block",
            "chainId": answers[1], "blockHash": "0x" + policy.anchor.block_hash.hex(),
            "header": answers[2], "code": answers[3], "account": dict(account, storageProof=rows)}


def verify_wire_baseline(raw, policy, now_s):
    # Reference integration: serialize normalized packet, then unchanged R5.
    return verify_r5(encode(packet_from_wire(raw, policy)), policy, now_s)


def verify_wire_object(raw, policy, now_s):
    # Ablation: avoid encode/reparse while retaining the R5 node decoder.
    return verify_object(packet_from_wire(raw, policy), policy, now_s, decoder_type=R5Decoder)


def verify_wire(raw, policy, now_s):
    # Experimental candidate: same object path, equivalent canonical hex parser.
    return verify_object(packet_from_wire(raw, policy), policy, now_s)
