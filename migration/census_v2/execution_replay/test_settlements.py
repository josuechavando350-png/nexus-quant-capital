from pathlib import Path
import json
import tempfile
import unittest

from reconcile_settlements import native_edges, reconcile, withdrawals, WETH, WITHDRAWAL

A = "0x" + "11" * 20
B = "0x" + "22" * 20
C = "0x" + "33" * 20
SENDER = "0x" + "44" * 20


def node(body, parent=None, line=1, success=True):
    return {"body": body, "parent": parent, "line": line, "successful_ancestry": success}


class SettlementSemanticsTests(unittest.TestCase):
    def test_delegate_value_is_not_payment_and_child_uses_proxy_balance(self):
        nodes = [node(A + "::run{value: 10}()"),
                 node(B + "::run{value: 10}() [delegatecall]", 0, 2),
                 node(C + "::receive{value: 7}()", 1, 3)]
        edges, excluded = native_edges(nodes, SENDER)
        self.assertEqual(len(edges), 2)
        self.assertEqual(edges[1]["caller_context"], A)
        self.assertEqual(sum(int(x["value_wei"]) for x in edges), 17)
        self.assertEqual(excluded[0]["excluded_reason"], "DELEGATECALL_INHERITED_VALUE_NOT_TRANSFER")

    def test_reverted_parent_rolls_back_child_payment(self):
        nodes = [node(A + "::run()"), node(B + "::run()", 0, 2, False),
                 node(C + "::receive{value: 7}()", 1, 3, False)]
        edges, excluded = native_edges(nodes, SENDER)
        self.assertEqual(edges, [])
        self.assertEqual(excluded[0]["excluded_reason"], "REVERTED_ANCESTRY")

    def test_unmodeled_callcode_fails(self):
        with self.assertRaisesRegex(ValueError, "CALLCODE"):
            native_edges([node(A + "::run()"), node(B + "::run() [callcode]", 0, 2)], SENDER)

    def test_weth_unwrap_uses_emitter_owner_and_amount_not_generic_value(self):
        nodes = [node(A + "::run()"), node(WETH + "::withdraw(7)", 0, 2),
                 node(A + "::receive{value: 7}()", 1, 3), node(C + "::receive{value: 7}()", 0, 4)]
        edges, _ = native_edges(nodes, SENDER)
        self.assertEqual([e["weth_withdraw_return"] for e in edges], [True, False])
        log = {"address": WETH, "topics": [WITHDRAWAL, "0x" + "0" * 24 + A[2:]], "data": "0x" + format(7, "064x")}
        self.assertEqual(withdrawals({"logs": [log]})[(A, 7)], 1)
        log["address"] = B
        self.assertEqual(withdrawals({"logs": [log]}), {})

    def test_selected_original_archive_reconciles_and_no_profit_is_admitted(self):
        archive = Path(__file__).parent / "inputs/original-winner-traces.zip"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            report = reconcile(archive, output)
            self.assertEqual((report["transactions"], report["rendered_values_reconciled"],
                              report["visible_transfer_edges"], report["excluded_values"],
                              report["withdrawal_events_matched"]), (127, 350, 332, 18, 98))
            rows = [json.loads(line) for line in (output / "settlement-ledger.jsonl").read_text().splitlines()]
            selected = [r for r in rows if r.get("selected_weth_reference", {}).get("rank") == 1]
            self.assertEqual(len(selected), 1)
            row = selected[0]
            self.assertEqual(row["root_visible_native_outflow_wei"], "96156124691020450")
            self.assertEqual(row["root_visible_native_net_before_gas_wei"], "9975")
            self.assertEqual(sum(int(p["wei"]) for p in row["root_outgoing_recipients"]),
                             int(row["selected_weth_reference"]["event_collateral_less_debt_wei"]))
            self.assertTrue(all(r["complete_profit_wei"] is None and not r["recipient_ownership_proven"]
                                and r["admitted_nqc_executable_value_usd_wad"] == "0" for r in rows))


if __name__ == "__main__":
    unittest.main()
