#!/usr/bin/env python3
"""Bind the two retained full headers to their historical Keccak/RLP hashes.

This authenticates header fields against existing anchors, not state responses,
trace inclusion, recipient ownership, economic agreements, or finality afresh.
Header order: Ethereum execution-specs, Header through requests_hash.
"""
import argparse
import gzip
import json
from pathlib import Path
import sys
import tempfile
sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "ci/nqc-census"))
from typed_observation_vectors import keccak256, rlp_list, rlp_uint
from rpc_witness import HASHES, PREVIOUS, WINNER, Witness, canonical, sha

FIELDS = [
    ("parentHash", 32), ("sha3Uncles", 32), ("miner", 20), ("stateRoot", 32),
    ("transactionsRoot", 32), ("receiptsRoot", 32), ("logsBloom", 256),
    ("difficulty", None), ("number", None), ("gasLimit", None), ("gasUsed", None),
    ("timestamp", None), ("extraData", -1), ("mixHash", 32), ("nonce", 8),
    ("baseFeePerGas", None), ("withdrawalsRoot", 32), ("blobGasUsed", None),
    ("excessBlobGas", None), ("parentBeaconBlockRoot", 32), ("requestsHash", 32),
]
WINNER_TX = "0x6313fb267755f3cfa48214bf74309505984306129ee09a558efe4801006dcbba"


def verify_header(header):
    values = []
    for name, length in FIELDS:
        value = header[name]
        if not isinstance(value, str) or not value.startswith("0x"):
            raise ValueError("header hex field: " + name)
        if length is None:
            number = int(value, 16)
            if value != hex(number):
                raise ValueError("noncanonical quantity: " + name)
            raw = rlp_uint(number)
        else:
            raw = bytes.fromhex(value[2:])
            if (length == -1 and len(raw) > 32) or (length != -1 and len(raw) != length):
                raise ValueError("header field length: " + name)
        values.append(raw)
    encoded = rlp_list(values)
    digest = "0x" + keccak256(encoded).hex()
    if digest != header["hash"] or digest != HASHES.get(int(header["number"], 16)):
        raise ValueError("header RLP hash mismatch")
    return {"number": int(header["number"], 16), "block_hash": digest,
            "parent_hash": header["parentHash"], "fee_recipient": header["miner"],
            "base_fee_per_gas_wei": str(int(header["baseFeePerGas"], 16)),
            "header_rlp_hex": "0x" + encoded.hex(), "field_count": len(FIELDS)}


def verify(witness_path):
    with tempfile.TemporaryDirectory() as d:
        witness = Witness(Path(d) / "offline", replay=witness_path, provider="nodies")
        headers = [witness.call("eth_getBlockByNumber", [hex(n), False]) for n in [PREVIOUS, WINNER]]
        verified = [verify_header(h) for h in headers]
    if verified[1]["parent_hash"] != verified[0]["block_hash"]:
        raise ValueError("header parent link")
    ledger_path = HERE / "settlements/settlement-ledger.jsonl"
    ledger_raw = ledger_path.read_bytes()
    if sha(ledger_raw) != "41baeedb38ad823c630ef8f3591630d45f5c520f3d755e7bcd2d399982541b93":
        raise ValueError("original settlement ledger changed")
    ledger = [json.loads(x) for x in ledger_raw.splitlines()]
    selected = [x for x in ledger if x["transaction_hash"] == WINNER_TX]
    if len(selected) != 1 or selected[0]["block_hash"] != HASHES[WINNER]:
        raise ValueError("settlement block binding")
    selected = selected[0]
    payments = [x for x in selected["root_outgoing_recipients"]
                if x["address"] == verified[1]["fee_recipient"]]
    receipts_path = HERE.parent / "additional_evidence/recovered-rmc016/tenderly-receipts-20261009.jsonl.gz"
    receipts_raw = receipts_path.read_bytes()
    if sha(receipts_raw) != "2db8f5d3d73c0a83aeae6af16bb61c275c35edcca7b229ce72a8b26484e8fe20":
        raise ValueError("receipt archive changed")
    receipts = [json.loads(x) for x in gzip.decompress(receipts_raw).splitlines()]
    matches = [x["result"] for x in receipts if x["method"] == "eth_getTransactionReceipt"
               and x["params"] == [WINNER_TX]]
    if len(matches) != 1 or matches[0]["blockHash"] != HASHES[WINNER]:
        raise ValueError("receipt block binding")
    receipt = matches[0]
    used, price = int(receipt["gasUsed"], 16), int(receipt["effectiveGasPrice"], 16)
    base_fee = int(verified[1]["base_fee_per_gas_wei"])
    if price < base_fee or used * price != int(selected["gas_from_existing_receipt_counted_once_wei"]):
        raise ValueError("receipt/header gas mismatch")
    return {"schema": "nqc-rank1-authenticated-header-payments-v1", "headers": verified,
            "witness_sha256": sha(Path(witness_path).read_bytes()),
            "settlement_ledger_sha256": sha(ledger_raw), "transaction_hash": WINNER_TX,
            "root_executor": selected["root_execution_account"],
            "trace_visible_payments_to_block_fee_recipient": payments,
            "receipt_archive_sha256": sha(receipts_raw),
            "historical_transaction_gas": {"gas_used": used, "payer": receipt["from"],
                "effective_gas_price_wei": str(price), "total_wei": str(used * price),
                "base_fee_burn_wei": str(used * base_fee),
                "priority_fee_to_block_fee_recipient_wei": str(used * (price - base_fee)),
                "already_counted_in_settlement_ledger": True,
                "direct_trace_payment_is_separate_from_receipt_gas": True},
            "proof_scope": "HEADER_FIELDS_AGAINST_PREEXISTING_BLOCK_HASH_ANCHORS",
            "state_responses_merkle_proven": False, "trace_inclusion_proven": False,
            "recipient_ownership_proven": False, "payment_agreement_proven": False,
            "payment_applied_as_nqc_capture_cost": False, "complete_profit_wei": None,
            "capital_admission_changed": False, "census_closed": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--witness", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    Path(args.output).write_text(canonical(verify(args.witness)) + "\n")
