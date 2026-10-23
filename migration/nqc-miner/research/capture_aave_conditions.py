#!/usr/bin/env python3
"""Bounded getters for initial conditions at three already retained Aave blocks.

The liquidator is taken retrospectively from each observed event. These inputs
are not prospective predictions or transaction-boundary witnesses.
"""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import time
import urllib.request
import aave_runtime_identity as identity

MODULE = identity.MODULE
spec = importlib.util.spec_from_file_location("proxy_conditions_transport", MODULE / "evidence/aave-proxy-identity-20261023/capture.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
SELECTORS = {"getReserveData": "0x35ea6a75", "getUserConfiguration": "0x4417a583",
             "getLiquidationGracePeriod": "0x5c9a8b18", "getUserAccountData": "0xbf92857c", "balanceOf": "0x70a08231"}
ZERO = "0x" + "00" * 20
JOURNAL_SHA = "9563e32f70ef56fb69ddc04db8164650b184dbc91fd382548345e749409c337b"


def address(value, allow_zero=False):
    probe.check(isinstance(value, str) and re.fullmatch(r"0x[0-9a-f]{40}", value)
                and (allow_zero or value != ZERO), "address")
    return value


def params(name, target, argument, block):
    address(target); address(argument)
    return [{"from": ZERO, "to": target, "value": "0x0", "gas": "0x1e8480",
             "data": SELECTORS[name] + "0" * 24 + argument[2:]},
            {"blockHash": block["hash"], "requireCanonical": True}]


def validate_params(value):
    probe.check(isinstance(value, list) and len(value) == 2, "parameter count")
    call, block = value
    probe.check(isinstance(call, dict) and set(call) == {"from", "to", "value", "gas", "data"}
                and call["from"] == ZERO and call["value"] == "0x0" and call["gas"] == "0x1e8480", "call object")
    address(call["to"])
    data = call["data"]
    probe.check(isinstance(data, str) and re.fullmatch(r"0x[0-9a-f]{72}", data)
                and data[:10] in SELECTORS.values() and data[10:34] == "0" * 24, "selector/ABI")
    address("0x" + data[34:])
    probe.check(isinstance(block, dict) and set(block) == {"blockHash", "requireCanonical"}
                and block["requireCanonical"] is True and isinstance(block["blockHash"], str)
                and re.fullmatch(r"0x[0-9a-f]{64}", block["blockHash"]) and int(block["blockHash"], 16), "block anchor")


def words(value, count, widths=None):
    probe.check(isinstance(value, str) and re.fullmatch(r"0x[0-9a-f]{%d}" % (64 * count), value), "return ABI length/encoding")
    result = [int(value[i:i + 64], 16) for i in range(2, len(value), 64)]
    for item, width in zip(result, widths or [256] * count):
        probe.check(item < 1 << width, "noncanonical ABI width")
    return result


def reserve(value):
    values = words(value, 15, [256,128,128,128,128,128,40,16,160,160,160,160,128,128,128])
    token = address("0x" + format(values[10], "040x"))
    return {"configuration": str(values[0]), "id": values[7], "variable_debt_token": token}


def sources():
    path = MODULE / "evidence/public-capture-v2-20261022/state/events.jsonl"
    probe.check(probe.sha(path.read_bytes()) == JOURNAL_SHA, "journal changed")
    events = [json.loads(line)["record"] for line in path.read_text().splitlines()]
    events = [e for e in events if e["kind"] == "observed"]
    probe.check(len(events) == 3, "source event count")
    result = []
    for i, event in enumerate(events):
        proxy = MODULE / f"evidence/aave-proxy-identity-20261023/public/proxy-{i:03d}.json"
        probe.check(probe.sha(proxy.read_bytes()) == identity.SOURCE_HASHES[i], "identity evidence changed")
        sample = probe.load(proxy)
        probe.check(event["log"]["block_hash"] == sample["event_anchor"]["hash"]
                    and event["scope_id"] == "ethereum-aave-liquidations"
                    and event["log"]["chain_id"] == 1 and event["log"]["address"] == probe.POOL, "event identity")
        result.append({"event": event, "identity": sample})
    return result


class Rpc(probe.Rpc):
    def __call__(self, provider, method, arguments):
        if method != "eth_call":
            probe.check(method in {"eth_chainId", "eth_getBlockByNumber"}, "method")
            return super().__call__(provider, method, arguments)
        probe.check(provider in probe.PROVIDERS, "provider")
        validate_params(arguments)
        time.sleep(max(0, 0.125 - (time.monotonic() - self.last)))
        self.last = time.monotonic(); self.sequence += 1
        request = {"jsonrpc": "2.0", "id": self.sequence, "method": method, "params": arguments}
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        req = urllib.request.Request(probe.PROVIDERS[provider], data=json.dumps(request).encode(),
                                     headers={"Content-Type": "application/json", "User-Agent": "nqc-miner-condition-research"})
        with urllib.request.build_opener(NoRedirect).open(req, timeout=15) as response:
            raw = response.read(65537)
        probe.check(len(raw) <= 65536, "oversize call response")
        value = json.loads(raw)
        probe.check(value.get("jsonrpc") == "2.0" and type(value.get("id")) is int
                    and value["id"] == self.sequence and "result" in value and "error" not in value, "RPC envelope")
        return {"request": request, "response": value}


def capture_one(source, query):
    original, event = source["identity"], source["event"]
    block, anchor = original["block"], original["event_anchor"]
    payload = event["decoded"]["payload"]
    borrower, liquidator = address(payload["borrower"]), address(payload["liquidator"])
    collateral, debt = address(payload["collateral_token"]), address(payload["debt_token"])
    records, observations = [], []

    def read(provider, method, arguments):
        r = query(provider, method, arguments); value = r["response"]["result"]
        if method == "eth_getBlockByNumber":
            value = {k: value[k] for k in ("number", "hash", "parentHash", "timestamp")}
        records.append({"provider_id": provider, "request": r["request"], "response": {**r["response"], "result": value}})
        return value

    def verify(provider, expected):
        probe.check(probe.same(probe.header(read(provider, "eth_getBlockByNumber", [hex(expected["number"]), False])), expected), "header changed")

    for provider in probe.PROVIDERS:
        probe.check(read(provider, "eth_chainId", []) == "0x1", "chain")
        finalized = probe.header(read(provider, "eth_getBlockByNumber", ["finalized", False]))
        probe.check(finalized["number"] >= anchor["number"], "finality")
        verify(provider, block); verify(provider, anchor)
        def call(name, target, arg):
            return read(provider, "eth_call", params(name, target, arg, block))
        cr = reserve(call("getReserveData", probe.POOL, collateral))
        dr = reserve(call("getReserveData", probe.POOL, debt))
        cg = words(call("getLiquidationGracePeriod", probe.POOL, collateral), 1, [40])[0]
        dg = words(call("getLiquidationGracePeriod", probe.POOL, debt), 1, [40])[0]
        uc = words(call("getUserConfiguration", probe.POOL, borrower), 1)[0]
        account = words(call("getUserAccountData", probe.POOL, borrower), 6)
        selected = words(call("balanceOf", dr["variable_debt_token"], borrower), 1)[0]
        observations.append({"borrower": borrower, "liquidator": liquidator,
            "collateral_configuration": cr["configuration"], "debt_configuration": dr["configuration"],
            "collateral_grace_until": cg, "debt_grace_until": dg, "collateral_reserve_id": cr["id"],
            "user_configuration": str(uc), "health_factor_wad": str(account[5]),
            "selected_debt": str(selected), "timestamp": block["timestamp"]})
        verify(provider, block); verify(provider, anchor); verify(provider, finalized)
    probe.check(probe.same(*observations), "decoded provider disagreement")
    # Require complete getter bytes, not just the selected decoded fields.
    calls = [[r["response"]["result"] for r in records if r["provider_id"] == p and r["request"]["method"] == "eth_call"] for p in probe.PROVIDERS]
    probe.check(probe.same(*calls), "getter byte disagreement")
    for provider in probe.PROVIDERS:
        verify(provider, block); verify(provider, anchor)
    return {"schema": "nqc-miner-aave-condition-observation-v1", "block": block, "event_anchor": anchor,
            "event_transaction": event["log"]["transaction_hash"], "event_log_index": event["log"]["log_index"],
            "inputs": observations[0], "records": records, "liquidator_basis": "retrospective_event",
            "debt_basis": "pinned_variable_debt_token_balanceOf_not_authenticated", "state_authenticated": False,
            "transaction_prestate": False, "executable_eligibility_verified": False, "activation_allowed": False}


def replay(directory):
    manifest = probe.load(directory / "manifest.json")
    probe.check(manifest["complete"] is True and manifest["requests"] == 96
                and manifest["capture_sha256"] == probe.sha(Path(__file__).read_bytes()), "capture integrity")
    probe.check(len(manifest["observations"]) == 3, "observation coverage")
    results = []
    for i, (entry, source) in enumerate(zip(manifest["observations"], sources())):
        probe.check(entry["file"] == f"conditions-{i:03d}.json", "capture path")
        path = directory / entry["file"]
        probe.check(probe.sha(path.read_bytes()) == entry["sha256"], "report hash")
        original = probe.load(path); records = iter(original["records"]); count = 0
        def query(provider, method, arguments):
            nonlocal count
            count += 1; r = next(records); request, response = r["request"], r["response"]
            probe.check(r["provider_id"] == provider and request["method"] == method
                        and probe.same(request["params"], arguments), "request mismatch")
            probe.check(request["jsonrpc"] == response["jsonrpc"] == "2.0"
                        and type(request["id"]) is int and type(response["id"]) is int
                        and request["id"] == response["id"] == i * 32 + count and "error" not in response, "response identity")
            return {"request": request, "response": response}
        result = capture_one(source, query)
        probe.check(count == 32 and next(records, None) is None and probe.same(result, original), "replay mismatch")
        results.append(result)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    rpc, entries = Rpc(), []; started = datetime.now(timezone.utc).isoformat()
    for i, source in enumerate(sources()):
        try:
            result = capture_one(source, rpc); name = f"conditions-{i:03d}.json"
            probe.save(args.output / name, result)
            entries.append({"file": name, "sha256": probe.sha((args.output / name).read_bytes())})
        except Exception as error:
            probe.save(args.output / "failure.json", {"index": i, "error_type": type(error).__name__, "complete": False})
            raise
    probe.save(args.output / "manifest.json", {"schema": "nqc-miner-aave-conditions-capture-v1", "complete": True,
        "observations": entries, "requests": rpc.sequence, "capture_sha256": probe.sha(Path(__file__).read_bytes()),
        "started_at_utc": started, "completed_at_utc": datetime.now(timezone.utc).isoformat(), "new_source_events": 0})
    print(json.dumps({"complete": True, "requests": rpc.sequence}))


if __name__ == "__main__":
    main()
