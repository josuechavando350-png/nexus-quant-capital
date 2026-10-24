#!/usr/bin/env python3
"""One bounded research capture of ERC-1967 identities at three retained blocks.

This is a separate evidence probe, not a new method exposed by the Miner CLI.
No signing, broadcast, mutable state calls, overrides, credentials or fallback.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.request

MODULE = Path(__file__).resolve().parents[2]
SLOT = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
POOL = "0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2"
PROVIDERS = {"ethereum-primary": "https://ethereum-rpc.publicnode.com",
             "ethereum-secondary": "https://eth.drpc.org/"}
MAX_CODE = 65536


def check(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def same(a, b):
    return json.dumps(a, sort_keys=True, separators=(",", ":")) == json.dumps(b, sort_keys=True, separators=(",", ":"))


def load(path):
    raw = path.read_bytes()
    check(len(raw) <= 2 * 1024 * 1024 and not path.is_symlink(), "invalid source file")
    return json.loads(raw)


def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def implementation(word):
    check(isinstance(word, str) and re.fullmatch(r"0x[0-9a-f]{64}", word), "storage word")
    check(word[2:26] == "0" * 24 and int(word, 16) != 0, "unsupported empty/beacon/non-address slot")
    return "0x" + word[26:]


def code_bytes(value):
    check(isinstance(value, str) and len(value) <= 2 + MAX_CODE * 2
          and re.fullmatch(r"0x(?:[0-9a-f]{2})+", value), "missing/malformed/oversize runtime")
    return bytes.fromhex(value[2:])


def header(raw):
    check(isinstance(raw, dict), "missing header")
    result = {}
    for k in ("number", "timestamp"):
        text = raw.get(k)
        check(isinstance(text, str) and re.fullmatch(r"0x(?:0|[1-9a-f][0-9a-f]*)", text), "header quantity")
        result[k] = int(text, 16)
    for source, target in (("hash", "hash"), ("parentHash", "parent_hash")):
        text = raw.get(source)
        check(isinstance(text, str) and re.fullmatch(r"0x[0-9a-f]{64}", text) and int(text, 16) != 0, "header hash")
        result[target] = text
    return result


class Rpc:
    def __init__(self):
        self.sequence = 0
        self.last = 0

    def __call__(self, provider, method, params):
        # The probe supplies only the following fixed requests to known public endpoints.
        check(provider in PROVIDERS and method in
              {"eth_chainId", "eth_getBlockByNumber", "eth_getStorageAt", "eth_getCode"}, "method/provider")
        if method in {"eth_getStorageAt", "eth_getCode"}:
            check(isinstance(params, list) and len(params) == (3 if method == "eth_getStorageAt" else 2), "parameter count")
            check(isinstance(params[0], str) and re.fullmatch(r"0x[0-9a-f]{40}", params[0]) and int(params[0], 16), "address")
            anchor = params[-1]
            check(isinstance(anchor, dict) and set(anchor) == {"blockHash", "requireCanonical"}
                  and anchor["requireCanonical"] is True
                  and re.fullmatch(r"0x[0-9a-f]{64}", anchor["blockHash"])
                  and int(anchor["blockHash"], 16), "unpinned request")
            if method == "eth_getStorageAt":
                check(params[0] == POOL and params[1] == SLOT, "foreign proxy/slot")
        elif method == "eth_chainId":
            check(params == [], "chain parameters")
        else:
            check(len(params) == 2 and params[1] is False and isinstance(params[0], str)
                  and (params[0] == "finalized" or re.fullmatch(r"0x[1-9a-f][0-9a-f]*", params[0])), "header parameters")
        time.sleep(max(0, 0.125 - (time.monotonic() - self.last)))
        self.last = time.monotonic()
        self.sequence += 1
        request = {"jsonrpc": "2.0", "id": self.sequence, "method": method, "params": params}
        req = urllib.request.Request(PROVIDERS[provider], data=json.dumps(request).encode(),
                                     headers={"Content-Type": "application/json", "User-Agent": "nqc-miner-read-only-research"})
        # No retry or fallback. Redirects are rejected to keep the provider binding fixed.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        with urllib.request.build_opener(NoRedirect).open(req, timeout=15) as response:
            raw = response.read(1024 * 1024 + 1)
        check(len(raw) <= 1024 * 1024, "oversize response")
        value = json.loads(raw)
        check(value.get("jsonrpc") == "2.0" and type(value.get("id")) is int
              and value["id"] == self.sequence and "error" not in value and "result" in value, "RPC envelope")
        return {"request": request, "response": value}


def capture_one(source, query):
    plan = source["plan"]
    check(source["schema"] == "nqc-miner-aave-state-v1" and source["owner"]["data_class"] == "historical", "source class")
    check(plan["scope_id"] == "ethereum-aave-liquidations", "source scope")
    block, event = source["samples"][-1]["block"], source["event_anchor"]
    check(block["number"] + 1 == event["number"] and event["parent_hash"] == block["hash"], "source anchor")
    records = []

    def read(provider, method, params):
        result = query(provider, method, params)
        value = result["response"]["result"]
        # Header projections are sufficient for this bounded comparison, not
        # cryptographic header validation. Contract/slot bytes remain complete.
        if method == "eth_getBlockByNumber":
            value = {k: value[k] for k in ("number", "hash", "parentHash", "timestamp")}
        records.append({"provider_id": provider, "request": result["request"],
                        "response": {**result["response"], "result": value}})
        return value

    identities = []
    for provider in PROVIDERS:
        check(read(provider, "eth_chainId", []) == "0x1", "wrong chain")
        finalized = header(read(provider, "eth_getBlockByNumber", ["finalized", False]))
        check(finalized["number"] >= event["number"], "not finalized")
        check(same(header(read(provider, "eth_getBlockByNumber", [hex(block["number"]), False])), block), "source block changed")
        check(same(header(read(provider, "eth_getBlockByNumber", [hex(event["number"]), False])), event), "source event changed")
        anchor = {"blockHash": block["hash"], "requireCanonical": True}
        word = read(provider, "eth_getStorageAt", [POOL, SLOT, anchor])
        target = implementation(word)
        proxy = code_bytes(read(provider, "eth_getCode", [POOL, anchor]))
        runtime = code_bytes(read(provider, "eth_getCode", [target, anchor]))
        identities.append({"implementation": target, "slot_word": word, "proxy_runtime_sha256": sha(proxy),
                           "implementation_runtime_sha256": sha(runtime), "proxy_bytes": len(proxy), "implementation_bytes": len(runtime)})
        check(same(header(read(provider, "eth_getBlockByNumber", [hex(block["number"]), False])), block), "block changed during reads")
        check(same(header(read(provider, "eth_getBlockByNumber", [hex(event["number"]), False])), event), "event changed during reads")
        check(same(header(read(provider, "eth_getBlockByNumber", [hex(finalized["number"]), False])), finalized), "finality anchor changed")
    check(same(identities[0], identities[1]), "proxy/runtime disagreement")
    # Recheck after both providers, not just after each provider's own calls.
    for provider in PROVIDERS:
        check(same(header(read(provider, "eth_getBlockByNumber", [hex(block["number"]), False])), block), "final source block changed")
        check(same(header(read(provider, "eth_getBlockByNumber", [hex(event["number"]), False])), event), "final event block changed")
    return {"schema": "nqc-miner-aave-proxy-observation-v1", "block": block, "event_anchor": event,
            "pool": POOL, "implementation_slot": SLOT, **identities[0], "records": records,
            "state_authentication_verified": False, "implementation_source_match_verified": False,
            "protocol_version": None, "executable_eligibility_verified": False, "activation_allowed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.absolute()
    check(not any(p.is_symlink() for p in (output, *output.parents)), "output symlink")
    output.mkdir(mode=0o700, exist_ok=False)
    rpc, results = Rpc(), []
    started = datetime.now(timezone.utc).isoformat()
    for i in range(3):
        source = MODULE / f"evidence/aave-state-public-attempt-20261023/history-{i:03d}/read-state.stdout"
        before = sha(source.read_bytes())
        try:
            report = capture_one(load(source), rpc)
            check(before == sha(source.read_bytes()), "source changed")
            report.update(source_report=str(source.relative_to(MODULE)), source_report_sha256=before)
            name = f"proxy-{i:03d}.json"
            save(output / name, report)
            results.append({"file": name, "sha256": sha((output / name).read_bytes()),
                            "implementation": report["implementation"], "block": report["block"]["number"]})
        except Exception as error:
            # Retain the failure class without endpoint or request credentials.
            save(output / "failure.json", {"index": i, "error_type": type(error).__name__, "complete": False})
            raise SystemExit("proxy research capture failed; incomplete evidence retained") from None
    save(output / "manifest.json", {"schema": "nqc-miner-aave-proxy-capture-v1", "started_at_utc": started,
         "completed_at_utc": datetime.now(timezone.utc).isoformat(), "complete": True, "observations": results,
         "requests": rpc.sequence, "capture_sha256": sha(Path(__file__).read_bytes()), "new_source_events": 0,
         "state_authentication_verified": False, "implementation_source_match_verified": False,
         "economic_certification": False, "observer_bridge_enabled": False, "activation_allowed": False})
    print(json.dumps({"complete": True, "requests": rpc.sequence, "observations": results}))


if __name__ == "__main__":
    main()
