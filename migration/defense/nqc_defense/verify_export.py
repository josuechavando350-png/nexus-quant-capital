"""Verify a bounded audit export against operator-supplied key, policy and checkpoint."""

import hashlib
import io
import zipfile

from .audit import GENESIS
from .audit_verification import event_counts, record_event
from .build import verify_archive
from .codec import Rejected, decode, fields, integer
from .config import validate
from .receipts import hex_digest


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
    previous, sequence, replayed, legacy, snapshots = GENESIS, 0, 0, 0, 0
    previous_event = None
    for record in audit["records"]:
        event = record_event(record, key)
        if record["sequence"] != sequence + 1 or record["previous"] != previous:
            raise Rejected("audit_sequence")
        counts = event_counts(event, policy, policy_digest, previous_event)
        replayed += counts[0]
        legacy += counts[1]
        snapshots += counts[2]
        sequence, previous = record["sequence"], record["mac"]
        previous_event = event
    actual = {"sequence": sequence, "head": previous}
    if actual != audit["checkpoint"] or actual != checkpoint:
        raise Rejected("audit_checkpoint_mismatch")
    return {"verified": True, "checkpoint": actual, "replayed_decisions": replayed,
            "authorized_snapshots": snapshots,
            "legacy_unreplayed_decisions": legacy, "policy_digest": policy_digest,
            "scope": "authenticated_records_and_replay_not_external_sensor_attestation"}
