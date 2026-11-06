"""Verify a bounded audit export against operator-supplied key, policy and checkpoint."""

import hashlib
import hmac
import io
import zipfile

from .audit import GENESIS, mac
from .build import verify_archive
from .codec import Rejected, decode, fields, integer
from .config import validate
from .receipts import hex_digest, verify as verify_receipt


def verify(data, key, policy_digest, checkpoint):
    if not isinstance(key, bytes) or len(key) < 32:
        raise Rejected("audit_key_size")
    hex_digest(policy_digest)
    fields(checkpoint, ("sequence", "head"))
    integer(checkpoint["sequence"], 0, 2**63 - 1)
    hex_digest(checkpoint["head"])
    members = verify_archive(data)
    if set(members) != {"audit.json", "policy.json", "policy.sha3"}:
        raise Rejected("export_membership")
    with zipfile.ZipFile(io.BytesIO(data)) as bundle:
        if bundle.getinfo("audit.json").file_size > 8 * 1024 * 1024:
            raise Rejected("audit_export_size")
        policy_bytes = bundle.read("policy.json")
        if (hashlib.sha3_256(policy_bytes).hexdigest() != policy_digest
                or bundle.read("policy.sha3") != policy_digest.encode("ascii")):
            raise Rejected("export_policy_binding")
        policy = validate(decode(policy_bytes))
        audit = decode(bundle.read("audit.json"), max_bytes=8 * 1024 * 1024, max_nodes=100000)
    fields(audit, ("checkpoint", "records"))
    if type(audit["records"]) is not list or len(audit["records"]) > 10000:
        raise Rejected("audit_export_count")
    previous, sequence, replayed, legacy = GENESIS, 0, 0, 0
    for record in audit["records"]:
        fields(record, ("sequence", "payload", "previous", "mac"))
        integer(record["sequence"], 1, 2**63 - 1)
        hex_digest(record["mac"])
        hex_digest(record["previous"])
        if record["sequence"] != sequence + 1 or record["previous"] != previous:
            raise Rejected("audit_sequence")
        if not isinstance(record["payload"], str) or len(record["payload"]) > 65536:
            raise Rejected("audit_payload")
        expected = mac(key, record["sequence"], previous, record["payload"])
        if not hmac.compare_digest(record["mac"], expected):
            raise Rejected("audit_integrity")
        event = decode(record["payload"].encode())
        if type(event) is not dict:
            raise Rejected("audit_event")
        if event.get("kind") == "decision":
            if "receipt" in event:
                receipt = event["receipt"]
                verify_receipt(receipt, policy, event.get("receipt_sha256"))
                if (event.get("subject") != receipt["subject"] or event.get("asset") != receipt["request"]["asset"]
                        or event.get("request_id") != receipt["request"]["request_id"]
                        or event.get("time") != receipt["facts"]["decided_at"]
                        or event.get("decision") != receipt["outcome"]["decision"]
                        or event.get("reasons") != receipt["outcome"]["reasons"]):
                    raise Rejected("receipt_event_binding")
                replayed += 1
            else:
                legacy += 1
        sequence, previous = record["sequence"], record["mac"]
    actual = {"sequence": sequence, "head": previous}
    if actual != audit["checkpoint"] or actual != checkpoint:
        raise Rejected("audit_checkpoint_mismatch")
    return {"verified": True, "checkpoint": actual, "replayed_decisions": replayed,
            "legacy_unreplayed_decisions": legacy, "policy_digest": policy_digest,
            "scope": "authenticated_records_and_replay_not_external_sensor_attestation"}
