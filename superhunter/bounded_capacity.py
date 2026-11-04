"""Exhaustive checks of a fixed, explicitly finite NQC numerical domain.

This is not model checking of Solidity, an economic-loss estimator, or a proof
of universal security. No user-supplied targets, properties or code execute.
"""
from __future__ import annotations

import hashlib
from itertools import product
from pathlib import Path

from .evidence_links import digest, exact, expected_nqc
from .local_lab import independent_reference
from .native_runtime import load_components, source_inventory
from .safe_io import canonical, read_artifact

DOMAIN = {
    "records": 3, "ids": ["a", "b", "c"], "intervals": [[0, 1], [0, 2], [1, 2]],
    "values": [0, 1], "amounts": [1, 2], "capacity": 2,
    "resource_kind": "PROTOCOL_MARKET_CAP", "resource_id": "bounded-local-fixture",
    "interpretation": "dimensionless synthetic integer units, not USD or blockchain balances",
}
EXPECTED_CASES = 1728


def cases():
    options = list(product(DOMAIN["intervals"], DOMAIN["values"], DOMAIN["amounts"]))
    for sequence in product(options, repeat=3):
        yield [{"opportunity_id": name, "start_order": interval[0], "end_order": interval[1],
                "success_path_value_usd_wad": value,
                "claims": [{"resource_kind": DOMAIN["resource_kind"], "resource_id": DOMAIN["resource_id"],
                            "amount": amount, "capacity": DOMAIN["capacity"]}]}
               for name, (interval, value, amount) in zip(DOMAIN["ids"], sequence)]


def _verifier_sources() -> dict:
    root = Path(__file__).resolve().parent
    return {name: hashlib.sha256(read_artifact(root, name)).hexdigest()
            for name in ("bounded_capacity.py", "evidence_links.py", "local_lab.py")}


def _transcript(*, execute_native: bool) -> tuple[int, str]:
    native = load_components() if execute_native else None
    chain, count = digest(DOMAIN), 0
    for index, rows in enumerate(cases()):
        expected = expected_nqc(rows, independent_reference(rows))
        if native is not None:
            actual = native.capacity.solve(rows)
            exact(actual, expected, f"bounded numerical case {index}")
        else:
            actual = expected  # independent recalculation, not an execution assertion
        chain = digest({"previous": chain, "index": index, "inputs": rows, "result": actual})
        count += 1
    if count != EXPECTED_CASES:
        raise ValueError("finite domain enumeration incomplete")
    return count, chain


def run_bounded() -> dict:
    count, transcript = _transcript(execute_native=True)
    return {
        "schema_version": 1, "status": "FINITE_DOMAIN_CHECK_PASS", "domain": DOMAIN,
        "domain_sha256": digest(DOMAIN), "cases_checked": count,
        "reference_subsets_enumerated": count * 8, "complete_for_declared_domain": True,
        "transcript_sha256": transcript, "native_sources": source_inventory(),
        "verifier_sha256": _verifier_sources(), "universal_security_proof": False,
        "vulnerability_confirmed": False, "producer_authenticated": False,
    }


def verify_bounded(certificate: dict) -> str:
    count, transcript = _transcript(execute_native=False)
    exact(certificate, {
        "schema_version": 1, "status": "FINITE_DOMAIN_CHECK_PASS", "domain": DOMAIN,
        "domain_sha256": digest(DOMAIN), "cases_checked": count,
        "reference_subsets_enumerated": count * 8, "complete_for_declared_domain": True,
        "transcript_sha256": transcript, "native_sources": source_inventory(),
        "verifier_sha256": _verifier_sources(), "universal_security_proof": False,
        "vulnerability_confirmed": False, "producer_authenticated": False,
    }, "finite-domain certificate")
    return digest(certificate)
