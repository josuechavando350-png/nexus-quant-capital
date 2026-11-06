"""Shared authentication and receipt checks for full and paginated audit exports."""

import hmac

from .audit import GENESIS, mac
from .codec import Rejected, decode, fields, integer
from .receipts import hex_digest, verify as verify_receipt


def checkpoint(value):
    fields(value, ("sequence", "head"))
    integer(value["sequence"], 0, 2**63 - 1)
    hex_digest(value["head"])
    if value["sequence"] == 0 and value["head"] != GENESIS:
        raise Rejected("audit_checkpoint_mismatch")
    return dict(value)


def record_event(record, key):
    fields(record, ("sequence", "payload", "previous", "mac"))
    integer(record["sequence"], 1, 2**63 - 1)
    hex_digest(record["mac"])
    hex_digest(record["previous"])
    if not isinstance(record["payload"], str):
        raise Rejected("audit_payload")
    try:
        payload_bytes = record["payload"].encode("utf-8")
    except UnicodeEncodeError as exc:
        raise Rejected("audit_payload") from exc
    if len(payload_bytes) > 65536:
        raise Rejected("audit_payload")
    expected = mac(key, record["sequence"], record["previous"], record["payload"])
    if not hmac.compare_digest(record["mac"], expected):
        raise Rejected("audit_integrity")
    event = decode(payload_bytes)
    if type(event) is not dict:
        raise Rejected("audit_event")
    return event


def decision(event, policy):
    receipt = event["receipt"]
    verify_receipt(receipt, policy, event.get("receipt_sha256"))
    if (event.get("subject") != receipt["subject"] or event.get("asset") != receipt["request"]["asset"]
            or event.get("request_id") != receipt["request"]["request_id"]
            or event.get("time") != receipt["facts"]["decided_at"]
            or event.get("decision") != receipt["outcome"]["decision"]
            or event.get("reasons") != receipt["outcome"]["reasons"]):
        raise Rejected("receipt_event_binding")


def event_counts(event, policy, policy_digest, previous_event):
    """Return replayed decisions, legacy decisions and snapshots for this record only."""
    if event.get("kind") == "decision":
        if "receipt" in event:
            decision(event, policy)
            return 1, 0, 0
        return 0, 1, 0
    if event.get("kind") != "snapshot_authorized":
        return 0, 0, 0
    fields(event, ("kind", "time", "subject", "request_id", "asset", "receipt_sha256",
                   "policy_digest", "sha256", "size_bytes"))
    integer(event["size_bytes"], 0, 16 * 1024 * 1024)
    hex_digest(event["sha256"])
    if (previous_event is None or previous_event.get("kind") != "decision"
            or previous_event.get("decision") != "admit" or "receipt" not in previous_event):
        raise Rejected("snapshot_without_admission")
    # A page boundary supplies authenticated context, which still needs semantic replay.
    decision(previous_event, policy)
    for field in ("time", "subject", "request_id", "asset", "receipt_sha256"):
        if event[field] != previous_event.get(field):
            raise Rejected("snapshot_receipt_binding")
    observations = previous_event["receipt"]["facts"]["observations"]
    if (event["policy_digest"] != policy_digest or not observations
            or observations[0]["error"] is not None or event["sha256"] != observations[0]["sha256"]):
        raise Rejected("snapshot_content_binding")
    return 0, 0, 1
