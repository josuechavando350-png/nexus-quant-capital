"""Verify persisted intervals continuously between independently supplied witness receipts."""

from .archive_store import match_witness_record
from .codec import Rejected, canonical, decode, fields
from .files import publish_local, read_local, sha256
from .receipts import hex_digest
from .witness import MAX_WITNESS_INTERVAL, receipt

SCHEMA = "nqc-archive-coverage-v1"
MAX_CATALOG_BYTES = 256 * 1024
MAX_COVERAGE_PAGES = 16384
MAX_COVERAGE_BYTES = 1024 * 1024 * 1024


def manifest_list(value):
    if type(value) is not list or len(value) > MAX_WITNESS_INTERVAL:
        raise Rejected("coverage_manifest_limit")
    for digest in value:
        hex_digest(digest)
    if len(set(value)) != len(value):
        raise Rejected("coverage_duplicate_manifest")
    return list(value)


class ArchiveCoverage:
    def __init__(self, store, witness):
        store._separate_from(witness.root)
        self.store, self.witness = store, witness

    def verify(self, manifests, start, target):
        manifests, start, target = manifest_list(manifests), receipt(start), receipt(target)
        records = self.witness.interval(start, target)
        current = start
        intervals, pages, total_bytes, total_records = [], 0, 0, 0
        for index, digest in enumerate(manifests):
            if index >= len(records):
                raise Rejected("coverage_target_exceeded")
            manifest = self.store._manifest(digest, self.witness.audit_key, self.witness.policy_digest)
            if manifest["start"]["sequence"] > current["checkpoint"]["sequence"]:
                raise Rejected("coverage_gap")
            if manifest["start"]["sequence"] < current["checkpoint"]["sequence"]:
                raise Rejected("coverage_overlap")
            if manifest["start"] != current["checkpoint"]:
                raise Rejected("coverage_checkpoint_conflict")
            if manifest["target"]["sequence"] > target["checkpoint"]["sequence"]:
                raise Rejected("coverage_target_exceeded")
            matched = match_witness_record(records[index], manifest, current)
            pages += len(manifest["pages"])
            total_bytes += sum(item["size_bytes"] for item in manifest["pages"])
            if pages > MAX_COVERAGE_PAGES or total_bytes > MAX_COVERAGE_BYTES:
                raise Rejected("coverage_size_limit")
            observed_bytes = sum(len(data) for data in self.store._verified_pages(manifest, self.witness.audit_key))
            total_records += manifest["records"]
            intervals.append({"manifest_sha256": digest, "witness_revision": matched["revision"],
                              "start": manifest["start"], "checkpoint": manifest["target"],
                              "pages": len(manifest["pages"]), "records": manifest["records"],
                              "stored_page_bytes": observed_bytes})
            current = matched
        if current != target or len(manifests) != len(records):
            raise Rejected("coverage_incomplete")
        if total_records != target["checkpoint"]["sequence"] - start["checkpoint"]["sequence"]:
            raise Rejected("coverage_record_count")
        # Later appends are allowed; rollback or a changed pinned target during I/O is not.
        if self.witness.record(target["revision"])["receipt"] != target:
            raise Rejected("witness_receipt_mismatch")
        inventory = {"policy_digest": self.witness.policy_digest, "audit_key_id": self.witness.audit_key_id,
                     "start_receipt": start, "target_receipt": target, "intervals": intervals}
        return {"verified": True, "complete": True, "from_genesis": start["checkpoint"]["sequence"] == 0,
                **inventory, "interval_count": len(intervals), "page_count": pages,
                "record_count": total_records, "stored_page_bytes": total_bytes,
                "inventory_sha256": sha256(canonical(inventory)),
                "scope": "local_contiguous_archive_coverage_at_check_time_not_future_availability"}

    def seal(self, manifests, start, target):
        manifests, start, target = manifest_list(manifests), receipt(start), receipt(target)
        self.verify(manifests, start, target)
        value = {"schema": SCHEMA, "policy_digest": self.witness.policy_digest,
                 "audit_key_id": self.witness.audit_key_id, "start_receipt": start,
                 "target_receipt": target, "manifests": manifests}
        data = canonical(value)
        if len(data) > MAX_CATALOG_BYTES:
            raise Rejected("coverage_catalog_size")
        digest = sha256(data)
        # The root already exists in 0.6.0; no directory or database migration is needed.
        publish_local(self.store.root, "coverage-" + digest + ".json", data)
        return self.verify_catalog(digest, start, target)

    def verify_catalog(self, digest, start, target):
        hex_digest(digest)
        start, target = receipt(start), receipt(target)
        self.store._check_directories()
        data = read_local(self.store.root, "coverage-" + digest + ".json", MAX_CATALOG_BYTES)
        if sha256(data) != digest:
            raise Rejected("coverage_catalog_integrity")
        value = decode(data, max_bytes=MAX_CATALOG_BYTES, max_nodes=4096)
        fields(value, ("schema", "policy_digest", "audit_key_id", "start_receipt", "target_receipt", "manifests"))
        if canonical(value) != data:
            raise Rejected("coverage_catalog_encoding")
        if (value["schema"] != SCHEMA or value["policy_digest"] != self.witness.policy_digest
                or value["audit_key_id"] != self.witness.audit_key_id):
            raise Rejected("coverage_catalog_binding")
        if receipt(value["start_receipt"]) != start or receipt(value["target_receipt"]) != target:
            raise Rejected("coverage_catalog_anchor_mismatch")
        return {**self.verify(value["manifests"], start, target), "catalog_sha256": digest}
