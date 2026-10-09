#!/usr/bin/env python3
"""Offline gas-capital accounting model for the explicit MXN 2,000 exception.

Exact integers only. No wallet, price feed, RPC, signing or broadcasting. The
caller must independently authenticate funding lots, nonce/finality witnesses,
receipts and exclusivity of wallet use. Hash references alone do not do that.
Acceptance here means accounting-consistent supplied witnesses, not executable
capital or economic certification. A chain reorg requires independent recovery;
this reference model has no automated reversal or live-execution authority.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re

POLICY = "NQC_GAS_ONLY_MXN_2000_20261009"
AUTHORIZATION_DATE = dt.date(2026, 10, 9)
MAX_CENTAVOS = 200000
UINT256_MAX = 2**256 - 1


def require(condition, message):
    if not condition:
        raise ValueError(message)


def uint(value, label, positive=False):
    require(type(value) is int and int(positive) <= value <= UINT256_MAX, label + ": invalid integer")
    return value


def evidence(value):
    require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value)
            and value != "0" * 64, "nonzero evidence SHA-256 required")
    return value


def timestamp(value):
    require(type(value) is str and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", value),
            "UTC timestamp required")
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def keys(value, expected):
    require(type(value) is dict and set(value) == set(expected), "unknown/missing fields")


def account(row):
    chain = uint(row["chain_id"], "chain id", True)
    wallet = row["wallet"]
    require(type(wallet) is str and re.fullmatch(r"0x[0-9a-f]{40}", wallet)
            and wallet != "0x" + "0" * 40, "canonical nonzero wallet required")
    return chain, wallet


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


class Budget:
    def __init__(self):
        self.contributed = 0
        self.wallets = {}
        self.holds = {}
        self.closed_nonces = set()
        self.events = set()
        self.funding_proofs = set()
        self.receipts = set()
        self.transactions = set()
        self.last_time = None
        self.chain_hash = "0" * 64
        self.spent_wei = {}
        self.failed_wei = {}
        self.event_count = 0

    def apply(self, event):
        """Atomic model transition: invalid events cannot partly change state."""
        import copy
        staged = copy.deepcopy(self)
        staged._apply(event)
        self.__dict__.update(staged.__dict__)

    def _apply(self, event):
        require(type(event) is dict, "event must be object")
        base = {"event_id", "kind", "at", "policy_id"}
        extra = {
            "FUND": {"chain_id", "wallet", "native_wei", "cost_centavos", "evidence_sha256", "received_at"},
            "RESERVE": {"chain_id", "wallet", "nonce", "tx_hash", "purpose", "gas_limit", "max_fee_per_gas",
                        "data_and_blob_fee_cap_wei", "evidence_sha256", "received_at"},
            "SETTLE": {"chain_id", "wallet", "nonce", "tx_hash", "gas_used", "effective_gas_price",
                       "data_and_blob_fee_wei", "outcome", "evidence_sha256", "received_at"},
        }
        kind = event.get("kind")
        require(kind in extra, "unsupported event; no implicit refund/reset/release")
        keys(event, base | extra[kind])
        equal_policy = event["policy_id"] == POLICY
        require(equal_policy, "policy mismatch")
        eid = event["event_id"]
        require(type(eid) is str and re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", eid)
                and eid not in self.events, "duplicate/invalid event id")
        at, received = timestamp(event["at"]), timestamp(event["received_at"])
        require(at.date() >= AUTHORIZATION_DATE, "gas policy cannot be applied before authorization date")
        require(received <= at, "future evidence at decision time")
        require(self.last_time is None or at >= self.last_time, "events must be chronological")
        key = account(event)
        proof = evidence(event["evidence_sha256"])
        if kind == "FUND":
            native = uint(event["native_wei"], "funded native", True)
            cost = uint(event["cost_centavos"], "funded MXN", True)
            require(proof not in self.funding_proofs, "funding evidence reused")
            require(self.contributed + cost <= MAX_CENTAVOS, "operator contribution cap exceeded")
            self.contributed += cost
            self.funding_proofs.add(proof)
            self.wallets[key] = uint(self.wallets.get(key, 0) + native, "wallet balance")
        else:
            nonce = uint(event["nonce"], "nonce")
            nonce_key = (*key, nonce)
            require(nonce_key not in self.closed_nonces, "nonce already settled")
            tx_hash = event["tx_hash"]
            require(type(tx_hash) is str and re.fullmatch(r"0x[0-9a-f]{64}", tx_hash)
                    and tx_hash != "0x" + "0" * 64, "nonzero transaction hash required")
            if kind == "RESERVE":
                require(event["purpose"] == "NATIVE_NETWORK_GAS", "operator capital restricted to gas")
                gas = uint(event["gas_limit"], "gas limit", True)
                fee = uint(event["max_fee_per_gas"], "max gas price", True)
                other = uint(event["data_and_blob_fee_cap_wei"], "data/blob cap")
                reserve = uint(gas * fee + other, "gas exposure", True)
                require((key[0], tx_hash) not in self.transactions, "transaction already reserved")
                variants = self.holds.setdefault(nonce_key, {})
                variants[tx_hash] = {"cap": reserve, "gas_limit": gas, "max_fee": fee, "other_cap": other}
                held = sum(max(v["cap"] for v in txs.values()) for nk, txs in self.holds.items() if nk[:2] == key)
                require(held <= self.wallets.get(key, 0), "insufficient native balance including concurrent holds")
                self.transactions.add((key[0], tx_hash))
            else:
                require(nonce_key in self.holds and tx_hash in self.holds[nonce_key], "unreserved settlement")
                require(proof not in self.receipts, "receipt evidence reused")
                require(event["outcome"] in ("FINALIZED_SUCCESS", "FINALIZED_REVERT"), "finalized outcome required")
                variant = self.holds[nonce_key][tx_hash]
                gas = uint(event["gas_used"], "gas used", True)
                price = uint(event["effective_gas_price"], "effective gas price")
                other = uint(event["data_and_blob_fee_wei"], "data/blob fee")
                require(gas <= variant["gas_limit"] and price <= variant["max_fee"] and
                        other <= variant["other_cap"], "receipt exceeds reserved transaction bounds")
                paid = uint(gas * price + other, "paid gas")
                require(paid <= self.wallets[key], "receipt exceeds wallet balance")
                self.wallets[key] -= paid
                self.spent_wei[key] = self.spent_wei.get(key, 0) + paid
                if event["outcome"] == "FINALIZED_REVERT":
                    self.failed_wei[key] = self.failed_wei.get(key, 0) + paid
                del self.holds[nonce_key]
                self.closed_nonces.add(nonce_key)
                self.receipts.add(proof)
        self.events.add(eid)
        self.last_time = at
        self.event_count += 1
        self.chain_hash = hashlib.sha256(bytes.fromhex(self.chain_hash) + canonical(event)).hexdigest()

    def report(self):
        wallets = []
        for key, balance in sorted(self.wallets.items()):
            held = sum(max(v["cap"] for v in txs.values()) for nk, txs in self.holds.items() if nk[:2] == key)
            wallets.append({"chain_id": key[0], "wallet": key[1], "native_remaining_wei": balance,
                            "native_reserved_wei": held, "native_available_wei": balance - held,
                            "gas_paid_wei": self.spent_wei.get(key, 0), "reverted_gas_paid_wei": self.failed_wei.get(key, 0)})
        return {"schema": "nqc-gas-budget-accounting-v1", "policy_id": POLICY,
                "status": "SUPPLIED_WITNESS_ACCOUNTING_CONSISTENT",
                "operator_budget_centavos": MAX_CENTAVOS, "contributed_centavos": self.contributed,
                "uncontributed_budget_centavos": MAX_CENTAVOS - self.contributed,
                "event_count": self.event_count, "event_chain_sha256": self.chain_hash,
                "wallets": wallets, "funding_authenticity_verified": False,
                "receipt_semantics_verified": False, "capital_feasibility_certified": False,
                "intraday_authorization_time_verified": False,
                "real_market_census_closed": False, "operational_executor_connected": False}


def replay(events):
    require(type(events) is list, "event array required")
    state = Budget()
    for event in events:
        state.apply(event)
    return state.report()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    def pairs(items):
        value = {}
        for k, v in items:
            require(k not in value, "duplicate JSON key")
            value[k] = v
        return value
    def bad_constant(value):
        raise ValueError("nonfinite JSON: " + value)
    raw = args.events.read_bytes()
    require(len(raw) <= 16 * 1024 * 1024, "input limit")
    result = replay(json.loads(raw, object_pairs_hook=pairs, parse_constant=bad_constant))
    result["input_sha256"] = hashlib.sha256(raw).hexdigest()
    with args.output.open("xb") as stream:
        stream.write(canonical(result))


if __name__ == "__main__":
    main()
