"""azarch.configuration.application_menu -- OUR application menu, baked into the
ISO and shown right of Kickoff.

These pin the contract that (a) the three runtime files are emitted to the fixed
system paths the panel icon expects, (b) the constants shared with
configuration/desktop.py agree (a drift there = an icon that launches nothing),
and (c) the emitted content is the real menu (Hello World) wired to the launcher.
"""

from __future__ import annotations

import configparser
import io

from azarch.configuration import application_menu as am
from azarch.configuration import desktop


def test_emit_plan_targets_expected_system_paths():
    # The panel icon (baked into desktop.plasma_appletsrc) points at
    # MENU_DESKTOP_SYSTEM_PATH, whose Exec runs MENU_LAUNCHER_SYSTEM_PATH, which
    # runs MENU_PY_SYSTEM_PATH. All three must be emitted, at these paths.
    dests = {e["dest"] for e in am.emit_plan()}
    assert am.MENU_PY_SYSTEM_PATH in dests
    assert am.MENU_LAUNCHER_SYSTEM_PATH in dests
    assert am.MENU_DESKTOP_SYSTEM_PATH in dests


def test_launcher_is_executable_others_are_conf():
    modes = {e["dest"]: e["mode"] for e in am.emit_plan()}
    assert modes[am.MENU_LAUNCHER_SYSTEM_PATH] == 0o755   # runnable by the icon
    assert modes[am.MENU_PY_SYSTEM_PATH] == 0o644
    assert modes[am.MENU_DESKTOP_SYSTEM_PATH] == 0o644


def test_content_is_nonempty_and_is_the_hello_world_menu():
    for e in am.emit_plan():
        assert e["builder"]().strip(), f"empty content for {e['dest']}"
    # The menu program is our Tkinter "Hello World" window.
    assert "Hello World" in am.menu_py()
    assert "tkinter" in am.menu_py()


def test_desktop_entry_launches_the_installed_launcher():
    # The .desktop the icon points at must Exec the installed launcher and carry a
    # menu icon, so clicking the panel icon runs our menu.
    cp = configparser.ConfigParser(interpolation=None)
    cp.read_file(io.StringIO(am.menu_desktop()))
    entry = cp["Desktop Entry"]
    assert entry["Exec"] == am.MENU_LAUNCHER_SYSTEM_PATH
    assert entry["Type"] == "Application"


def test_constants_match_desktop_module():
    # desktop.plasma_appletsrc bakes the panel icon using these; a mismatch means
    # the icon would launch a path we never installed.
    assert desktop._AZ_MENU_DESKTOP_PATH == am.MENU_DESKTOP_SYSTEM_PATH
    assert desktop._AZ_MENU_ICON_NAME == am.MENU_ICON_NAME


def test_launcher_runs_the_menu_module():
    # The launcher must invoke the installed menu.py (so the icon opens our menu).
    assert am.MENU_PY_SYSTEM_PATH in am.launcher_sh()
