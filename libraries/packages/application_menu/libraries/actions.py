#!/usr/bin/env python3
"""Az'arch application menu -- side-effect actions (launch + session power).

Small, dependency-free helpers the menu calls when the user clicks something:
launching an application detached from the menu, and the four session/power
operations on the bottom bar (Sleep, Lock, Restart, Shut Down).

Everything is fire-and-forget and swallows its own errors: a launcher that
fails must never take the menu (or the session) down with it. Power operations
go through ``systemctl``/``loginctl``/``qdbus6`` -- the same tools Plasma uses --
so they honour the system's logind + polkit policy.
"""

from __future__ import annotations

import os
import shutil
import subprocess


def launch(argv: list[str]) -> None:
    """Start an application detached from the menu process.

    Uses ``setsid`` so the child is fully reparented (survives the menu closing
    immediately after) with stdio detached. Best-effort: never raises.
    """
    if not argv:
        return
    cmd = list(argv)
    if shutil.which("setsid"):
        cmd = ["setsid"] + cmd
    try:
        subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except (OSError, ValueError):
        pass


def _run_detached(argv: list[str]) -> bool:
    """Run a short command detached; return True if it was spawned (not that it
    succeeded -- these hand off to logind and return immediately)."""
    try:
        subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
        return True
    except (OSError, ValueError):
        return False


def _first_available(*commands: list[str]) -> None:
    """Run the first command whose binary exists on PATH."""
    for argv in commands:
        if argv and shutil.which(argv[0]):
            if _run_detached(argv):
                return


# --- Session / power actions ----------------------------------------------
def lock_session() -> None:
    """Lock the screen. Prefer the Plasma/freedesktop screensaver D-Bus call
    (what Kickoff's Lock does), fall back to ``loginctl lock-session``."""
    sid = os.environ.get("XDG_SESSION_ID")
    _first_available(
        ["qdbus6", "org.freedesktop.ScreenSaver", "/ScreenSaver", "Lock"],
        ["loginctl", "lock-session"] + ([sid] if sid else []),
        ["loginctl", "lock-sessions"],
        ["xdg-screensaver", "lock"],
    )


def suspend() -> None:
    """Suspend (Sleep)."""
    _first_available(
        ["systemctl", "suspend"],
        ["loginctl", "suspend"],
    )


def reboot() -> None:
    """Restart."""
    _first_available(
        ["systemctl", "reboot"],
        ["loginctl", "reboot"],
    )


def poweroff() -> None:
    """Shut Down."""
    _first_available(
        ["systemctl", "poweroff"],
        ["loginctl", "poweroff"],
    )
