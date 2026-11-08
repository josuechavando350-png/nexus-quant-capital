"""Observed lifecycle of one newly created private temporary directory.

For fixed own-process consumers only, not a sandbox or a recovery sweeper.
Never recursively delete a replacement at the root path. Keep a directory FD
open while removing children and reject missing, replaced or reappearing roots.
Absence is an observation at a particular time, not a future guarantee.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat
import tempfile
import time
import uuid


class WorkspaceError(ValueError):
    """Fixed diagnostics without private paths or original exception strings."""


def need(condition: bool, reason: str) -> None:
    if not condition:
        raise WorkspaceError(reason)


def identity(info) -> tuple[int, int]:
    return info.st_dev, info.st_ino


class Workspace:
    """Single-owner context; cleanup errors are never suppressed or retried.

    An excluded root is an input/source/output tree, not a deletion target.
    Only this instance's random child of the system temp directory is owned.
    No finalizer, arbitrary cleanup path, CLI, or orphan-removal API is exposed.
    Same-UID concurrent mutation and a hostile kernel are outside this contract.
    """

    def __init__(self, purpose: str, *, excluded: tuple[Path, ...] = ()):
        need(type(purpose) is str and purpose in ('capture', 'diagnosis', 'verification'),
             'WORKSPACE_PURPOSE')
        need(type(excluded) is tuple and all(isinstance(p, Path) for p in excluded),
             'WORKSPACE_EXCLUSIONS')
        self.purpose = purpose
        self.excluded = tuple(p.resolve() for p in excluded)
        self.path = None
        self.state = 'NEW'
        self.observation = None
        self._parent_fd = self._root_fd = None

    def _close_fds(self) -> None:
        lost = False
        for field, expected_field in (('_root_fd', '_root_identity'),
                                      ('_parent_fd', '_parent_identity')):
            descriptor = getattr(self, field)
            if descriptor is None:
                continue
            setattr(self, field, None)
            try:
                expected = getattr(self, expected_field, None)
                current = identity(os.fstat(descriptor))
                if expected is not None and current != expected:
                    lost = True
                    continue  # Never close an observed replacement descriptor.
                os.close(descriptor)
            except OSError:
                lost = True
                # Still release the other verified descriptor before failing.
        if lost:
            self.state = 'FAILED'
            self.observation = None
            raise WorkspaceError('WORKSPACE_DESCRIPTOR_OWNERSHIP_LOST')

    def _check_identity(self) -> None:
        parent = os.stat(self.path.parent, follow_symlinks=False)
        root = os.stat(self.path.name, dir_fd=self._parent_fd, follow_symlinks=False)
        need(stat.S_ISDIR(parent.st_mode) and identity(parent) == self._parent_identity ==
             identity(os.fstat(self._parent_fd)), 'WORKSPACE_PARENT_CHANGED')
        need(stat.S_ISDIR(root.st_mode) and identity(root) == self._root_identity ==
             identity(os.fstat(self._root_fd)), 'WORKSPACE_IDENTITY_CHANGED')
        need(stat.S_IMODE(root.st_mode) == 0o700 and root.st_uid == os.geteuid(),
             'WORKSPACE_PRIVACY_CHANGED')

    def __enter__(self):
        need(self.state == 'NEW', 'WORKSPACE_SINGLE_USE')
        need(getattr(shutil.rmtree, 'avoids_symlink_attacks', False) is True and hasattr(os, 'O_NOFOLLOW') and
             all(function in os.supports_dir_fd for function in (os.open, os.stat, os.mkdir, os.rmdir, os.unlink)),
             'WORKSPACE_SECURE_IO_REQUIRED')
        self.state = 'ADMITTING'
        created = False
        try:
            parent = Path(tempfile.gettempdir()).absolute()
            need(parent == parent.resolve(), 'WORKSPACE_PARENT_SYMLINK')
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            self._parent_fd = os.open(parent, flags)
            self._parent_identity = identity(os.fstat(self._parent_fd))
            self.path = parent / ('superhunter-' + self.purpose + '-' + uuid.uuid4().hex)
            need(all(not self.path.is_relative_to(p) and not p.is_relative_to(self.path)
                     for p in self.excluded), 'WORKSPACE_EXCLUDED_TREE')
            os.mkdir(self.path.name, 0o700, dir_fd=self._parent_fd)
            created = True
            self._root_identity = identity(os.stat(self.path.name, dir_fd=self._parent_fd,
                                                   follow_symlinks=False))
            self._root_fd = os.open(self.path.name, flags, dir_fd=self._parent_fd)
            self._check_identity()
            self._created_ns = time.monotonic_ns()
            self.state = 'ACTIVE'
            return self
        except BaseException:
            # Admission may have created an empty own directory. Never sweep
            # contents on this path: nonempty or changed identity is retained.
            if created:
                try:
                    current = os.stat(self.path.name, dir_fd=self._parent_fd, follow_symlinks=False)
                    if stat.S_ISDIR(current.st_mode) and identity(current) == getattr(self, '_root_identity', None):
                        os.rmdir(self.path.name, dir_fd=self._parent_fd)
                except OSError:
                    pass
            self.state = 'FAILED'
            self._close_fds()
            raise

    def cleanup(self) -> None:
        if self.state == 'REMOVED':
            return  # A recreated path is not owned by this closed instance.
        need(self.state == 'ACTIVE', 'WORKSPACE_NOT_ACTIVE')
        started = time.monotonic_ns()
        try:
            self._check_identity()
            # Traverse our pinned root, not a potentially replaced root path.
            # shutil supplies fd-based, symlink-safe traversal for descendants.
            for name in os.listdir(self._root_fd):
                info = os.stat(name, dir_fd=self._root_fd, follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    shutil.rmtree(name, dir_fd=self._root_fd)
                else:
                    os.unlink(name, dir_fd=self._root_fd)
            self._check_identity()
            os.rmdir(self.path.name, dir_fd=self._parent_fd)
            try:
                os.stat(self.path.name, dir_fd=self._parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise WorkspaceError('WORKSPACE_REAPPEARED')
            self.state = 'REMOVED'
            self.observation = {
                'profile': 'owned-temporary-lifecycle-v1', 'purpose': self.purpose,
                'created_monotonic_ns': self._created_ns,
                'cleanup_started_monotonic_ns': started,
                'cleanup_finished_monotonic_ns': time.monotonic_ns(),
                'path_absent_after_cleanup': True, 'future_absence_proved': False,
                'host_isolation_proved': False,
            }
        except BaseException as error:
            self.state = 'FAILED'
            self.observation = None
            if isinstance(error, OSError):
                raise WorkspaceError('WORKSPACE_CLEANUP_FAILED') from error
            raise
        finally:
            self._close_fds()

    def confirm_removed(self) -> None:
        need(self.state == 'REMOVED', 'WORKSPACE_NOT_REMOVED')
        need(not os.path.lexists(self.path), 'WORKSPACE_REAPPEARED')

    def __exit__(self, exception_type, exception, traceback):
        self.cleanup()
        self.confirm_removed()
        return False
