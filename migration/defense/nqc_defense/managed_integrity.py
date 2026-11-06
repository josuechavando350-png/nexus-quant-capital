"""Local managed JSON protection: sampled observation, incident, admission quarantine and recovery."""

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import secrets
import stat

from .archive_store import ArchiveStore
from .codec import Rejected, canonical, decode, fields
from .consumer import ArtifactReader
from .engine import Engine
from .enroll import enroll
from .files import create_local, read_local, sha256
from .receipts import hex_digest
from .witness import Witness

SCHEMA = "nqc-managed-integrity-v1"
ASSET = "managed-json"


class ManagedIntegrity:
    def __init__(self, root, manifest_digest):
        self.root = Path(root).absolute()
        hex_digest(manifest_digest)
        self.digest = manifest_digest
        self._directories()
        self.manifest = self._manifest()
        self._state_files()
        key = read_local(self.root, "control/ledger.key", 32)
        self.witness = Witness(self.root / "witness", read_local(self.root, "witness.key", 32),
                               key, self.manifest["policy_digest"])
        self.engine = Engine(self.root / "assets", self.root / "control/configs", self.root / "control/state",
                             self.manifest["policy_digest"], key, witness=self.witness)
        self.archive = ArchiveStore(self.root / "archive", self.manifest["archive_budget_digest"])

    @classmethod
    def create(cls, source, root):
        source, root = Path(source).absolute(), Path(root).absolute()
        data = read_local(source.parent, source.name, 1024 * 1024)
        decode(data, max_bytes=1024 * 1024, max_nodes=65536)
        root.mkdir(mode=0o700, parents=False, exist_ok=False)
        for name in ("assets", "baseline"):
            (root / name).mkdir(mode=0o700)
        create_local(root, "assets/artifact.json", data)
        enrolled = enroll(root / "assets", "artifact.json", ASSET, "canary", root / "control")
        canary = read_local(root, "assets/canary", 4096)
        create_local(root, "baseline/artifact.json", data)
        create_local(root, "baseline/canary", canary)
        witness_key = secrets.token_bytes(32)
        create_local(root, "witness.key", witness_key)
        Witness.create(root / "witness", witness_key, read_local(root, "control/ledger.key", 32), enrolled["policy_digest"])
        archive = ArchiveStore.create(root / "archive")
        budget = archive.configure_budget(16 * 1024 * 1024, 1024)
        manifest = {"schema": SCHEMA, "policy_digest": enrolled["policy_digest"],
                    "artifact_sha256": sha256(data), "canary_sha256": sha256(canary),
                    "archive_budget_digest": budget["budget_digest"]}
        encoded = canonical(manifest)
        create_local(root, "managed.json", encoded)
        return cls(root, sha256(encoded))

    def _directories(self):
        for name in ("", "assets", "baseline", "control", "control/state", "control/configs", "witness"):
            info = (self.root / name).lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077:
                raise Rejected("managed_directory_permissions")

    def _state_files(self):
        # Check on every operation as well as reopening; never recreate lost history.
        for name in ("control/state/state.sqlite3", "witness/witness.sqlite3"):
            info = (self.root / name).lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o077:
                raise Rejected("managed_state_permissions")

    def _manifest(self):
        data = read_local(self.root, "managed.json", 4096)
        if sha256(data) != self.digest:
            raise Rejected("managed_manifest_integrity")
        value = decode(data, max_bytes=4096)
        fields(value, ("schema", "policy_digest", "artifact_sha256", "canary_sha256", "archive_budget_digest"))
        if value["schema"] != SCHEMA or canonical(value) != data:
            raise Rejected("managed_manifest_format")
        for name in ("policy_digest", "artifact_sha256", "canary_sha256", "archive_budget_digest"):
            hex_digest(value[name])
        return value

    @contextmanager
    def _operation(self):
        self._directories()
        handle = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise Rejected("managed_operation_busy") from exc
            named, opened = self.root.lstat(), os.fstat(handle)
            if (named.st_dev, named.st_ino) != (opened.st_dev, opened.st_ino):
                raise Rejected("managed_root_changed")
            if self._manifest() != self.manifest:
                raise Rejected("managed_manifest_changed")
            self._state_files()
            self.engine._check_policy()
            yield
        finally:
            os.close(handle)

    def _status(self):
        incident = None
        with self.engine.state.transaction() as db:
            checkpoint = self.engine._verify_ledger(db)
            for sequence, payload in db.execute("SELECT seq,payload FROM audit ORDER BY seq"):
                event = decode(payload.encode())
                if event.get("kind") == "decision" and event.get("asset") == ASSET:
                    recorded = event["receipt"]
                    if recorded["outcome"]["transition"] == "quarantine":
                        incident = {"case_id": event["receipt_sha256"], "asset": ASSET, "status": "open",
                                    "opened_sequence": sequence, "closed_sequence": None,
                                    "reasons": event["reasons"], "receipt_sha256": event["receipt_sha256"]}
                elif event.get("kind") == "operator_release" and event.get("asset") == ASSET and incident:
                    incident.update(status="resolved", closed_sequence=sequence)
            contained = bool(db.execute("SELECT 1 FROM quarantine WHERE asset=?", (ASSET,)).fetchone())
            if contained != bool(incident and incident["status"] == "open"):
                raise Rejected("managed_incident_state_mismatch")
        return {"contained": contained, "incident": incident, "checkpoint": checkpoint,
                "scope": "managed_json_admission_only_not_host_or_process_isolation"}

    def status(self):
        with self._operation():
            return self._status()

    def inspect(self):
        with self._operation():
            existing = self._status()
            if existing["contained"]:
                return {**existing, "observation_performed": False}
            token = self.engine.issue("managed-monitor", ASSET)
            result = self.engine.process(canonical({"asset": ASSET, "request_id": secrets.token_hex(16)}), token)
            if result["decision"] not in ("admit", "quarantined"):
                raise Rejected("managed_inspection_incomplete")
            return {**self._status(), "observation_performed": True, "admission": result}

    def _read(self):
        return ArtifactReader(self.engine).read_json(canonical({"asset": ASSET, "request_id": secrets.token_hex(16)}),
                                                      self.engine.issue("managed-reader", ASSET))

    def read_json(self):
        with self._operation():
            return self._read()

    def recover(self):
        """Operator-only restoration of the two owned files; quarantine survives partial failure."""
        with self._operation():
            before = self._status()
            if not before["contained"]:
                raise Rejected("managed_no_open_incident")
            backups = []
            for name, expected, maximum in (("artifact.json", self.manifest["artifact_sha256"], 1024 * 1024),
                                             ("canary", self.manifest["canary_sha256"], 4096)):
                data = read_local(self.root, "baseline/" + name, maximum)
                if sha256(data) != expected:
                    raise Rejected("managed_baseline_integrity")
                backups.append((name, data))
            parent = os.open(self.root / "assets", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                for name, data in backups:
                    temporary = "restore-" + secrets.token_hex(24)
                    created = False
                    try:
                        try:
                            target = os.stat(name, dir_fd=parent, follow_symlinks=False)
                        except FileNotFoundError:
                            target = None
                        if target is not None and (not stat.S_ISREG(target.st_mode) or target.st_nlink != 1):
                            raise Rejected("managed_restore_target_type")
                        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
                        created = True
                        with os.fdopen(fd, "wb") as stream:
                            stream.write(data)
                            stream.flush()
                            os.fsync(stream.fileno())
                        os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
                        created = False
                        os.fsync(parent)
                    finally:
                        if created:
                            os.unlink(temporary, dir_fd=parent)
            finally:
                os.close(parent)
            self.engine.release(ASSET)  # Re-observe both files and commit release before permitting reads.
            consumed = self._read()
            return {**self._status(), "restored_sha256": consumed["content_sha256"],
                    "read_after_recovery_verified": True, "recovered_case_id": before["incident"]["case_id"]}

    def archive_evidence(self):
        with self._operation():
            target, expected = self.engine.checkpoint(), self.witness.head()
            if target == expected["checkpoint"]:
                return {"archived": False, "reason": "no_new_events", "checkpoint": target}
            result = self.archive.capture(self.engine, self.witness, target, expected)
            return {"archived": True, **result}
