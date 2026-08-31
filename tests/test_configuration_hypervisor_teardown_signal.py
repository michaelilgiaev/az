"""Ctrl-C teardown must KILL the VM, never hang -- the fix for the stuck-process bug.

THE BUG: pressing Ctrl-C on `hypervisor run` (with a shared folder) left the whole
thing STOPPED in the background -- QEMU survived as an unreaped zombie and the CLI
never exited. ROOT CAUSE: cleanup() (run from the SIGINT handler) calls `sudo pkill`
to reap the root virtiofsd daemon. Ctrl-C hands terminal foreground away from the
process group, so sudo's attempt to read a password off the controlling tty raised
SIGTTIN/SIGTTOU, whose default action STOPS the process group mid-cleanup (observed
live as WCHAN=do_signal_stop with a [sudo] <defunct> child). Even without the stop,
an interactive sudo would block forever on a password that never comes.

THE FIX: every sudo reachable from cleanup() is non-interactive -- `sudo -n` (never
prompt) with stdin=DEVNULL (no controlling tty to read). It then either succeeds on
the still-cached timestamp from the boot-time sudo, or fails INSTANTLY; teardown can
neither block nor be stopped. These tests pin that wiring so it cannot regress.
"""

from __future__ import annotations

import subprocess
import types

import pytest

from hypervisor_helpers import make_cfg

from packages.hypervisor import virtual_machine as vm


def _cfg(tmp_path, **overrides):
    return make_cfg(str(tmp_path), **overrides)


class _DeadProc:
    """A child that is already gone: poll() -> 0, kill()/wait() are no-ops."""

    def __init__(self, argv, **kw):
        self.argv = argv

    def poll(self):
        return 0

    def kill(self):
        pass

    def wait(self, timeout=None):
        return 0


def _run_launch_capturing_sudo(tmp_path, monkeypatch, **cfg_overrides):
    """Drive vm._launch through to teardown with everything faked, and return the
    list of (argv, kwargs) for every subprocess.run call so the test can inspect
    how the cleanup-path sudo commands were invoked."""
    runs: list[tuple[list, dict]] = []

    def fake_run(argv, **kw):
        runs.append((list(argv), kw))
        return types.SimpleNamespace(returncode=1)  # 1 == "not cached" worst case

    # No real tty in the test runner; keep the terminal helpers inert.
    monkeypatch.setattr(vm.sys.stdin, "isatty", lambda: False, raising=False)
    monkeypatch.setattr(vm.os.path, "exists", lambda p: True)  # spice sock "appears"
    monkeypatch.setattr(vm, "_spawn_virtiofsd", lambda cfg: _DeadProc(["virtiofsd"]))
    monkeypatch.setattr(vm, "_maximize_window", lambda *a, **k: None)
    monkeypatch.setattr(vm.subprocess, "Popen", lambda argv, **kw: _DeadProc(argv, **kw))
    monkeypatch.setattr(vm.subprocess, "run", fake_run)
    monkeypatch.setattr(
        vm.configuration_watcher, "ConfigWatcher",
        lambda *a, **k: types.SimpleNamespace(start=lambda: None, stop=lambda: None),
    )

    # shared=True so cleanup() exercises the virtiofsd `sudo pkill` reaping path.
    cfg = _cfg(tmp_path, shared=True, ssh=False, **cfg_overrides)
    vm._launch(cfg, ["qemu-system-x86_64"], port=None)
    return runs


def _sudo_calls(runs):
    return [(argv, kw) for argv, kw in runs if argv and argv[0] == "sudo"]


def test_cleanup_sudo_is_noninteractive(tmp_path, monkeypatch):
    # The core guarantee: any sudo cleanup() runs must pass -n so it NEVER prompts
    # for a password (an interactive prompt is what got the process group stopped).
    runs = _run_launch_capturing_sudo(tmp_path, monkeypatch)
    sudos = _sudo_calls(runs)
    assert sudos, "expected cleanup() to attempt a `sudo pkill` for the virtiofsd daemon"
    for argv, _kw in sudos:
        assert "-n" in argv, (
            "cleanup() sudo must be non-interactive (`sudo -n`) so Ctrl-C teardown "
            f"cannot block or be stopped on a password prompt; got: {argv}"
        )


def test_cleanup_sudo_never_reads_the_terminal(tmp_path, monkeypatch):
    # Belt-and-braces: even with -n, hand sudo /dev/null for stdin so it has NO
    # controlling terminal to read -- this is what actually prevents SIGTTIN/SIGTTOU
    # from stopping the process group during teardown.
    runs = _run_launch_capturing_sudo(tmp_path, monkeypatch)
    sudos = _sudo_calls(runs)
    assert sudos
    for argv, kw in sudos:
        assert kw.get("stdin") is subprocess.DEVNULL, (
            "cleanup() sudo must be spawned with stdin=DEVNULL so it cannot be "
            f"stopped by a tty read during teardown; got stdin={kw.get('stdin')!r} for {argv}"
        )


def test_cleanup_reaps_virtiofsd_by_socket(tmp_path, monkeypatch):
    # Regression guard on WHAT is killed: the root daemon is matched by its socket
    # path, so the correct VM's daemon (and only it) is reaped.
    runs = _run_launch_capturing_sudo(tmp_path, monkeypatch)
    cfg = _cfg(tmp_path, shared=True)
    pkills = [argv for argv, _ in _sudo_calls(runs) if "pkill" in argv]
    assert any(cfg.virtiofs_sock in " ".join(argv) for argv in pkills), (
        "cleanup() must reap the virtiofsd daemon by its per-VM socket path"
    )
