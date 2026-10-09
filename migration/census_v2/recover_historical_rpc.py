#!/usr/bin/env python3
"""Append-only read-only RPC evidence, tied to the authentic 139-event universe.

Every response retains acquisition time. Historical state does not imply that
Nexus observed it before the historical transaction. No financial operations.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ci/nqc-census"))
from rmc016_collect_winner_events import gather, canonical, sha, sortkey
from rmc016_probe_historical_rpc import PROVIDERS
from rmc016_resume_verified_receipts import authenticated_drpc_checkpoint
from rmc016_two_operator_receipts import receipt_normalized

MAX_BYTES = 8_000_000
METHODS = {"eth_chainId", "eth_getBlockByNumber", "eth_getLogs", "eth_getTransactionReceipt"}

def need(ok, message):
    if not ok:
        raise ValueError(message)

def utc():
    return datetime.now(timezone.utc).isoformat()

def distinct(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, "duplicate JSON key")
        result[key] = value
    return result

def decode_response(raw, request_id):
    need(len(raw) <= MAX_BYTES, "response exceeds bound")
    doc = json.loads(raw, object_pairs_hook=distinct)
    need(type(doc) is dict and doc.get("jsonrpc") == "2.0"
         and type(doc.get("id")) is int and doc["id"] == request_id,
         "wrong RPC envelope or request identity")
    need("error" not in doc and "result" in doc, "RPC error: " + str(doc.get("error"))[:250])
    return doc["result"]

class Recorder:
    def __init__(self, provider, out, interval=1.1, opener=urlopen, resume=None):
        need(provider in PROVIDERS and provider[0] in {"drpc", "blockpi"}, "unapproved source")
        need(1 <= interval <= 30, "invalid rate spacing")
        self.provider, self.out, self.interval, self.opener = provider, out, interval, opener
        self.sequence, self.last = 0, 0.0
        self.cached, self.cursor = [], 0
        out.mkdir(parents=True, exist_ok=False)
        if resume is not None:
            ledger = (resume/"rpc/decision-time-ledger.jsonl").read_bytes()
            need(ledger.endswith(b"\n"), "interrupted checkpoint has incomplete ledger row")
            copies = []
            last_received = None
            for i, line in enumerate(ledger.splitlines(), 1):
                row = json.loads(line, object_pairs_hook=distinct)
                need(row["sequence"] == i and row["provider_id"] == provider[0]
                     and row["operator"] == provider[1] and row["url"] == provider[2]
                     and row["status"] == "RESPONSE_CAPTURED" and row["http_status"] == 200,
                     "checkpoint identity/failure mismatch")
                sent, received = datetime.fromisoformat(row["sent_at"]), datetime.fromisoformat(row["received_at"])
                need(sent.tzinfo is not None and received.tzinfo is not None and sent <= received
                     and (last_received is None or last_received <= sent), "checkpoint chronology mismatch")
                last_received = received
                request = (resume/"rpc"/f"{i:06d}.request.json").read_bytes()
                response = (resume/"rpc"/f"{i:06d}.response.json").read_bytes()
                need(sha(request) == row["request_sha256"] and sha(response) == row["response_sha256"],
                     "checkpoint raw bytes corrupted")
                req = json.loads(request, object_pairs_hook=distinct)
                need(req["id"] == i and req["method"] == row["method"]
                     and row["original_decision_time_observation_proven"] is False,
                     "checkpoint request binding mismatch")
                self.cached.append((req, decode_response(response, i)))
                copies.extend([(f"{i:06d}.request.json", request), (f"{i:06d}.response.json", response)])
            for name, raw in copies:
                (out/name).write_bytes(raw)
            (out/"decision-time-ledger.jsonl").write_bytes(ledger)
            self.sequence = len(self.cached)
            (out.parent/"resume-source.json").write_bytes(canonical({
                "source_directory": resume.name, "source_ledger_sha256": sha(ledger),
                "completed_responses_reused": self.sequence,
                "orphan_requests_replayed_as_new_requests": True,
                "original_receipt_times_preserved": True}))

    def __call__(self, url, method, params):
        need(url == self.provider[2] and method in METHODS, "RPC outside read-only scope")
        need(method != "eth_getBlockByNumber" or
             (len(params) == 2 and type(params[0]) is str and params[0].startswith("0x")
              and params[1] is False), "unpinned block request")
        if self.cursor < len(self.cached):
            request, result = self.cached[self.cursor]
            need(request["method"] == method and request["params"] == params, "checkpoint query order differs")
            self.cursor += 1
            return result
        time.sleep(max(0, self.interval - (time.monotonic() - self.last)))
        self.last = time.monotonic()
        self.sequence += 1
        need(self.sequence <= 1200, "request budget exhausted")
        prefix = f"{self.sequence:06d}"
        body = canonical({"jsonrpc": "2.0", "id": self.sequence, "method": method, "params": params})
        (self.out / (prefix + ".request.json")).write_bytes(body)
        entry = {"sequence": self.sequence, "provider_id": self.provider[0], "operator": self.provider[1],
                 "url": url, "method": method, "request_sha256": sha(body), "sent_at": utc(),
                 "original_decision_time_observation_proven": False}
        request = Request(url, data=body, headers={"Content-Type": "application/json",
                          "Accept": "application/json", "User-Agent": "NQC-Census-ReadOnly/2"}, method="POST")
        raw = b""
        try:
            with self.opener(request, timeout=25) as response:
                entry["http_status"] = response.status
                raw = response.read(MAX_BYTES + 1)
                entry["response_headers"] = dict(response.headers)
            entry["received_at"] = utc()
            result = decode_response(raw, self.sequence)
            entry["status"] = "RESPONSE_CAPTURED"
            return result
        except Exception as error:
            if isinstance(error, HTTPError):
                entry["http_status"] = error.code
                entry["response_headers"] = dict(error.headers)
                raw = error.read(MAX_BYTES + 1)
            entry.update(status="FAILED", received_at=utc(), failure_type=type(error).__name__,
                         failure=str(error)[:500])
            raise
        finally:
            entry["response_sha256"] = sha(raw)
            entry["response_size"] = len(raw)
            (self.out / (prefix + ".response.json")).write_bytes(raw)
            with (self.out / "decision-time-ledger.jsonl").open("ab") as stream:
                stream.write(canonical(entry))

def collect(event_zip, checkpoint_zip, out, provider_id, mode, resume=None):
    rows, events, tids = authenticated_drpc_checkpoint(checkpoint_zip, event_zip)
    provider = next(p for p in PROVIDERS if p[0] == provider_id)
    recorder = Recorder(provider, out / "rpc", resume=resume)
    report = {"schema": "nqc-historical-rpc-recovery-v1", "provider_id": provider_id,
              "mode": mode, "started_at": utc(), "status": "INCOMPLETE",
              "source_event_zip_sha256": sha(event_zip.read_bytes()),
              "checkpoint_zip_sha256": sha(checkpoint_zip.read_bytes()),
              "original_decision_time_observation_proven": False,
              "independent_execution_node_proven": False, "real_market_census_closed": False,
              "nexus_capture_proven": False, "nexus_net_pnl_proven": False,
              "verifier_sha256": sha(Path(__file__).read_bytes())}
    try:
        if mode == "logs":
            discovered, observed, _, _ = gather(provider, call=recorder, chunk=1024 if provider_id == "blockpi" else 8192,
                                                call_budget=1200, min_rpc_interval=0)
            (out / "discovery-report.json").write_bytes(canonical(discovered))
            expected = sorted([e for group in events.values() for e in group], key=sortkey)
            need(discovered["coverage_complete"] and observed == expected, "full-window logs differ or incomplete")
            (out / "verified-events.jsonl").write_bytes(b"".join(canonical(e) for e in observed))
            report.update(status="FULL_WINDOW_EVENTS_MATCH", event_count=len(observed), transaction_count=len(tids))
        else:
            report["verified_transaction_count"] = 0
            with (out / "verified-receipts.jsonl").open("xb") as stream:
                for tid in tids:
                    raw = recorder(provider[2], "eth_getTransactionReceipt", [tid])
                    observed = receipt_normalized(tid, events[tid], raw)
                    need(observed == rows[tid], "receipt differs from authenticated checkpoint: " + tid)
                    stream.write(canonical(observed))
                    stream.flush()
                    report["verified_transaction_count"] += 1
                    if report["verified_transaction_count"] % 20 == 0:
                        print(json.dumps({"provider": provider_id, "verified": report["verified_transaction_count"]}), flush=True)
            report.update(status="FULL_RECEIPT_CHECKPOINT_MATCH", gas_paid_wei=str(sum(int(r["total_gas_paid_wei"]) for r in rows.values())))
    except Exception as error:
        report.update(status="BLOCKED", failure_type=type(error).__name__, failure=str(error)[:700])
    finally:
        report.update(finished_at=utc(), rpc_calls=recorder.sequence)
        (out / "recovery-report.json").write_bytes(canonical(report))
        manifest = [{"path": str(p.relative_to(out)), "size": p.stat().st_size, "sha256": sha(p.read_bytes())}
                    for p in sorted(out.rglob("*")) if p.is_file()]
        (out / "manifest.json").write_bytes(canonical(manifest))
    return report

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-zip", required=True, type=Path)
    parser.add_argument("--checkpoint-zip", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--provider", required=True, choices=["drpc", "blockpi"])
    parser.add_argument("--mode", required=True, choices=["logs", "receipts"])
    parser.add_argument("--resume", type=Path)
    args = parser.parse_args()
    need(not args.out.exists(), "output must be new and append-only")
    report = collect(args.event_zip, args.checkpoint_zip, args.out, args.provider, args.mode, args.resume)
    print(json.dumps(report, sort_keys=True))
    return int(report["status"] == "BLOCKED")

if __name__ == "__main__":
    raise SystemExit(main())
