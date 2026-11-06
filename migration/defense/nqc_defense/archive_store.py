"""Fsynced local audit pages, immutable manifests and recoverable witness finalization."""

import os
from pathlib import Path
import stat

from .audit import key_id
from .audit_pages import AuditPageVerifier, MAX_ARCHIVE_BYTES
from .audit_verification import checkpoint
from .codec import Rejected, canonical, decode, fields, integer
from .files import publish_local, read_local, sha256
from .receipts import hex_digest
from .witness import SCHEMA as WITNESS_SCHEMA, page_chain_start, page_chain_step, receipt

SCHEMA = "nqc-audit-archive-v1"
MAX_PAGES = 4096
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024


def match_witness_record(record, manifest, expected):
    event = {"schema": WITNESS_SCHEMA, "policy_digest": manifest["policy_digest"],
             "audit_key_id": manifest["audit_key_id"], "start": manifest["start"],
             "checkpoint": manifest["target"], "pages": len(manifest["pages"]),
             "records": manifest["records"], "page_chain_sha256": manifest["page_chain_sha256"]}
    if (record["receipt"]["revision"] != expected["revision"] + 1
            or record["previous"] != expected["head"] or record["event"] != event):
        raise Rejected("archive_witness_binding")
    return record["receipt"]


class ArchiveStore:
    def __init__(self, root):
        self.root = Path(root).absolute()
        self._check_directories()

    @classmethod
    def create(cls, root):
        root = Path(root).absolute()
        root.mkdir(mode=0o700, parents=False, exist_ok=False)
        (root / "pages").mkdir(mode=0o700)
        (root / "manifests").mkdir(mode=0o700)
        for path in (root / "pages", root / "manifests", root, root.parent):
            fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        return cls(root)

    def _check_directories(self):
        for path in (self.root, self.root / "pages", self.root / "manifests"):
            try:
                mode = path.lstat().st_mode
            except OSError as exc:
                raise Rejected("archive_store_unavailable") from exc
            if not stat.S_ISDIR(mode) or mode & 0o077:
                raise Rejected("archive_store_permissions")

    def _separate_from(self, other):
        left, right = self.root.resolve(), Path(other).resolve()
        if left == right or left in right.parents or right in left.parents:
            raise Rejected("archive_store_overlap")

    def prepare(self, pages, audit_key, policy_digest, start, target):
        """Seal only a complete interval. Failures may leave unreferenced immutable pages."""
        self._check_directories()
        start, target = checkpoint(start), checkpoint(target)
        if target["sequence"] <= start["sequence"]:
            raise Rejected("archive_empty_interval")
        verifier = AuditPageVerifier(audit_key, policy_digest, target, start)
        identity = key_id(audit_key)
        chain = page_chain_start(policy_digest, identity, start, target)
        entries, total = [], 0
        for data in pages:
            if len(entries) >= MAX_PAGES:
                raise Rejected("archive_page_limit")
            verifier.accept(data)
            total += len(data)
            if total > MAX_TOTAL_BYTES:
                raise Rejected("archive_total_size")
            digest = sha256(data)
            name = "pages/" + digest + ".zip"
            publish_local(self.root, name, data)
            stored = read_local(self.root, name, MAX_ARCHIVE_BYTES)
            if sha256(stored) != digest or len(stored) != len(data):
                raise Rejected("archive_page_integrity")
            chain = page_chain_step(chain, stored)
            entries.append({"sha256": digest, "size_bytes": len(stored)})
        summary = verifier.finish()
        manifest = {"schema": SCHEMA, "policy_digest": policy_digest, "audit_key_id": identity,
                    "start": start, "target": target, "pages": entries,
                    "records": summary["record_count"], "page_chain_sha256": chain.hex()}
        data = canonical(manifest)
        if len(data) > MAX_MANIFEST_BYTES:
            raise Rejected("archive_manifest_size")
        digest = sha256(data)
        publish_local(self.root, "manifests/" + digest + ".json", data)
        # Reopen the manifest and every stored page before reporting the prepared archive.
        return self.verify(digest, audit_key, policy_digest)

    def _manifest(self, digest, audit_key, policy_digest):
        self._check_directories()
        hex_digest(digest)
        hex_digest(policy_digest)
        if not isinstance(audit_key, bytes) or len(audit_key) < 32:
            raise Rejected("audit_key_size")
        data = read_local(self.root, "manifests/" + digest + ".json", MAX_MANIFEST_BYTES)
        if sha256(data) != digest:
            raise Rejected("archive_manifest_integrity")
        manifest = decode(data, max_bytes=MAX_MANIFEST_BYTES, max_nodes=20000)
        fields(manifest, ("schema", "policy_digest", "audit_key_id", "start", "target", "pages", "records", "page_chain_sha256"))
        if canonical(manifest) != data:
            raise Rejected("archive_manifest_encoding")
        if (manifest["schema"] != SCHEMA or manifest["policy_digest"] != policy_digest
                or manifest["audit_key_id"] != key_id(audit_key)):
            raise Rejected("archive_manifest_binding")
        start, target = checkpoint(manifest["start"]), checkpoint(manifest["target"])
        integer(manifest["records"], 1, 2**63 - 1)
        hex_digest(manifest["page_chain_sha256"])
        if target["sequence"] - start["sequence"] != manifest["records"]:
            raise Rejected("archive_manifest_range")
        if type(manifest["pages"]) is not list or not 1 <= len(manifest["pages"]) <= MAX_PAGES:
            raise Rejected("archive_page_limit")
        total = 0
        for item in manifest["pages"]:
            fields(item, ("sha256", "size_bytes"))
            hex_digest(item["sha256"])
            total += integer(item["size_bytes"], 1, MAX_ARCHIVE_BYTES)
        if total > MAX_TOTAL_BYTES:
            raise Rejected("archive_total_size")
        return manifest

    def _verified_pages(self, manifest, audit_key):
        verifier = AuditPageVerifier(audit_key, manifest["policy_digest"], manifest["target"], manifest["start"])
        chain = page_chain_start(manifest["policy_digest"], manifest["audit_key_id"], manifest["start"], manifest["target"])
        for item in manifest["pages"]:
            self._check_directories()
            data = read_local(self.root, "pages/" + item["sha256"] + ".zip", MAX_ARCHIVE_BYTES)
            if len(data) != item["size_bytes"] or sha256(data) != item["sha256"]:
                raise Rejected("archive_page_integrity")
            verifier.accept(data)
            chain = page_chain_step(chain, data)
            yield data
        summary = verifier.finish()
        if summary["record_count"] != manifest["records"] or chain.hex() != manifest["page_chain_sha256"]:
            raise Rejected("archive_transcript_mismatch")

    def verify(self, manifest_digest, audit_key, policy_digest):
        manifest = self._manifest(manifest_digest, audit_key, policy_digest)
        stored_bytes = sum(len(data) for data in self._verified_pages(manifest, audit_key))
        return {"verified": True, "manifest_sha256": manifest_digest, "start": manifest["start"],
                "checkpoint": manifest["target"], "pages": len(manifest["pages"]),
                "record_count": manifest["records"], "stored_page_bytes": stored_bytes,
                "page_chain_sha256": manifest["page_chain_sha256"],
                "scope": "local_files_reopened_and_verified_at_check_time_not_future_availability"}

    def _match_witness(self, witness, manifest, expected):
        record = witness.record(expected["revision"] + 1)
        return match_witness_record(record, manifest, expected)

    def finalize(self, witness, manifest_digest, expected):
        """Reread stored pages before advancing; recover an identical committed attempt."""
        self._separate_from(witness.root)
        expected = receipt(expected)
        manifest = self._manifest(manifest_digest, witness.audit_key, witness.policy_digest)
        if manifest["start"] != expected["checkpoint"]:
            raise Rejected("archive_witness_start")
        current = witness.head()
        recovered = current != expected
        stored_bytes = sum(item["size_bytes"] for item in manifest["pages"])
        if not recovered:
            try:
                acknowledged = witness.advance(self._verified_pages(manifest, witness.audit_key), manifest["target"], expected)
            except Rejected as exc:
                if str(exc) != "witness_receipt_mismatch":
                    raise
                recovered = True
        if recovered:
            # A concurrent or previously committed attempt is acceptable only for this exact transcript.
            acknowledged = self._match_witness(witness, manifest, expected)
            stored_bytes = sum(len(data) for data in self._verified_pages(manifest, witness.audit_key))
        bound = self._match_witness(witness, manifest, expected)
        if bound != acknowledged:
            raise Rejected("archive_witness_binding")
        return {"manifest_sha256": manifest_digest, "witness_receipt": acknowledged,
                "recovered_existing_commit": recovered, "stored_pages_verified": True,
                "stored_page_bytes": stored_bytes,
                "scope": "local_verified_archive_and_witness_not_independent_replication"}

    def capture(self, engine, witness, target, expected, limit=256):
        """Connect real engine export, persistent archive and checkpoint advancement."""
        self._separate_from(engine.state.root)
        self._separate_from(witness.root)
        witness.bind_engine(engine.state.root, engine.digest, engine.ledger.key)
        expected = receipt(expected)
        target = checkpoint(target)
        def pages():
            cursor = AuditPageVerifier(engine.ledger.key, engine.digest, target, expected["checkpoint"])
            while not cursor.complete:
                data = engine.export_page(cursor.current, target, limit=limit)
                cursor.accept(data)
                yield data
        prepared = self.prepare(pages(), engine.ledger.key, engine.digest, expected["checkpoint"], target)
        return self.finalize(witness, prepared["manifest_sha256"], expected)
