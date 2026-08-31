"""is_running() must NOT count a <defunct> zombie as a live VM -- the fix for the
false "VM already running" refusal.

THE BUG: after a crash/hard teardown, QEMU can linger as a zombie ([<PROC> <defunct>])
until its parent reaps it. is_running() ran `pgrep -x PROC`, which MATCHES a zombie
(the kernel keeps its comm), so `hypervisor run`/`install` refused with "VM already
running" against a process that is actually DEAD -- exactly what a stale teardown left
behind. Seen live as `pgrep -x azarch-vm` matching `[azarch-vm] <defunct>`.

THE FIX: `pgrep -x -r DRST PROC` -- match only live run states (Disk-sleep, Running,
Sleeping, sTopped) and EXCLUDE Z (zombie). A stopped (T) VM still counts (it holds
resources); a zombie holds nothing and must not.
"""

from __future__ import annotations

import ctypes
import os
import time

import pytest

from hypervisor_helpers import make_cfg

from packages.hypervisor import checks


def _spawn_zombie_with_comm(name: str) -> int:
    """Fork a child that sets its comm to EXACTLY `name` (prctl PR_SET_NAME, capped
    at 15 chars like the kernel) then exits WITHOUT being reaped -> a real <defunct>
    zombie whose comm still matches `pgrep -x name`. Returns the zombie's pid; the
    caller MUST os.waitpid() it to reap. Faithfully mirrors the QEMU teardown case."""
    pid = os.fork()
    if pid == 0:  # child
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        PR_SET_NAME = 15
        buf = ctypes.create_string_buffer(name.encode()[:15], 16)
        libc.prctl(PR_SET_NAME, ctypes.cast(buf, ctypes.c_void_p), 0, 0, 0)
        os._exit(0)
    # parent: give the child a moment to rename + exit, then it is a zombie
    time.sleep(0.3)
    return pid


def test_is_running_false_for_a_zombie(tmp_path):
    cfg = make_cfg(str(tmp_path), vm="zombvm")  # cfg.proc == "zombvm-vm"
    zpid = _spawn_zombie_with_comm(cfg.proc)
    try:
        # Sanity: it really is a zombie whose comm matches cfg.proc.
        with open(f"/proc/{zpid}/stat", encoding="ascii") as fh:
            state = fh.read().split(") ", 1)[1].split(" ", 1)[0]
        assert state == "Z", f"probe did not become a zombie (state={state!r})"
        assert checks.is_running(cfg) is False, (
            "is_running() counted a <defunct> zombie as a live VM -- it must not; "
            "a zombie is a dead process awaiting reaping, holding no resources"
        )
    finally:
        os.waitpid(zpid, 0)  # reap the zombie so the test leaves nothing behind


def test_is_running_false_when_nothing_matches(tmp_path):
    cfg = make_cfg(str(tmp_path), vm="nosuchvm")
    assert checks.is_running(cfg) is False
