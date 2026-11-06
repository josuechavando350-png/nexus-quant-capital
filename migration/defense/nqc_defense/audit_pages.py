"""Bounded, resumable audit exports between caller-pinned checkpoints."""

import hashlib
import io
import zipfile

from .audit import GENESIS
from .audit_verification import checkpoint, event_counts, record_event
from .build import archive, verify_archive
from .codec import Rejected, canonical, decode, fields, integer
from .config import validate
from .receipts import hex_digest

MAX_PAGE_BYTES = 1024 * 1024
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024
MAX_RECORDS = 512
SCHEMA = "nqc-audit-page-v1"


def as_record(row):
    return dict(zip(("sequence", "payload", "previous", "mac"), row))


def anchored_row(db, anchor):
    if anchor["sequence"] == 0:
        return None
    row = db.execute("SELECT seq,payload,previous,mac FROM audit WHERE seq=?", (anchor["sequence"],)).fetchone()
    if row is None or row[3] != anchor["head"]:
        raise Rejected("audit_anchor_unavailable")
    return as_record(row)


def export_page(db, policy, policy_digest, start, target, limit=256, max_bytes=MAX_PAGE_BYTES):
    """Called inside an engine transaction after its complete ledger verification."""
    start, target = checkpoint(start), checkpoint(target)
    integer(limit, 1, MAX_RECORDS)
    integer(max_bytes, 1024, MAX_PAGE_BYTES)
    if start["sequence"] > target["sequence"]:
        raise Rejected("audit_page_range")
    predecessor = anchored_row(db, start)
    anchored_row(db, target)
    page = {"schema": SCHEMA, "start": start, "target": target, "end": start,
            "predecessor": predecessor, "records": []}
    records, record_bytes = [], 0
    rows = db.execute("SELECT seq,payload,previous,mac FROM audit WHERE seq>? AND seq<=? ORDER BY seq LIMIT ?",
                      (start["sequence"], target["sequence"], limit))
    for row in rows:
        record = as_record(row)
        end = {"sequence": record["sequence"], "head": record["mac"]}
        # Exact serialized length without repeatedly encoding the accumulated records.
        record_size = len(canonical(record))
        candidate_bytes = len(canonical({**page, "end": end})) + record_bytes + record_size + len(records)
        if candidate_bytes > max_bytes:
            break
        records.append(record)
        record_bytes += record_size
        page["end"] = end
    page["records"] = records
    if not records and start != target:
        raise Rejected("audit_page_no_progress")
    encoded = canonical(page)
    if len(encoded) > max_bytes:
        raise Rejected("audit_page_size")
    return archive({"page.json": encoded, "policy.json": canonical(policy),
                    "policy.sha3": policy_digest.encode("ascii")})


def verify_page(data, key, policy_digest, start, target):
    """Verify one interval. A complete history requires contiguous pages from genesis."""
    if not isinstance(key, bytes) or len(key) < 32:
        raise Rejected("audit_key_size")
    hex_digest(policy_digest)
    start, target = checkpoint(start), checkpoint(target)
    if start["sequence"] > target["sequence"]:
        raise Rejected("audit_page_range")
    if not isinstance(data, bytes) or len(data) > MAX_ARCHIVE_BYTES:
        raise Rejected("audit_page_size")
    members = verify_archive(data)
    if set(members) != {"page.json", "policy.json", "policy.sha3"}:
        raise Rejected("export_membership")
    with zipfile.ZipFile(io.BytesIO(data)) as bundle:
        if bundle.getinfo("page.json").file_size > MAX_PAGE_BYTES:
            raise Rejected("audit_page_size")
        policy_bytes = bundle.read("policy.json")
        if (hashlib.sha3_256(policy_bytes).hexdigest() != policy_digest
                or bundle.read("policy.sha3") != policy_digest.encode("ascii")):
            raise Rejected("export_policy_binding")
        policy = validate(decode(policy_bytes))
        page = decode(bundle.read("page.json"), max_bytes=MAX_PAGE_BYTES, max_nodes=8192)
    fields(page, ("schema", "start", "target", "end", "predecessor", "records"))
    if page["schema"] != SCHEMA:
        raise Rejected("audit_page_version")
    for name in ("start", "target", "end"):
        checkpoint(page[name])
    if page["start"] != start or page["target"] != target:
        raise Rejected("audit_page_anchor_mismatch")
    if not start["sequence"] <= page["end"]["sequence"] <= target["sequence"]:
        raise Rejected("audit_page_range")
    if type(page["records"]) is not list or len(page["records"]) > MAX_RECORDS:
        raise Rejected("audit_page_count")
    previous_event = None
    predecessor = page["predecessor"]
    if start["sequence"] == 0:
        if predecessor is not None:
            raise Rejected("audit_page_context")
    else:
        previous_event = record_event(predecessor, key)
        if predecessor["sequence"] != start["sequence"] or predecessor["mac"] != start["head"]:
            raise Rejected("audit_page_context")
    current = start
    replayed = legacy = snapshots = 0
    for record in page["records"]:
        event = record_event(record, key)
        if record["sequence"] != current["sequence"] + 1 or record["previous"] != current["head"]:
            raise Rejected("audit_sequence")
        counts = event_counts(event, policy, policy_digest, previous_event)
        replayed += counts[0]
        legacy += counts[1]
        snapshots += counts[2]
        current = {"sequence": record["sequence"], "head": record["mac"]}
        previous_event = event
    if not page["records"] and start != target:
        raise Rejected("audit_page_no_progress")
    if current != page["end"] or (current["sequence"] == target["sequence"] and current != target):
        raise Rejected("audit_checkpoint_mismatch")
    return {"verified": True, "start": start, "checkpoint": current, "target": target,
            "complete": current == target, "record_count": len(page["records"]),
            "replayed_decisions": replayed, "legacy_unreplayed_decisions": legacy,
            "authorized_snapshots": snapshots, "policy_digest": policy_digest,
            "scope": "authenticated_interval_not_prior_history_or_external_sensor_attestation"}


class AuditPageVerifier:
    """Consume consecutive pages with bounded memory and require the pinned final head."""

    def __init__(self, key, policy_digest, target, start=None):
        if not isinstance(key, bytes) or len(key) < 32:
            raise Rejected("audit_key_size")
        hex_digest(policy_digest)
        self.key, self.policy_digest = key, policy_digest
        self.target = checkpoint(target)
        self.start = checkpoint(start if start is not None else {"sequence": 0, "head": GENESIS})
        if self.start["sequence"] > self.target["sequence"]:
            raise Rejected("audit_page_range")
        self.current = dict(self.start)
        self.pages = self.records = self.replayed = self.legacy = self.snapshots = 0
        self.complete = False

    def accept(self, data):
        if self.complete:
            raise Rejected("audit_page_already_complete")
        result = verify_page(data, self.key, self.policy_digest, self.current, self.target)
        # Advance only after every structural, authentication and replay check passes.
        self.current = dict(result["checkpoint"])
        self.pages += 1
        self.records += result["record_count"]
        self.replayed += result["replayed_decisions"]
        self.legacy += result["legacy_unreplayed_decisions"]
        self.snapshots += result["authorized_snapshots"]
        self.complete = result["complete"]
        return result

    def finish(self):
        if not self.complete:
            raise Rejected("audit_pages_incomplete")
        return {"verified": True, "complete": True, "from_genesis": self.start["sequence"] == 0,
                "start": dict(self.start), "checkpoint": dict(self.current), "pages": self.pages,
                "record_count": self.records, "replayed_decisions": self.replayed,
                "legacy_unreplayed_decisions": self.legacy, "authorized_snapshots": self.snapshots,
                "policy_digest": self.policy_digest,
                "scope": "contiguous_authenticated_interval_not_external_sensor_attestation"}
