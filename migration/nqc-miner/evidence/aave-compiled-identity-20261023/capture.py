#!/usr/bin/env python3
"""Read six fixed contract runtimes at three already audited historical blocks."""
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
MODULE = ROOT.parents[1]
sys.path.insert(0, str(MODULE / "research"))
import aave_runtime_identity as identity

spec = importlib.util.spec_from_file_location("audited_proxy_capture", ROOT.parent / "aave-proxy-identity-20261023/capture.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
ADDRESSES = [identity.POOL, *identity.LIBRARIES.values()]


def source(index):
    path = ROOT.parent / f"aave-proxy-identity-20261023/public/proxy-{index:03d}.json"
    probe.check(probe.sha(path.read_bytes()) == identity.SOURCE_HASHES[index], "historical source changed")
    return probe.load(path)


def capture_one(original, query):
    block, event = original["block"], original["event_anchor"]
    probe.check(original["implementation"] == identity.POOL and block["number"] + 1 == event["number"]
                and event["parent_hash"] == block["hash"], "historical identity")
    records, runtimes = [], {a: {} for a in ADDRESSES}

    def read(provider, method, params):
        # Extra narrowing over the reused read-only transport: fixed six targets.
        probe.check(method in {"eth_chainId", "eth_getBlockByNumber", "eth_getCode"}, "method")
        if method == "eth_getCode":
            probe.check(params[0] in ADDRESSES and params[1] == {"blockHash": block["hash"], "requireCanonical": True}, "foreign code request")
        result = query(provider, method, params)
        value = result["response"]["result"]
        if method == "eth_getBlockByNumber":
            value = {k: value[k] for k in ("number", "hash", "parentHash", "timestamp")}
        records.append({"provider_id": provider, "request": result["request"],
                        "response": {**result["response"], "result": value}})
        return value

    def verify_header(provider, expected):
        probe.check(probe.same(probe.header(read(provider, "eth_getBlockByNumber", [hex(expected["number"]), False])), expected), "canonical header changed")

    for provider in probe.PROVIDERS:
        probe.check(read(provider, "eth_chainId", []) == "0x1", "chain")
        finalized = probe.header(read(provider, "eth_getBlockByNumber", ["finalized", False]))
        probe.check(finalized["number"] >= event["number"], "finality")
        verify_header(provider, block)
        verify_header(provider, event)
        for address in ADDRESSES:
            value = read(provider, "eth_getCode", [address, {"blockHash": block["hash"], "requireCanonical": True}])
            probe.code_bytes(value)
            runtimes[address][provider] = value
        verify_header(provider, block)
        verify_header(provider, event)
        verify_header(provider, finalized)
    for provider in probe.PROVIDERS:
        verify_header(provider, block)
        verify_header(provider, event)
    for address, responses in runtimes.items():
        probe.check(len(set(responses.values())) == 1, "runtime disagreement")
        if address == identity.POOL:
            probe.check(probe.sha(probe.code_bytes(next(iter(responses.values())))) == original["implementation_runtime_sha256"], "historical implementation changed")
    return {"schema": "nqc-miner-aave-linked-runtimes-v1", "block": block, "event_anchor": event,
            "records": records, "runtimes": runtimes, "state_authentication_verified": False,
            "executable_eligibility_verified": False, "activation_allowed": False}


def replay():
    manifest = probe.load(ROOT / "public/manifest.json")
    probe.check(manifest["complete"] is True and manifest["requests"] == 90, "incomplete capture")
    probe.check(manifest["capture_sha256"] == probe.sha(Path(__file__).read_bytes()), "capture source changed")
    probe.check(len(manifest["observations"]) == 3, "capture count")
    results = []
    for i, entry in enumerate(manifest["observations"]):
        probe.check(entry["file"] == f"runtime-{i:03d}.json", "capture path")
        path = ROOT / "public" / entry["file"]
        probe.check(probe.sha(path.read_bytes()) == entry["sha256"], "capture bytes changed")
        original = probe.load(path)
        records, count = iter(original["records"]), 0

        def replay_record(provider, method, params):
            nonlocal count
            record = next(records)
            count += 1
            request, response = record["request"], record["response"]
            probe.check(record["provider_id"] == provider and request["method"] == method
                        and probe.same(request["params"], params), "request mismatch")
            probe.check(request["jsonrpc"] == response["jsonrpc"] == "2.0"
                        and type(request["id"]) is int and type(response["id"]) is int
                        and request["id"] == response["id"] == i * 30 + count
                        and "error" not in response, "RPC identity/error")
            return {"request": request, "response": response}

        result = capture_one(source(i), replay_record)
        probe.check(next(records, None) is None and count == 30 and probe.same(result, original), "replay mismatch")
        results.append(result)
    return results


def main():
    output = ROOT / "public"
    output.mkdir(exist_ok=False)
    rpc, entries = probe.Rpc(), []
    started = datetime.now(timezone.utc).isoformat()
    for i in range(3):
        try:
            result = capture_one(source(i), rpc)
            filename = f"runtime-{i:03d}.json"
            probe.save(output / filename, result)
            entries.append({"file": filename, "sha256": probe.sha((output / filename).read_bytes())})
        except Exception as error:
            probe.save(output / "failure.json", {"index": i, "error_type": type(error).__name__, "complete": False})
            raise
    probe.save(output / "manifest.json", {"schema": "nqc-miner-aave-library-capture-v1", "complete": True,
         "started_at_utc": started, "completed_at_utc": datetime.now(timezone.utc).isoformat(),
         "capture_sha256": probe.sha(Path(__file__).read_bytes()), "observations": entries, "requests": rpc.sequence,
         "source_hashes": identity.SOURCE_HASHES, "new_source_events": 0, "activation_allowed": False})
    print({"complete": True, "requests": rpc.sequence})


if __name__ == "__main__":
    main()
