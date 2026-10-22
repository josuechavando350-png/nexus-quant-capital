import copy
import unittest

from protocol_adapters import (
    CAPABILITIES, ProtocolAdapterRegistry, seal_registry, validate_registry,
)


def h(ch):
    return ch * 64


def cap(supported):
    return {"supported": supported, "evidence_sha256": h("e") if supported else None}


def adapter(ch="1", family="AAVE_V3", chain=1, deployment="0x" + "1" * 40, supported=None):
    if supported is None:
        supported = {
            "market_discovery", "state_read", "position_enumeration",
        }
    return {
        "adapter_id": h(ch),
        "protocol_family": family,
        "chain_id": chain,
        "deployment": deployment,
        "version_commitment_sha256": h("a"),
        "implementation_git_blob": "b" * 40,
        "capabilities": {name: cap(name in supported) for name in CAPABILITIES},
        "source_commitment_sha256": h("c"),
    }


class ProtocolAdapterTests(unittest.TestCase):
    def test_valid_registry_passes(self):
        value = seal_registry([adapter()])
        self.assertEqual(validate_registry(value), [])

    def test_supported_capability_requires_evidence(self):
        item = adapter()
        item["capabilities"]["market_discovery"]["evidence_sha256"] = None
        with self.assertRaisesRegex(ValueError, "supported_capability_missing_evidence"):
            seal_registry([item])

    def test_unsupported_capability_must_have_null_evidence(self):
        item = adapter()
        item["capabilities"]["liquidation_math"]["evidence_sha256"] = h("d")
        with self.assertRaisesRegex(ValueError, "unsupported_capability_evidence_must_be_null"):
            seal_registry([item])

    def test_capability_matrix_is_exact(self):
        item = adapter()
        item["capabilities"].pop("route_evidence")
        with self.assertRaisesRegex(ValueError, "capability_matrix_invalid"):
            seal_registry([item])

    def test_duplicate_adapter_id_is_blocked(self):
        a = adapter()
        b = adapter(deployment="0x" + "2" * 40)
        with self.assertRaisesRegex(ValueError, "duplicate_adapter_id"):
            seal_registry([a, b])

    def test_duplicate_deployment_adapter_is_blocked(self):
        a = adapter("1")
        b = adapter("2")
        with self.assertRaisesRegex(ValueError, "duplicate_deployment_adapter"):
            seal_registry([a, b])

    def test_same_address_on_different_family_is_allowed(self):
        value = seal_registry([
            adapter("1", family="AAVE_V3"),
            adapter("2", family="MORPHO_BLUE"),
        ])
        self.assertEqual(validate_registry(value), [])

    def test_unknown_protocol_family_is_blocked(self):
        with self.assertRaisesRegex(ValueError, "protocol_family_invalid"):
            seal_registry([adapter(family="AAVE_V4")])

    def test_bad_git_blob_is_blocked(self):
        item = adapter()
        item["implementation_git_blob"] = "z" * 40
        with self.assertRaisesRegex(ValueError, "implementation_git_blob_invalid"):
            seal_registry([item])

    def test_bad_deployment_is_blocked(self):
        item = adapter()
        item["deployment"] = "0x1234"
        with self.assertRaisesRegex(ValueError, "deployment_invalid"):
            seal_registry([item])

    def test_require_capabilities_passes_only_supported_set(self):
        registry = ProtocolAdapterRegistry(seal_registry([adapter()]))
        result = registry.require_capabilities(h("1"), ["state_read", "market_discovery"])
        self.assertTrue(result["conformant"])
        self.assertEqual(result["missing"], [])
        self.assertFalse(result["certification_claimed"])

    def test_require_capabilities_reports_missing(self):
        registry = ProtocolAdapterRegistry(seal_registry([adapter()]))
        result = registry.require_capabilities(h("1"), ["liquidation_math", "state_read"])
        self.assertFalse(result["conformant"])
        self.assertEqual(result["missing"], ["liquidation_math"])

    def test_unknown_capability_is_blocked(self):
        registry = ProtocolAdapterRegistry(seal_registry([adapter()]))
        with self.assertRaisesRegex(ValueError, "unknown_capability"):
            registry.supports(h("1"), "magic")

    def test_duplicate_required_capability_is_blocked(self):
        registry = ProtocolAdapterRegistry(seal_registry([adapter()]))
        with self.assertRaisesRegex(ValueError, "duplicate_required_capability"):
            registry.require_capabilities(h("1"), ["state_read", "state_read"])

    def test_unknown_adapter_is_blocked(self):
        registry = ProtocolAdapterRegistry(seal_registry([adapter()]))
        with self.assertRaisesRegex(ValueError, "unknown_adapter"):
            registry.adapter(h("9"))

    def test_families_are_deterministic(self):
        registry = ProtocolAdapterRegistry(seal_registry([
            adapter("2", family="MORPHO_BLUE", deployment="0x" + "2" * 40),
            adapter("1", family="AAVE_V3"),
        ]))
        self.assertEqual(list(registry.families()), ["AAVE_V3", "MORPHO_BLUE"])

    def test_tamper_breaks_commitment(self):
        value = seal_registry([adapter()])
        value["adapters"][0]["chain_id"] = 10
        self.assertIn("registry_commitment_mismatch", validate_registry(value))

    def test_unsorted_adapters_are_rejected(self):
        value = seal_registry([
            adapter("2", family="MORPHO_BLUE", deployment="0x" + "2" * 40),
            adapter("1", family="AAVE_V3"),
        ])
        value["adapters"].reverse()
        self.assertIn("adapters_not_canonically_sorted", validate_registry(value))

    def test_all_execution_authorities_are_false(self):
        value = seal_registry([adapter()])
        for key in value["authorities"]:
            changed = copy.deepcopy(value)
            changed["authorities"][key] = True
            self.assertIn("authority_forbidden", validate_registry(changed))

    def test_morpho_can_exist_but_remain_nonconformant(self):
        morpho = adapter("2", family="MORPHO_BLUE", deployment="0x" + "2" * 40, supported=set())
        registry = ProtocolAdapterRegistry(seal_registry([morpho]))
        result = registry.require_capabilities(h("2"), ["market_discovery"])
        self.assertFalse(result["conformant"])
        self.assertEqual(result["missing"], ["market_discovery"])


if __name__ == "__main__":
    unittest.main()
