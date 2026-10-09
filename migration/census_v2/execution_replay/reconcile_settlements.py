#!/usr/bin/env python3
"""Trace-visible native settlements, with delegate context and rollback semantics.

Rendered call values are not complete state differences, recipient ownership,
builder attribution or profit. Root value and internal value are separate edges.
"""
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile
sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
sys.path[:0] = [str(V2), str(V2.parents[1] / "ci/nqc-census")]
from reconcile_winner_traces import ARCHIVE_SHA, parse_trace
from verify_winner_recovery import canonical, need, sha
from typed_observation_vectors import keccak256

ADDRESS = re.compile(r"^(0x[0-9a-fA-F]{40})::")
VALUE = re.compile(r"\{value: ([0-9]+)\}")
WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
WITHDRAWAL = "0x" + keccak256(b"Withdrawal(address,uint256)").hex()
BASE = "09bf5069d81d45928bfcda0926373c933aaaa557"


def fixed(path):
    import subprocess
    path = Path(path)
    raw = path.read_bytes()
    relative = str(path.relative_to(V2.parents[1]))
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    expected = subprocess.check_output(["git", "-C", str(V2.parents[1]), "rev-parse", BASE + ":" + relative], text=True).strip()
    need(blob == expected, "committed source drift: " + relative)
    return raw


def native_edges(nodes, sender):
    contexts, edges, excluded = [], [], []
    for index, node in enumerate(nodes):
        target_match = ADDRESS.match(node["body"])
        precompile = re.match(r"^PRECOMPILES::(ecrecover|identity)\(", node["body"])
        need(target_match is not None or precompile is not None, "unsupported call target representation")
        target = (target_match.group(1).lower() if target_match else
                  "0x" + format({"ecrecover": 1, "identity": 4}[precompile.group(1)], "040x"))
        parent = node["parent"]
        need(parent is None or 0 <= parent < index, "invalid call parent")
        caller = sender if parent is None else contexts[parent]
        delegated = "[delegatecall]" in node["body"]
        need("[callcode]" not in node["body"].lower(), "CALLCODE needs explicit semantics")
        contexts.append(caller if delegated else target)
        value = VALUE.search(node["body"])
        if not value:
            continue
        row = {"trace_line": node["line"], "caller_context": caller, "target": target,
               "value_wei": value.group(1), "root_call": parent is None,
               "successful_ancestry": node["successful_ancestry"], "delegatecall": delegated}
        if delegated or not row["successful_ancestry"]:
            row["excluded_reason"] = "DELEGATECALL_INHERITED_VALUE_NOT_TRANSFER" if delegated else "REVERTED_ANCESTRY"
            excluded.append(row)
        else:
            need("[staticcall]" not in node["body"], "value under STATICCALL")
            row["weth_withdraw_return"] = (
                parent is not None and caller == WETH and
                nodes[parent]["body"].lower().startswith(WETH + "::withdraw("))
            row["balance_delta_completeness_proven"] = False
            edges.append(row)
    return edges, excluded


def withdrawals(receipt):
    amounts = Counter()
    for log in receipt["logs"]:
        if log["address"] != WETH or not log["topics"] or log["topics"][0] != WITHDRAWAL:
            continue
        need(len(log["topics"]) == 2 and len(log["data"]) == 66 and log["topics"][1][2:26] == "0" * 24,
             "invalid WETH Withdrawal ABI")
        amounts[("0x" + log["topics"][1][-40:], int(log["data"], 16))] += 1
    return amounts


def reconcile(archive, output):
    archive_raw = archive.read_bytes()
    need(sha(archive_raw) == ARCHIVE_SHA, "original trace archive hash mismatch")
    receipt_raw = fixed(V2 / "additional_evidence/recovered-rmc016/tenderly-receipts-20261009.jsonl.gz")
    receipts = {}
    for raw in gzip.decompress(receipt_raw).splitlines():
        row = json.loads(raw)
        if row["method"] == "eth_getTransactionReceipt":
            tx = row["params"][0]
            need(tx not in receipts, "duplicate receipt")
            receipts[tx] = row["result"]
    need(len(receipts) == 127, "receipt population changed")
    original_values = [json.loads(line) for line in fixed(V2 / "evidence/winner-traces/native-value-observations.jsonl").splitlines()]
    prior_values = {(r["transaction_hash"], r["trace_line"]): r for r in original_values}
    need(len(prior_values) == len(original_values) == 350, "original value population changed")
    economics = {r["transaction_hash"]: r for r in map(json.loads, fixed(V2 / "evidence/economics/replay/winner-economic-ledger.jsonl").splitlines())}
    selected = {r["transaction_hash"]: r for r in map(json.loads, fixed(V2 / "evidence/economics/replay/weth-cost-reference.jsonl").splitlines())}
    edges_all, excluded_all, ledgers, seen_values, seen_transactions = [], [], [], set(), set()
    with zipfile.ZipFile(archive) as zipped:
        need(len(zipped.namelist()) == len(set(zipped.namelist())), "duplicate archive member")
        for name in sorted(zipped.namelist()):
            if not re.fullmatch(r"[0-9]{4}-[0-9a-f]{16}\.json", name):
                continue
            record = json.loads(zipped.read(name))
            tx = record["transaction_hash"]
            need(tx in receipts and tx not in seen_transactions, "trace population differs")
            seen_transactions.add(tx)
            receipt = receipts[tx]
            need(record["block_hash"] == receipt["blockHash"] and record["block_number"] == int(receipt["blockNumber"], 16)
                 and record["from"].lower() == receipt["from"] and record["to"].lower() == receipt["to"], "trace/receipt identity mismatch")
            trace_name = name[:-5] + ".cast.log"
            raw = zipped.read(trace_name)
            need(sha(raw) == record["cast_log_sha256"], "trace content mismatch")
            gas, nodes = parse_trace(raw)
            need(gas == int(receipt["gasUsed"], 16) == record["gas_used"]
                 and record["effective_gas_price_wei"] == str(int(receipt["effectiveGasPrice"], 16)), "gas/receipt mismatch")
            edges, excluded = native_edges(nodes, receipt["from"])
            provenance = {"transaction_hash": tx, "block_hash": receipt["blockHash"],
                          "trace_member": trace_name, "trace_sha256": sha(raw)}
            for edge in edges + excluded:
                key = (tx, edge["trace_line"])
                old = prior_values[key]
                need(old["rendered_value_wei"] == edge["value_wei"] and old["target"] == edge["target"]
                     and old["delegatecall"] == edge["delegatecall"] and old["successful_ancestry"] == edge["successful_ancestry"],
                     "new semantic readback differs from original value observation")
                seen_values.add(key)
                edge.update(provenance)
            visible_withdrawals = Counter((e["target"], int(e["value_wei"])) for e in edges if e["weth_withdraw_return"])
            need(visible_withdrawals == withdrawals(receipt), "trace WETH withdrawals differ from full receipt")
            amounts = defaultdict(int)
            for edge in edges:
                amounts[edge["caller_context"]] -= int(edge["value_wei"])
                amounts[edge["target"]] += int(edge["value_wei"])
            need(sum(amounts.values()) == 0, "native edge conservation failed")
            root = receipt["to"]
            payouts = [e for e in edges if not e["root_call"] and e["caller_context"] == root and e["target"] != root]
            root_in = sum(int(e["value_wei"]) for e in edges if e["target"] == root)
            root_out = sum(int(e["value_wei"]) for e in edges if e["caller_context"] == root)
            paid_gas = gas * int(receipt["effectiveGasPrice"], 16)
            need(str(paid_gas) == economics[tx]["historical_gas"]["whole_transaction_wei"], "gas double-count protection binding")
            row = {**provenance, "block_number": record["block_number"], "transaction_index": record["transaction_index"],
                   "gas_payer": receipt["from"], "root_execution_account": root, "visible_transfer_edges": len(edges),
                   "excluded_rendered_values": len(excluded), "withdrawal_events_matched": sum(visible_withdrawals.values()),
                   "root_visible_native_inflow_wei": str(root_in), "root_visible_native_outflow_wei": str(root_out),
                   "root_visible_native_net_before_gas_wei": str(root_in - root_out),
                   "root_outgoing_recipients": [{"address": e["target"], "wei": e["value_wei"], "trace_line": e["trace_line"],
                                                "role": "UNATTRIBUTED", "is_gas_payer": e["target"] == receipt["from"]} for e in payouts],
                   "gas_from_existing_receipt_counted_once_wei": str(paid_gas),
                   "complete_native_balance_deltas_proven": False, "recipient_ownership_proven": False,
                   "builder_payment_attribution_proven": False, "complete_profit_wei": None,
                   "admitted_nqc_executable_value_usd_wad": "0", "classification": "INSUFFICIENT_EVIDENCE"}
            if tx in selected:
                ref = selected[tx]
                row["selected_weth_reference"] = {"rank": ref["retrospective_rank"],
                    "event_collateral_less_debt_wei": str(int(ref["collateral_weth_wei"]) - int(ref["debt_weth_wei"])),
                    "total_visible_weth_withdrawn_wei": str(sum(a * n for (_, a), n in visible_withdrawals.items())),
                    "outgoing_native_not_automatically_an_additional_cost": True,
                    "prior_conditional_reference_is_not_retained_executor_profit": True}
            ledgers.append(row)
            edges_all.extend(edges)
            excluded_all.extend(excluded)
    need(seen_transactions == set(receipts) and seen_values == set(prior_values), "incomplete readback")
    output.mkdir(parents=True, exist_ok=False)
    files = {}
    for name, rows in [("native-transfer-edges.jsonl", edges_all), ("excluded-values.jsonl", excluded_all),
                       ("settlement-ledger.jsonl", ledgers)]:
        data = b"".join(canonical(row) for row in rows)
        (output / name).write_bytes(data)
        files[name] = {"sha256": sha(data), "rows": len(rows)}
    report = {"schema": "nqc-native-settlement-readback-v1", "status": "TRACE_AND_RECEIPT_READBACK_PASS_NOT_PNL",
              "trace_archive_sha256": ARCHIVE_SHA, "receipt_archive_sha256": sha(receipt_raw),
              "verifier_sha256": sha(Path(__file__).read_bytes()), "source_commit": BASE,
              "transactions": len(ledgers), "rendered_values_reconciled": len(seen_values),
              "visible_transfer_edges": len(edges_all), "excluded_values": len(excluded_all),
              "excluded_reasons": dict(Counter(e["excluded_reason"] for e in excluded_all)),
              "withdrawal_events_matched": sum(r["withdrawal_events_matched"] for r in ledgers),
              "selected_weth_transactions": sum("selected_weth_reference" in r for r in ledgers),
              "new_chain_rpc_calls": 0, "new_fork_execution": False, "files": files,
              "complete_profit_proven": False, "capital_admission_changed": False,
              "census_closed": False, "independent_certification": False}
    (output / "report.json").write_bytes(canonical(report))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(reconcile(args.archive, args.output), sort_keys=True))
