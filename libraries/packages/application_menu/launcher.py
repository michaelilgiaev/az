#!/usr/bin/env python3
"""Az'arch application menu -- TOGGLE launcher (INSTANT, via a daemon).

Installed to /usr/local/bin/azarch-application-menu. Bound to the Super key by
OpenBox (see patches/openbox.py) and pointed at by the menu's .desktop
entry -- opening either runs this.

The menu runs as a resident DAEMON (menu built once, kept hidden) so opening it is
instant -- no per-click Python/Tk startup. This launcher just signals the daemon:
  * daemon already running  -> SIGUSR1 = toggle (show if hidden, hide if shown)
  * daemon not running yet   -> start it, wait for it to be ready, SIGUSR2 = show

State is the daemon's PID file under XDG_RUNTIME_DIR. Pure standard library --
no pip packages, no venv (Python is already on the live session).

This is the Python replacement for the old POSIX-sh launcher: Az'arch packages
are all Python, no shell scripts. The daemon-signaling contract (PID file,
SIGUSR1 toggle / SIGUSR2 show) is unchanged, so daemon.py needs no edits.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

# Installed daemon/menu modules. Overridable via AZARCH_MENU_DIR for local testing
# (both daemon.py and menu.py live in the same dir).
MENU_DIR = os.environ.get("AZARCH_MENU_DIR", "/usr/local/lib/azarch-application-menu")
DAEMON_PY = os.environ.get("AZARCH_DAEMON_PY", os.path.join(MENU_DIR, "daemon.py"))

RUNTIME_DIR = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
PID_FILE = os.path.join(RUNTIME_DIR, "azarch-application-menu.pid")


def _read_pid() -> int | None:
    """Return the live daemon PID from the PID file, or None if absent/stale/dead."""
    try:
        pid = int(open(PID_FILE).read().strip())
    except (OSError, ValueError):
        return None
    try:
        os.kill(pid, 0)  # signal 0 = liveness probe, no signal delivered
    except OSError:
        return None
    return pid


def _signal(pid: int, sig: int) -> None:
    """Best-effort signal: a dead/gone daemon must not crash the launcher."""
    try:
        os.kill(pid, sig)
    except OSError:
        pass


def main() -> int:
    if not os.path.isfile(DAEMON_PY):
        print(f"azarch-application-menu: daemon module not found at {DAEMON_PY}",
              file=sys.stderr)
        return 1

    # --- Is the daemon already running? -----------------------------------
    pid = _read_pid()
    if pid is not None:
        # Alive -> toggle it and we're done (instant show/hide inside the daemon).
        _signal(pid, signal.SIGUSR1)
        return 0
    # Stale PID file (daemon gone) -> clean up and start a fresh one below.
    try:
        os.unlink(PID_FILE)
    except OSError:
        pass

    # --- Start the daemon, then show --------------------------------------
    # Detach (start_new_session) so the launcher/panel-icon does not block. The
    # daemon writes its own PID file once its window is built and ready.
    with open(os.devnull, "r+b") as null:
        subprocess.Popen(
            [sys.executable, DAEMON_PY],
            stdin=null, stdout=null, stderr=null, start_new_session=True,
        )

    # Wait (briefly) for the daemon to come up and publish its PID file, then tell
    # it to show. Poll up to ~5s in 50ms steps so a slow first start still works.
    for _ in range(100):
        pid = _read_pid()
        if pid is not None:
            _signal(pid, signal.SIGUSR2)
            return 0
        time.sleep(0.05)

    print("azarch-application-menu: daemon did not come up in time", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
