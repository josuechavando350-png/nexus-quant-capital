"""Bounded read-only archive inventory relative to externally pinned selected catalogs."""

from contextlib import ExitStack
import os
import re
import stat

from .archive_coverage import ArchiveCoverage
from .codec import Rejected, canonical, fields
from .files import sha256
from .receipts import hex_digest
from .witness import receipt

SCHEMA = "nqc-archive-inventory-v1"
MAX_SELECTIONS = 32
MAX_OBJECTS = 20000
MAX_OBSERVED_BYTES = 4 * 1024 * 1024 * 1024
MAX_REFERENCE_EDGES = 32768
MAX_SELECTED_PAGES = 16384
MAX_SELECTED_BYTES = 1024 * 1024 * 1024
MAX_REPORT_BYTES = 16 * 1024 * 1024
MAX_SELECTION_BYTES = 65536


def selections(value):
    if type(value) is not list or not 1 <= len(value) <= MAX_SELECTIONS:
        raise Rejected("inventory_selection_limit")
    result, seen = [], set()
    for item in value:
        fields(item, ("catalog_sha256", "start_receipt", "target_receipt"))
        digest = item["catalog_sha256"]
        hex_digest(digest)
        if digest in seen:
            raise Rejected("inventory_duplicate_selection")
        seen.add(digest)
        result.append({"catalog_sha256": digest, "start_receipt": receipt(item["start_receipt"]),
                       "target_receipt": receipt(item["target_receipt"])})
    return sorted(result, key=lambda item: item["catalog_sha256"])


def stamp(value):
    # atime changes caused by this read-only inspection are deliberately excluded.
    return (value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def object_kind(directory, name):
    if directory == "" and name == "archive-budget.json":
        return "control"
    if directory == "" and re.fullmatch(r"coverage-[0-9a-f]{64}\.json", name):
        return "catalog"
    if directory == "manifests" and re.fullmatch(r"[0-9a-f]{64}\.json", name):
        return "manifest"
    if directory == "pages" and re.fullmatch(r"[0-9a-f]{64}\.zip", name):
        return "page"
    if re.fullmatch(r"pending-[0-9a-f]{48}", name):
        return "temporary"
    return "unknown"


def scan_store(store):
    """Inspect only root/pages/manifests using directory descriptors; never recurse."""
    store._check_directories()
    files, directories, total = {}, {}, 0
    try:
        with ExitStack() as stack:
            root = os.open(store.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            stack.callback(os.close, root)
            handles = {"": root}
            for name in ("pages", "manifests"):
                handle = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
                stack.callback(os.close, handle)
                handles[name] = handle
            for directory, handle in handles.items():
                before = os.fstat(handle)
                if not stat.S_ISDIR(before.st_mode) or before.st_mode & 0o077:
                    raise Rejected("inventory_directory_permissions")
                directories[directory] = stamp(before)
                with os.scandir(handle) as entries:
                    for entry in entries:
                        info = entry.stat(follow_symlinks=False)
                        if directory == "" and entry.name in ("pages", "manifests"):
                            if stamp(info) != stamp(os.fstat(handles[entry.name])):
                                raise Rejected("inventory_changed_during_scan")
                            continue
                        if not stat.S_ISREG(info.st_mode):
                            raise Rejected("inventory_entry_type")
                        if info.st_nlink != 1:
                            raise Rejected("inventory_hardlink")
                        if info.st_mode & 0o077:
                            raise Rejected("inventory_file_permissions")
                        if len(files) >= MAX_OBJECTS:
                            raise Rejected("inventory_object_limit")
                        total += info.st_size
                        if total > MAX_OBSERVED_BYTES:
                            raise Rejected("inventory_observed_size_limit")
                        name = directory + "/" + entry.name if directory else entry.name
                        files[name] = {"kind": object_kind(directory, entry.name),
                                       "size_bytes": info.st_size, "stamp": stamp(info)}
                if stamp(os.fstat(handle)) != directories[directory]:
                    raise Rejected("inventory_changed_during_scan")
    except OSError as exc:
        raise Rejected("inventory_scan_unavailable") from exc
    return {"files": files, "directories": directories, "logical_bytes": total}


class ArchiveInventory:
    def __init__(self, store, witness):
        self.coverage = ArchiveCoverage(store, witness)
        self.store, self.witness = store, witness

    def inspect(self, selected):
        selected = selections(selected)
        before = scan_store(self.store)
        objects = before["files"]
        referenced, edges, issues, results = set(), set(), set(), []
        page_reads = page_bytes = 0

        def issue(path, reason):
            issues.add((path, reason))

        def reference(source, target):
            edge = (source, target)
            if edge not in edges and len(edges) >= MAX_REFERENCE_EDGES:
                raise Rejected("inventory_reference_limit")
            edges.add(edge)
            referenced.add(target)
            if target not in objects:
                issue(target, "missing_reference")
                return False
            return True

        for selection in selected:
            digest = selection["catalog_sha256"]
            path = "coverage-" + digest + ".json"
            referenced.add(path)
            result = {**selection, "verified": False}
            results.append(result)
            if path not in objects:
                issue(path, "missing_reference")
                continue
            try:
                catalog = self.coverage._catalog(digest, selection["start_receipt"], selection["target_receipt"])
                # Authenticate independent pins before expanding the selected reference graph.
                self.witness.interval(selection["start_receipt"], selection["target_receipt"])
            except Rejected as exc:
                issue(path, str(exc))
                continue
            candidate = True
            for manifest_digest in catalog["manifests"]:
                manifest_path = "manifests/" + manifest_digest + ".json"
                if not reference(path, manifest_path):
                    candidate = False
                    continue
                try:
                    manifest = self.store._manifest(manifest_digest, self.witness.audit_key, self.witness.policy_digest)
                except Rejected as exc:
                    issue(manifest_path, str(exc))
                    candidate = False
                    continue
                page_reads += len(manifest["pages"])
                page_bytes += sum(item["size_bytes"] for item in manifest["pages"])
                if page_reads > MAX_SELECTED_PAGES or page_bytes > MAX_SELECTED_BYTES:
                    raise Rejected("inventory_verification_limit")
                for page in manifest["pages"]:
                    if not reference(manifest_path, "pages/" + page["sha256"] + ".zip"):
                        candidate = False
            if candidate:
                try:
                    checked = self.coverage.verify_catalog(digest, selection["start_receipt"], selection["target_receipt"])
                except Rejected as exc:
                    issue(path, str(exc))
                    continue
                result.update(verified=True, coverage_inventory_sha256=checked["inventory_sha256"],
                              interval_count=checked["interval_count"], page_count=checked["page_count"],
                              record_count=checked["record_count"])

        # Recheck every pin after all selected catalogs, including overlapping histories.
        for result in results:
            if result["verified"]:
                try:
                    if self.witness.record(result["target_receipt"]["revision"])["receipt"] != result["target_receipt"]:
                        raise Rejected("witness_receipt_mismatch")
                except Rejected as exc:
                    result["verified"] = False
                    issue("coverage-" + result["catalog_sha256"] + ".json", str(exc))
        if scan_store(self.store) != before:
            raise Rejected("inventory_changed_during_scan")
        complete = not issues and all(item["verified"] for item in results)
        entries = [{"path": path, "kind": item["kind"], "size_bytes": item["size_bytes"],
                    "referenced_by_selected": path in referenced if complete else None,
                    "content_verification": "selected_coverage_verified" if complete and path in referenced else "not_verified"}
                   for path, item in sorted(objects.items())]
        summary = {}
        for kind in ("catalog", "manifest", "page", "temporary", "unknown", "control"):
            group = [entry for entry in entries if entry["kind"] == kind]
            summary[kind] = {"objects": len(group), "logical_bytes": sum(entry["size_bytes"] for entry in group),
                             "outside_selected_objects": sum(not entry["referenced_by_selected"] for entry in group) if complete else None,
                             "outside_selected_bytes": sum(entry["size_bytes"] for entry in group if not entry["referenced_by_selected"]) if complete else None}
        value = {"schema": SCHEMA, "verified": complete, "selected_coverage_complete": complete,
                 "reference_classification_available": complete, "selections": results,
                 "policy_digest": self.witness.policy_digest, "audit_key_id": self.witness.audit_key_id,
                 "observed_objects": len(entries), "observed_logical_bytes": before["logical_bytes"],
                 "summary": summary, "entries": entries,
                 "references": [{"source": source, "target": target} for source, target in sorted(edges)],
                 "issues": [{"path": path, "reason": reason} for path, reason in sorted(issues)],
                 "deletion_authorized": False, "unselected_content_verified": False,
                 "metadata_before_after_match": True,
                 "size_accounting": "logical_file_sizes_not_allocated_disk_blocks",
                 "atomic_filesystem_snapshot": False,
                 "scope": "local_metadata_inventory_and_selected_pinned_coverage_not_global_orphan_or_retention_proof"}
        encoded = canonical(value)
        if len(encoded) > MAX_REPORT_BYTES:
            raise Rejected("inventory_report_limit")
        return {**value, "report_sha256": sha256(encoded)}
