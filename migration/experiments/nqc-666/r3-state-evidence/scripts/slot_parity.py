"""Check slot derivation against pinned upstream Solidity in an in-memory EVM."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys

from eth.chains.base import MiningChain
from eth.db.atomic import AtomicDB
from eth.vm.forks.paris import ParisVM
from eth_hash.auto import keccak

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from state_evidence import slots


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--solc", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    assert hashlib.sha256(a.solc.read_bytes()).hexdigest() == "7a5c1d3dc9a8eba62bb2ec37192c9178ae5fe8a54a56e5573fd3c9c17cd9eb48"
    ref = ROOT / "reference"
    paths = ["SlotHarness.sol", "upstream/src/interfaces/IMorpho.sol",
             "upstream/src/libraries/periphery/MorphoStorageLib.sol"]
    inp = {"language": "Solidity", "sources": {k: {"content": (ref / k).read_text()} for k in paths},
           "settings": {"optimizer": {"enabled": True, "runs": 200}, "evmVersion": "paris",
                        "outputSelection": {"SlotHarness.sol": {"SlotHarness": ["evm.deployedBytecode.object"]}}}}
    build = json.loads(subprocess.check_output([str(a.solc), "--standard-json"], input=json.dumps(inp).encode()))
    assert not [x for x in build.get("errors", []) if x["severity"] == "error"]
    (a.out / "compiler.json").write_text(json.dumps(build, indent=2) + "\n")
    code = bytes.fromhex(build["contracts"]["SlotHarness.sol"]["SlotHarness"]["evm"]["deployedBytecode"]["object"])
    Chain = MiningChain.configure(__name__="Nqc666Slots", vm_configuration=((0, ParisVM),))
    vm = Chain.from_genesis(AtomicDB(), {"difficulty": 0, "gas_limit": 30000000, "timestamp": 1}).get_vm()
    rng = random.Random(666303)
    rows = [(b"\0" * 32, b"\0" * 20), (b"\xff" * 32, b"\xff" * 20)]
    rows += [(rng.randbytes(32), rng.randbytes(20)) for _ in range(512)]
    results = []
    for market, borrower in rows:
        calldata = keccak(b"slots(bytes32,address)")[:4] + market + borrower.rjust(32, b"\0")
        addr = b"\1" * 20
        c = vm.execute_bytecode(origin=addr, gas_price=0, gas=1000000, to=addr, sender=addr,
                                value=0, data=calldata, code=code)
        expected = b"".join(v.to_bytes(32, "big") for v in slots(market, borrower).values())
        assert not c.is_error and c.output == expected
        results.append({"market": market.hex(), "borrower": borrower.hex(), "slots": expected.hex()})
    (a.out / "cases.json").write_text(json.dumps(results, indent=2) + "\n")
    result = {"cases": len(results), "slots_compared": len(results) * 9, "equal": True,
              "scope": "PURE_UPSTREAM_SLOT_LIBRARY_NOT_MORPHO_RUNTIME_OR_FORK",
              "runtime_sha256": hashlib.sha256(code).hexdigest()}
    (a.out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
