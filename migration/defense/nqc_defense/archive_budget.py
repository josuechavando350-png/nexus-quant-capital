"""Pinned logical-size budgets for cooperating local archive writers on Linux."""

from contextlib import contextmanager
import fcntl
import os
import stat
import time

from .codec import Rejected, canonical, decode, fields, integer
from .files import open_parent, publish_local, read_local, sha256

SCHEMA = "nqc-archive-budget-v1"
POLICY_FILE = "archive-budget.json"
LOCK_WAIT_SECONDS = 5.0


def limits(max_logical_bytes, max_objects):
    # Reuse the inventory's bounded real-file scanner without introducing an import cycle.
    from .archive_inventory import MAX_OBJECTS, MAX_OBSERVED_BYTES
    integer(max_logical_bytes, 1, MAX_OBSERVED_BYTES)
    integer(max_objects, 1, MAX_OBJECTS)
    return {"schema": SCHEMA, "max_logical_bytes": max_logical_bytes, "max_objects": max_objects}


@contextmanager
def locked(store):
    store._check_directories()
    handle = os.open(store.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise Rejected("archive_writer_busy")
                time.sleep(0.01)
        opened, named = os.fstat(handle), store.root.lstat()
        if ((opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
                or not stat.S_ISDIR(named.st_mode) or named.st_mode & 0o077):
            raise Rejected("archive_lock_identity")
        yield
    finally:
        # Closing releases the kernel lock even when validation or publication fails.
        os.close(handle)


def policy(store, required=False):
    try:
        info = (store.root / POLICY_FILE).lstat()
    except FileNotFoundError:
        if required or store.budget_digest is not None:
            raise Rejected("archive_budget_missing")
        return None
    if store.budget_digest is None:
        raise Rejected("archive_budget_pin_required")
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o077:
        raise Rejected("archive_budget_permissions")
    data = read_local(store.root, POLICY_FILE, 4096)
    if sha256(data) != store.budget_digest:
        raise Rejected("archive_budget_integrity")
    value = decode(data, max_bytes=4096)
    fields(value, ("schema", "max_logical_bytes", "max_objects"))
    expected = limits(value["max_logical_bytes"], value["max_objects"])
    if value != expected or canonical(value) != data:
        raise Rejected("archive_budget_format")
    return value


def usage(store):
    from .archive_inventory import scan_store
    return scan_store(store)


def fits(observed, value, extra_bytes=0, extra_objects=0):
    return (observed["logical_bytes"] + extra_bytes <= value["max_logical_bytes"]
            and len(observed["files"]) + extra_objects <= value["max_objects"])


def sync_existing(root, name, data):
    """Compare and fsync an identical object without creating a temporary copy."""
    if read_local(root, name, len(data)) != data:
        raise Rejected("existing_file_differs")
    parent = handle = None
    try:
        parent, leaf = open_parent(root, name)
        handle = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        info = os.fstat(handle)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size != len(data):
            raise Rejected("archive_existing_changed")
        os.fsync(handle)
        os.fsync(parent)
    finally:
        for descriptor in (handle, parent):
            if descriptor is not None:
                os.close(descriptor)


def publish(store, name, data, publisher=publish_local):
    if not isinstance(data, bytes):
        raise Rejected("file_bytes")
    digest = sha256(data)
    if name not in ("pages/" + digest + ".zip", "manifests/" + digest + ".json", "coverage-" + digest + ".json"):
        raise Rejected("archive_object_name")
    with locked(store):
        value = policy(store)
        if value is None:
            publisher(store.root, name, data)
            return
        before = usage(store)
        if not fits(before, value):
            raise Rejected("archive_budget_exceeded")
        if name in before["files"]:
            sync_existing(store.root, name, data)
        else:
            if not fits(before, value, len(data), 1):
                raise Rejected("archive_budget_exceeded")
            publisher(store.root, name, data)
        # No acknowledgement if storage or the pinned policy changed unexpectedly.
        policy(store, required=True)
        if not fits(usage(store), value):
            raise Rejected("archive_budget_exceeded")


def configure(store, max_logical_bytes, max_objects):
    value = limits(max_logical_bytes, max_objects)
    data, digest = canonical(value), sha256(canonical(value))
    if store.budget_digest is not None and store.budget_digest != digest:
        raise Rejected("archive_budget_pin_conflict")
    with locked(store):
        before = usage(store)
        exists = POLICY_FILE in before["files"]
        if exists and read_local(store.root, POLICY_FILE, 4096) != data:
            raise Rejected("archive_budget_already_configured")
        if not fits(before, value, 0 if exists else len(data), 0 if exists else 1):
            raise Rejected("archive_budget_exceeded")
        if exists:
            sync_existing(store.root, POLICY_FILE, data)
        else:
            publish_local(store.root, POLICY_FILE, data)
        store.budget_digest = digest
        checked = _status(store)
        if not checked["within_budget"]:
            raise Rejected("archive_budget_exceeded")
        return {"configured": True, **checked}


def _status(store):
    value, observed = policy(store, required=True), usage(store)
    return {"verified": True, "budget_digest": store.budget_digest, "limits": value,
            "used_logical_bytes": observed["logical_bytes"], "used_objects": len(observed["files"]),
            "remaining_logical_bytes": max(0, value["max_logical_bytes"] - observed["logical_bytes"]),
            "remaining_objects": max(0, value["max_objects"] - len(observed["files"])),
            "within_budget": fits(observed, value), "deletion_performed": False,
            "scope": "logical_archive_budget_for_cooperating_writers_not_os_disk_quota"}


def status(store):
    with locked(store):
        return _status(store)
