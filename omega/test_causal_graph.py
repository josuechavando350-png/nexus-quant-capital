import copy
import unittest

from causal_graph import CausalGraph, seal_graph, validate_graph


def h(ch):
    return ch * 64


def bh(ch):
    return "0x" + ch * 64


ANCHOR = {"chain_id": 1, "block_number": 26000000, "block_hash": bh("a")}


def node(ch, kind):
    return {"node_id": h(ch), "kind": kind, "evidence_sha256": h("f")}


def edge(source, target, kind):
    return {
        "from_node": h(source), "to_node": h(target), "kind": kind,
        "evidence_sha256": h("e"),
    }


def fixture():
    nodes = [
        node("1", "POSITION"), node("2", "MARKET"), node("3", "ORACLE"),
        node("4", "INTEREST_MODEL"), node("5", "LIQUIDITY_SOURCE"),
        node("6", "ROUTE"),
    ]
    edges = [
        edge("1", "2", "POSITION_MARKET"),
        edge("1", "3", "POSITION_ORACLE"),
        edge("1", "4", "POSITION_INTEREST"),
        edge("1", "5", "POSITION_LIQUIDITY"),
        edge("1", "6", "POSITION_ROUTE"),
        edge("2", "3", "MARKET_ORACLE"),
        edge("2", "4", "MARKET_INTEREST"),
        edge("6", "5", "ROUTE_LIQUIDITY"),
    ]
    return nodes, edges


class CausalGraphTests(unittest.TestCase):
    def test_valid_complete_graph_passes(self):
        nodes, edges = fixture()
        graph = seal_graph(ANCHOR, nodes, edges)
        self.assertEqual(validate_graph(graph), [])

    def test_missing_position_dependency_is_blocked(self):
        nodes, edges = fixture()
        edges = [item for item in edges if item["kind"] != "POSITION_ROUTE"]
        with self.assertRaisesRegex(ValueError, "position_dependency_coverage_incomplete"):
            seal_graph(ANCHOR, nodes, edges)

    def test_duplicate_node_is_blocked(self):
        nodes, edges = fixture()
        nodes.append(copy.deepcopy(nodes[0]))
        with self.assertRaisesRegex(ValueError, "duplicate_node"):
            seal_graph(ANCHOR, nodes, edges)

    def test_duplicate_edge_is_blocked(self):
        nodes, edges = fixture()
        edges.append(copy.deepcopy(edges[0]))
        with self.assertRaisesRegex(ValueError, "duplicate_edge"):
            seal_graph(ANCHOR, nodes, edges)

    def test_dangling_edge_is_blocked(self):
        nodes, edges = fixture()
        edges.append(edge("1", "9", "POSITION_ROUTE"))
        with self.assertRaisesRegex(ValueError, "dangling_edge"):
            seal_graph(ANCHOR, nodes, edges)

    def test_edge_type_mismatch_is_blocked(self):
        nodes, edges = fixture()
        edges.append(edge("2", "5", "MARKET_ORACLE"))
        with self.assertRaisesRegex(ValueError, "edge_type_mismatch"):
            seal_graph(ANCHOR, nodes, edges)

    def test_self_edge_is_blocked(self):
        nodes, edges = fixture()
        edges.append(edge("2", "2", "MARKET_ORACLE"))
        with self.assertRaisesRegex(ValueError, "self_edge_forbidden"):
            seal_graph(ANCHOR, nodes, edges)

    def test_cycle_is_blocked(self):
        nodes, edges = fixture()
        # Add a POSITION node as a forbidden target by mutating an otherwise valid edge kind.
        cycle = {
            "from_node": h("6"), "to_node": h("1"),
            "kind": "ROUTE_LIQUIDITY", "evidence_sha256": h("e"),
        }
        edges.append(cycle)
        with self.assertRaises(ValueError) as ctx:
            seal_graph(ANCHOR, nodes, edges)
        self.assertTrue(
            "edge_type_mismatch" in str(ctx.exception) or "causal_cycle_forbidden" in str(ctx.exception)
        )

    def test_oracle_change_invalidates_position_transitively(self):
        nodes, edges = fixture()
        graph = CausalGraph(seal_graph(ANCHOR, nodes, edges))
        self.assertEqual(graph.affected_positions([h("3")]), [h("1")])

    def test_liquidity_change_invalidates_via_route_and_direct_edge(self):
        nodes, edges = fixture()
        graph = CausalGraph(seal_graph(ANCHOR, nodes, edges))
        self.assertEqual(graph.affected_positions([h("5")]), [h("1")])

    def test_market_change_invalidates_position(self):
        nodes, edges = fixture()
        graph = CausalGraph(seal_graph(ANCHOR, nodes, edges))
        self.assertEqual(graph.affected_positions([h("2")]), [h("1")])

    def test_unrelated_oracle_does_not_invalidate_position(self):
        nodes, edges = fixture()
        nodes.append(node("7", "ORACLE"))
        graph = CausalGraph(seal_graph(ANCHOR, nodes, edges))
        self.assertEqual(graph.affected_positions([h("7")]), [])

    def test_shared_oracle_invalidates_multiple_positions(self):
        nodes, edges = fixture()
        nodes.append(node("8", "POSITION"))
        edges.extend([
            edge("8", "2", "POSITION_MARKET"),
            edge("8", "3", "POSITION_ORACLE"),
            edge("8", "4", "POSITION_INTEREST"),
            edge("8", "5", "POSITION_LIQUIDITY"),
            edge("8", "6", "POSITION_ROUTE"),
        ])
        graph = CausalGraph(seal_graph(ANCHOR, nodes, edges))
        self.assertEqual(graph.affected_positions([h("3")]), [h("1"), h("8")])

    def test_direct_dependencies_are_complete_and_deterministic(self):
        nodes, edges = fixture()
        graph = CausalGraph(seal_graph(ANCHOR, nodes, edges))
        deps = graph.direct_dependencies(h("1"))
        self.assertEqual(len(deps), 5)
        self.assertEqual({item["edge_kind"] for item in deps}, {
            "POSITION_MARKET", "POSITION_ORACLE", "POSITION_INTEREST",
            "POSITION_LIQUIDITY", "POSITION_ROUTE",
        })

    def test_unknown_changed_node_is_blocked(self):
        nodes, edges = fixture()
        graph = CausalGraph(seal_graph(ANCHOR, nodes, edges))
        with self.assertRaisesRegex(ValueError, "unknown_changed_node"):
            graph.affected_positions([h("9")])

    def test_empty_change_set_is_blocked(self):
        nodes, edges = fixture()
        graph = CausalGraph(seal_graph(ANCHOR, nodes, edges))
        with self.assertRaisesRegex(ValueError, "changed_nodes_invalid"):
            graph.affected_positions([])

    def test_node_and_edge_evidence_are_required(self):
        nodes, edges = fixture()
        nodes[0]["evidence_sha256"] = ""
        with self.assertRaisesRegex(ValueError, "node_evidence_invalid"):
            seal_graph(ANCHOR, nodes, edges)
        nodes, edges = fixture()
        edges[0]["evidence_sha256"] = ""
        with self.assertRaisesRegex(ValueError, "edge_evidence_invalid"):
            seal_graph(ANCHOR, nodes, edges)

    def test_tamper_breaks_graph_commitment(self):
        nodes, edges = fixture()
        graph = seal_graph(ANCHOR, nodes, edges)
        graph["nodes"][0]["evidence_sha256"] = h("d")
        self.assertIn("graph_commitment_mismatch", validate_graph(graph))

    def test_unsorted_graph_is_rejected(self):
        nodes, edges = fixture()
        graph = seal_graph(ANCHOR, nodes, edges)
        graph["nodes"].reverse()
        graph["edges"].reverse()
        errors = validate_graph(graph)
        self.assertIn("nodes_not_canonically_sorted", errors)
        self.assertIn("edges_not_canonically_sorted", errors)

    def test_all_execution_authorities_are_false(self):
        nodes, edges = fixture()
        graph = seal_graph(ANCHOR, nodes, edges)
        for key in graph["authorities"]:
            changed = copy.deepcopy(graph)
            changed["authorities"][key] = True
            self.assertIn("authority_forbidden", validate_graph(changed))


if __name__ == "__main__":
    unittest.main()
