"""Exclusive supervision of fixed local QA/OWNED subprocesses on Linux.

Observe exit with WNOWAIT, then stop the owned session group, then reap its
leader. Do not release the leader PID before group cleanup. Detached sessions,
aggregate budgets and OS sandboxing are outside this helper's guarantees.
Callers provide fixed internal commands; this module has no CLI.
"""
from __future__ import annotations

import math
import os
import signal
import subprocess
import sys
import time


class OwnedProcessError(ValueError):
    """Fixed diagnostics without commands, environment values or private paths."""


def _peek(process):
    # This module is the exclusive waiter for the child it launches. WNOWAIT
    # preserves a terminated leader until group cleanup has completed.
    info = os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    if info is not None and info.si_pid != process.pid:
        raise OwnedProcessError('OWNED_CHILD_IDENTITY_MISMATCH')
    return info


def _stop_and_reap(process) -> None:
    try:
        _peek(process)
    except ChildProcessError:
        # An unexpected external waiter/auto-reaper invalidates PID ownership.
        # Never signal a numeric group after losing that ownership evidence.
        process.wait()
        raise OwnedProcessError('OWNED_CHILD_OWNERSHIP_LOST') from None
    except BaseException:
        # With no verified group identity, stop only the Popen-owned leader.
        try:
            process.kill()
        finally:
            process.wait()
        raise
    try:
        if os.getpgid(process.pid) != process.pid or os.getsid(process.pid) != process.pid:
            raise OwnedProcessError('OWNED_SESSION_IDENTITY_MISMATCH')
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    except BaseException:
        process.kill()  # Stop only our leader if group cleanup fails; never claim success.
        raise
    finally:
        process.wait()


def run(command, *, cwd, env, timeout, stdout, stderr, pass_fds=()):
    """Launch a new session and clean its group on every exit before reaping.

    The worker sets its existing CPU/address-space/file limits. Output streams
    remain caller-owned; callers must enforce their existing byte limits.
    """
    if (sys.platform != 'linux' or not all(hasattr(os, n) for n in
            ('waitid', 'P_PID', 'WEXITED', 'WNOHANG', 'WNOWAIT'))):
        raise OwnedProcessError('LINUX_WAITID_REQUIRED')
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 180:
        raise OwnedProcessError('OWNED_WALL_BUDGET')
    deadline = time.monotonic() + timeout
    process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                               stdout=stdout, stderr=stderr, pass_fds=pass_fds,
                               start_new_session=True)
    try:
        while True:
            info = _peek(process)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            if info is not None:
                break
            time.sleep(min(0.01, remaining))
    finally:
        _stop_and_reap(process)
    return subprocess.CompletedProcess(command, process.returncode)
