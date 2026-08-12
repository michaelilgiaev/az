"""patches.gimp -- preload GIMP so it opens INSTANTLY and CLEANLY, and re-warm after close.

Why these tests matter: the preload leans on GIMP being single-instance (a warm instance a
later open reuses). It must be silent (--no-splash + welcome/tips off), keep the warm window
mapped-but-off-screen (NOT iconic -- iconic caused the transparent-middle bug), re-warm after
close (a supervise loop, not `exec`), and open via a wrapper that surfaces the warm window.
openbox.py must keep that window unfocused + off the taskbar/pager (via the shared WM_CLASS
constant). A drift in any of those breaks "instant", "clean", "silent" or "re-warms".
"""

from __future__ import annotations

from patches import gimp
from patches import openbox


def test_emit_plan_has_all_six_pieces():
    plan = gimp.emit_plan()
    dests = {e["dest"] for e in plan}
    assert gimp.WINMOVE_HELPER_PATH in dests
    assert gimp.PRELOAD_HELPER_PATH in dests
    assert gimp.OPEN_WRAPPER_PATH in dests
    assert gimp.AUTOSTART_DESKTOP_PATH in dests
    assert gimp.GIMP_GIMPRC_PATH in dests
    assert gimp.GIMP_DESKTOP_PATH in dests
    assert len(plan) == 6


def test_home_helpers_are_executable_home_owned():
    for path in (gimp.WINMOVE_HELPER_PATH, gimp.PRELOAD_HELPER_PATH, gimp.OPEN_WRAPPER_PATH):
        entry = next(e for e in gimp.emit_plan() if e["dest"] == path)
        assert entry["mode"] == 0o755          # scripts must be executable
        assert entry["owner"] == "home"


def test_gimprc_and_autostart_are_home_conf():
    for path in (gimp.GIMP_GIMPRC_PATH, gimp.AUTOSTART_DESKTOP_PATH):
        entry = next(e for e in gimp.emit_plan() if e["dest"] == path)
        assert entry["mode"] == 0o644
        assert entry["owner"] == "home"


def test_desktop_override_is_root_system_file():
    entry = next(e for e in gimp.emit_plan() if e["dest"] == gimp.GIMP_DESKTOP_PATH)
    assert entry["owner"] == "root"
    assert gimp.GIMP_DESKTOP_PATH == "/usr/share/applications/gimp.desktop"


def test_home_dests_live_under_home():
    for entry in gimp.emit_plan():
        if entry["owner"] == "home":
            assert entry["dest"].startswith(gimp.HOME + "/"), entry["dest"]
    assert gimp.AUTOSTART_DESKTOP_PATH.endswith("/.config/autostart/azarch-gimp-preload.desktop")
    # The gimprc must land in the REAL 3.2 config dir (3.0 is ignored by GIMP 3.2.4).
    assert gimp.GIMP_GIMPRC_PATH == "/home/main/.config/GIMP/3.2/gimprc"


def test_gimprc_disables_welcome_and_tips():
    # --no-splash does NOT hide the "Welcome to GIMP 3.2.4"/tips dialogs; the gimprc must.
    out = gimp.gimprc()
    assert "(show-welcome-dialog no)" in out
    assert "(show-tips no)" in out


def test_preload_is_a_rewarm_loop_not_exec():
    # Re-warm on close needs a supervise loop (launch -> wait -> relaunch), NOT `exec` (which
    # would leave nothing to relaunch). It must warm the same binary silently, hide the window
    # off-screen, wait on the process, and settle before relaunch.
    out = gimp.preload_helper_sh()
    assert out.startswith("#!/bin/sh\n")
    assert gimp.GIMP_BINARY == "gimp-3.2"
    assert "--no-splash" in out
    assert "exec " not in out                          # a bare `exec gimp` would break re-warm
    assert 'while :; do' in out or "while :" in out     # the supervise loop
    assert 'wait "$gpid"' in out                        # waits for real exit
    assert f'"{gimp.WINMOVE_HELPER_PATH}" hide' in out  # hides the warm window off-screen
    assert f"pgrep -x {gimp.GIMP_BINARY}" in out        # settle before relaunch
    # Guarded: do nothing if GIMP is missing (defensive).
    assert f"command -v {gimp.GIMP_BINARY}" in out


def test_open_wrapper_surfaces_the_warm_window_then_presents():
    # The wrapper the launcher runs: bring the warm window on-screen, then let gimp-3.2
    # present/raise it (single-instance) -- instant + clean.
    out = gimp.open_wrapper_sh()
    assert f'"{gimp.WINMOVE_HELPER_PATH}" show' in out
    assert f'exec {gimp.GIMP_BINARY} "$@"' in out


def test_desktop_exec_uses_the_wrapper():
    out = gimp.desktop_entry()
    assert out.splitlines()[0] == "[Desktop Entry]"
    assert f"Exec={gimp.OPEN_WRAPPER_PATH} %U" in out
    assert "StartupWMClass=gimp" in out


def test_winmove_helper_is_shipped_verbatim_and_x11_only():
    # The hide/show helper uses ONLY libX11 via ctypes (no xdotool/wmctrl dependency).
    out = gimp.winmove_helper_py()
    assert out.startswith("#!/usr/bin/env python3")
    assert "ctypes" in out
    assert "libX11" in out or "find_library" in out
    assert '"hide"' in out and '"show"' in out
    # No dependency on external window tools.
    assert "xdotool" not in out and "wmctrl" not in out


def test_openbox_parks_the_preloaded_gimp_offscreen_not_iconic():
    # The "out of the way" half lives in openbox.py: the warm window is kept unfocused and
    # off the taskbar/pager, but NOT <iconic> (iconic/unmapped caused the transparent middle;
    # the preload hides it off-screen instead). The rule must use gimp.py's shared match.
    rc = openbox.openbox_rc_xml()
    assert gimp.GIMP_WM_CLASS_MATCH == "gimp*"
    assert f'<application name="{gimp.GIMP_WM_CLASS_MATCH}">' in rc
    start = rc.index(f'<application name="{gimp.GIMP_WM_CLASS_MATCH}">')
    end = rc.index("</application>", start)
    block = rc[start:end]
    assert "<focus>no</focus>" in block
    assert "<skip_taskbar>yes</skip_taskbar>" in block
    assert "<skip_pager>yes</skip_pager>" in block
    assert "<iconic>yes</iconic>" not in block          # the removed transparent-middle cause
