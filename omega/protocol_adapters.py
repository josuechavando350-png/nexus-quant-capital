"""Protocol-agnostic offline adapter manifest/registry for Omega Census.

The registry describes adapter identity and evidence-bound capabilities. It does
not perform RPC, protocol math, signing, broadcasting, spending, or certification.
"""
from __future__ import annotations

import copy
import re

from integrity import canonical, digest

SCHEMA = "nqc.omega.protocol-adapter-registry.v1"
SCOPE = "CENSUS_OFFLINE_ADAPTER_IDENTITY_ONLY"
HEX32 = re.compile(r"^[0-9a-f]{64}$")
GIT_BLOB = re.compile(r"^[0-9a-f]{40}$")
ADDRESS = re.compile(r"^0x[0-9a-f]{40}$")
PROTOCOL_FAMILIES = {"AAVE_V3", "MORPHO_BLUE", "MORPHO_MIDNIGHT", "DUTCH_AUCTION"}
CAPABILITIES = (
    "market_discovery",
    "state_read",
    "position_enumeration",
    "liquidation_math",
    "oracle_semantics",
    "route_evidence",
)
TOP_KEYS = {
    "schema", "record_scope", "adapters", "authorities",
    "registry_commitment_sha256",
}
ADAPTER_KEYS = {
    "adapter_id", "protocol_family", "chain_id", "deployment",
    "version_commitment_sha256", "implementation_git_blob",
    "capabilities", "source_commitment_sha256",
}
CAPABILITY_KEYS = {"supported", "evidence_sha256"}
AUTHORITY_KEYS = {
    "can_sign", "can_broadcast", "can_spend", "phase_advance_authorized",
    "census_closed",
}


def _hex32(value: object) -> bool:
    return isinstance(value, str) and HEX32.fullmatch(value) is not None


def _canonical_adapters(values: list[dict]) -> list[dict]:
    return sorted(
        (copy.deepcopy(v) for v in values),
        key=lambda item: (item["chain_id"], item["protocol_family"], item["deployment"], item["adapter_id"]),
    )


def validate_registry(value: object) -> list[str]:
    errors: list[str] = []
    if type(value) is not dict:
        return ["registry_not_object"]
    if set(value) != TOP_KEYS:
        errors.append("top_level_shape_invalid")
    if value.get("schema") != SCHEMA:
        errors.append("wrong_schema")
    if value.get("record_scope") != SCOPE:
        errors.append("wrong_scope")

    authorities = value.get("authorities")
    if type(authorities) is not dict or set(authorities) != AUTHORITY_KEYS:
        errors.append("authorities_shape_invalid")
    elif any(authorities[key] is not False for key in AUTHORITY_KEYS):
        errors.append("authority_forbidden")

    adapters = value.get("adapters")
    ids = set()
    deployments = set()
    if type(adapters) is not list or not adapters:
        errors.append("adapters_invalid")
    else:
        for adapter in adapters:
            if type(adapter) is not dict or set(adapter) != ADAPTER_KEYS:
                errors.append("adapter_shape_invalid")
                continue
            aid = adapter["adapter_id"]
            if not _hex32(aid):
                errors.append("adapter_id_invalid")
            elif aid in ids:
                errors.append("duplicate_adapter_id")
            ids.add(aid)
            if adapter["protocol_family"] not in PROTOCOL_FAMILIES:
                errors.append("protocol_family_invalid")
            if type(adapter["chain_id"]) is not int or adapter["chain_id"] <= 0:
                errors.append("chain_id_invalid")
            deployment = adapter["deployment"]
            if not isinstance(deployment, str) or ADDRESS.fullmatch(deployment) is None:
                errors.append("deployment_invalid")
            dep_key = (adapter["chain_id"], adapter["protocol_family"], deployment)
            if dep_key in deployments:
                errors.append("duplicate_deployment_adapter")
            deployments.add(dep_key)
            if not _hex32(adapter["version_commitment_sha256"]):
                errors.append("version_commitment_invalid")
            if not isinstance(adapter["implementation_git_blob"], str) or GIT_BLOB.fullmatch(adapter["implementation_git_blob"]) is None:
                errors.append("implementation_git_blob_invalid")
            if not _hex32(adapter["source_commitment_sha256"]):
                errors.append("source_commitment_invalid")

            capabilities = adapter["capabilities"]
            if type(capabilities) is not dict or set(capabilities) != set(CAPABILITIES):
                errors.append("capability_matrix_invalid")
            else:
                for name in CAPABILITIES:
                    capability = capabilities[name]
                    if type(capability) is not dict or set(capability) != CAPABILITY_KEYS:
                        errors.append("capability_shape_invalid")
                        continue
                    if type(capability["supported"]) is not bool:
                        errors.append("capability_supported_invalid")
                        continue
                    if capability["supported"]:
                        if not _hex32(capability["evidence_sha256"]):
                            errors.append("supported_capability_missing_evidence")
                    elif capability["evidence_sha256"] is not None:
                        errors.append("unsupported_capability_evidence_must_be_null")

        if all(type(item) is dict and set(item) == ADAPTER_KEYS for item in adapters):
            if adapters != _canonical_adapters(adapters):
                errors.append("adapters_not_canonically_sorted")

    commitment = value.get("registry_commitment_sha256")
    if _hex32(commitment):
        unsigned = {k: v for k, v in value.items() if k != "registry_commitment_sha256"}
        if commitment != digest(canonical(unsigned)):
            errors.append("registry_commitment_mismatch")
    else:
        errors.append("registry_commitment_invalid")
    return sorted(set(errors))


def seal_registry(adapters: list[dict]) -> dict:
    registry = {
        "schema": SCHEMA,
        "record_scope": SCOPE,
        "adapters": _canonical_adapters(adapters),
        "authorities": {
            "can_sign": False,
            "can_broadcast": False,
            "can_spend": False,
            "phase_advance_authorized": False,
            "census_closed": False,
        },
    }
    registry["registry_commitment_sha256"] = digest(canonical(registry))
    errors = validate_registry(registry)
    if errors:
        raise ValueError("invalid_registry:" + ",".join(errors))
    return registry


class ProtocolAdapterRegistry:
    def __init__(self, registry: dict):
        errors = validate_registry(registry)
        if errors:
            raise ValueError("invalid_registry:" + ",".join(errors))
        self._registry = copy.deepcopy(registry)
        self._by_id = {item["adapter_id"]: item for item in registry["adapters"]}

    @property
    def commitment(self) -> str:
        return self._registry["registry_commitment_sha256"]

    def adapter(self, adapter_id: str) -> dict:
        if adapter_id not in self._by_id:
            raise ValueError("unknown_adapter")
        return copy.deepcopy(self._by_id[adapter_id])

    def supports(self, adapter_id: str, capability: str) -> bool:
        if capability not in CAPABILITIES:
            raise ValueError("unknown_capability")
        return self.adapter(adapter_id)["capabilities"][capability]["supported"]

    def require_capabilities(self, adapter_id: str, required: list[str]) -> dict:
        if type(required) is not list or not required:
            raise ValueError("required_capabilities_invalid")
        if len(required) != len(set(required)):
            raise ValueError("duplicate_required_capability")
        unknown = sorted(set(required) - set(CAPABILITIES))
        if unknown:
            raise ValueError("unknown_capability:" + ",".join(unknown))
        item = self.adapter(adapter_id)
        missing = sorted(
            capability for capability in required
            if not item["capabilities"][capability]["supported"]
        )
        return {
            "adapter_id": adapter_id,
            "required": sorted(required),
            "missing": missing,
            "conformant": not missing,
            "certification_claimed": False,
        }

    def families(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for item in self._registry["adapters"]:
            out.setdefault(item["protocol_family"], []).append(item["adapter_id"])
        return {key: sorted(value) for key, value in sorted(out.items())}
