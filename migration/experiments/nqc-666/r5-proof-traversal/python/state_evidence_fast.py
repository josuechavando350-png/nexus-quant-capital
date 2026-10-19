"""R5 verifier: R3 semantics verbatim, packet-local validated-node traversal.

verify/_verify bodies are preserved byte-for-byte from R3. Only ProofDecoder
binding differs. AST/source tests guard that boundary. No live authorization.
"""
from pathlib import Path
import sys
R3 = Path(__file__).resolve().parents[2] / "r3-state-evidence"
sys.path.insert(0, str(R3 / "src"))
import rlp
from eth_hash.auto import keccak
from state_evidence import (Rejected, require, load_packet, exact, quantity, data,
                            LAYOUT, verify_header, uint_bytes, slots, WAD, Facts)
from proof_traversal import ProofDecoder


def verify(raw, policy, now_s, *, shared=True):
    """All checks run on both paths; shared=True only deduplicates node decoding."""
    try:
        return _verify(raw, policy, now_s, shared)
    except Rejected:
        raise
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, RecursionError,
            rlp.DecodingError) as e:
        raise Rejected("malformed evidence") from e


def _verify(raw, policy, now_s, shared):
    p = load_packet(raw)
    exact(p, ("schema", "chainId", "blockHash", "statePoint", "header", "account", "code"))
    a = policy.anchor
    require(type(now_s) is int and type(policy.max_age_s) is int and policy.max_age_s > 0,
            "clock/expiry type")
    require(a.timestamp <= now_s <= a.timestamp + policy.max_age_s, "future/stale evidence")
    require(p["schema"] == "nqc666-eip1186-v1" and p["statePoint"] == "end_of_block",
            "schema/state point")
    require(quantity(p["chainId"]) == a.chain and data(p["blockHash"], 32) == a.block_hash,
            "packet identity")
    require(policy.layout == LAYOUT, "unsupported layout")
    require(type(policy.address) is bytes and len(policy.address) == 20 and any(policy.address),
            "configured account")
    require(type(policy.code_hash) is bytes and len(policy.code_hash) == 32, "configured code hash")
    root = verify_header(p["header"], a)
    account = p["account"]
    exact(account, ("address", "nonce", "balance", "storageHash", "codeHash", "accountProof", "storageProof"))
    require(data(account["address"], 20) == policy.address, "account identity")
    decoder = ProofDecoder(shared)
    leaf = decoder.prove(root, keccak(policy.address), account["accountProof"])
    require(bool(leaf), "account absent")
    acc = rlp.decode(leaf, strict=True)
    require(type(acc) is list and len(acc) == 4, "account RLP schema")
    require(uint_bytes(acc[0]) == quantity(account["nonce"]) and
            uint_bytes(acc[1]) == quantity(account["balance"]), "account metadata")
    require(type(acc[2]) is bytes and len(acc[2]) == 32 and
            type(acc[3]) is bytes and len(acc[3]) == 32, "account roots")
    require(acc[2] == data(account["storageHash"], 32) and
            acc[3] == data(account["codeHash"], 32) == policy.code_hash, "account code/storage identity")
    code = data(p["code"])
    require(0 < len(code) <= 24576 and keccak(code) == policy.code_hash, "runtime code digest/size")
    expected = slots(policy.market_id, policy.borrower)
    require(type(account["storageProof"]) is list and len(account["storageProof"]) == len(expected),
            "storage proof coverage")
    actual = {}
    for row in account["storageProof"]:
        exact(row, ("key", "value", "proof"))
        slot = int.from_bytes(data(row["key"], 32), "big")
        require(slot in expected.values() and slot not in actual, "unexpected/duplicate slot")
        v = decoder.prove(acc[2], keccak(slot.to_bytes(32, "big")), row["proof"])
        value = 0 if not v else uint_bytes(rlp.decode(v, strict=True))
        require(not v or value != 0, "noncanonical stored zero")
        require(value == quantity(row["value"]), "storage value metadata")
        actual[slot] = value
    words = {name: actual[slot] for name, slot in expected.items()}
    for name in ("loan_token", "collateral_token", "oracle", "irm"):
        require(words[name] < 2**160, "address padding")
    require(words["loan_token"] > 0 and words["collateral_token"] > 0 and words["oracle"] > 0,
            "uninitialized market params")
    require(0 < words["lltv"] < WAD, "LLTV range")
    encoded_params = b"".join(words[n].to_bytes(32, "big") for n in
                              ("loan_token", "collateral_token", "oracle", "irm", "lltv"))
    require(keccak(encoded_params) == policy.market_id, "market ID/params mismatch")
    require(words["position"] % 2**128 <= words["borrow"] >> 128, "position shares exceed market")
    require(0 < words["time_fee"] % 2**128 <= a.timestamp and
            words["time_fee"] >> 128 <= WAD // 4, "market time/fee")
    require(words["borrow"] % 2**128 <= words["supply"] % 2**128, "borrow exceeds supply")
    return Facts(a, policy.address, policy.market_id, policy.borrower, policy.code_hash,
                 acc[2], tuple(words.items()), decoder.decoded, decoder.references)
