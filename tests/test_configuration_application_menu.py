"""azarch.configuration.application_menu -- OUR application menu, baked into the
ISO and shown right of Kickoff.

These pin the contract that (a) the three runtime files are emitted to the fixed
system paths the panel icon expects, (b) the constants shared with
configuration/desktop.py agree (a drift there = an icon that launches nothing),
and (c) the emitted content is the real menu (Hello World) wired to the launcher.

They also pin the menu's look/behaviour matching the live hypervisor: the window
is borderless (overrideredirect, no titlebar buttons) and sized to Kickoff's
popup, and the launcher is a single-instance TOGGLE (a second click closes it via
a PID file) rather than a spawn-every-click opener.

Two behaviours were ported from the live hypervisor and are pinned here (see
test_menu_closes_on_outside_click and test_menu_highlights_panel_icon):
  * The menu now dismisses like Plasma's Kickoff -- a global pointer grab
    (grab_set_global) plus an outside-click hit-test, with <FocusOut> and Escape
    backing it up, and the grab always released on close. This SUPERSEDES the
    earlier "deliberately does NOT grab focus, closes only via the launcher
    toggle" contract, which must not be re-asserted anywhere.
  * A borderless Breeze-blue (#3daee9) HighlightBar pops in over the panel icon
    while the menu is open and vanishes on close. It appears instantly, with NO
    animation -- a guard asserts no animation helper is reintroduced.
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


def test_menu_is_borderless_and_kickoff_sized():
    # The menu must be chromeless (no titlebar/min/max/close) and sized to match
    # Plasma's Kickoff popup, pinned bottom-right -- matching the live hypervisor.
    src = am.menu_py()
    assert "overrideredirect(True)" in src          # no window chrome
    assert "kickoff_popup_size" in src              # size tracks Kickoff's popup
    assert "popupWidth" in src and "popupHeight" in src
    # NOTE: the earlier version of this menu deliberately did NOT grab focus and
    # left dismissal to the launcher toggle. That contract was replaced by the
    # Kickoff-style outside-click close (see test_menu_closes_on_outside_click),
    # so this test no longer asserts the absence of a focus grab / -topmost.


def test_menu_closes_on_outside_click():
    # Ported behaviour #1: the menu dismisses like Plasma's Kickoff when anything
    # outside it is pressed. This is a GLOBAL pointer grab (grab_set_global) plus a
    # hit-test against the window bounds, backed by <FocusOut> and Escape.
    src = am.menu_py()
    assert "grab_set_global" in src                 # global pointer grab is taken
    assert "on_button" in src                       # outside-click hit-test handler
    assert 'bind_all("<Button>"' in src             # every press is fed to the test
    assert '"<FocusOut>"' in src                    # focus-loss also closes it
    assert '"<Escape>"' in src                      # Escape still dismisses
    # The grab must ALWAYS be released on close, so it can never wedge the session.
    assert "grab_release" in src


def test_menu_highlights_panel_icon():
    # Ported behaviour #2: a Breeze-blue highlight bar appears over the panel icon
    # while the menu is open, matching Plasma's "active applet" indicator.
    src = am.menu_py()
    assert "#3daee9" in src                          # Breeze Dark selection color
    assert "HIGHLIGHT_COLOR" in src                  # named accent color
    assert "class HighlightBar" in src               # the bar is its own Toplevel
    assert "az_highlight" in src                     # stashed on root, torn down on close
    assert "HighlightBar(root" in src                # actually instantiated
    assert ".show()" in src                          # the bar is shown while open


def test_highlight_bar_is_not_animated():
    # The bar was explicitly required to POP IN at full size -- no fade/grow. Guard
    # against a future edit silently reintroducing an animation. show() must just
    # place + deiconify the bar, never step a geometry over time.
    src = am.menu_py()
    assert "animate_in" not in src                   # the old fade helper is gone
    assert "def _animate" not in src                 # no animation stepper method
    assert "def _grow" not in src                    # nor a grow-over-time helper
    # show() reveals the bar at full size in one shot.
    assert "deiconify" in src


def test_launcher_is_a_single_instance_toggle():
    # A second click must CLOSE the menu, not open another: the launcher tracks a
    # PID file and kills the live instance instead of stacking a new window.
    src = am.launcher_sh()
    assert "PID_FILE" in src                        # tracks the running instance
    assert "azarch-application-menu.pid" in src
    assert "XDG_RUNTIME_DIR" in src                 # PID file under the runtime dir
    assert "kill -0" in src                         # is the recorded instance alive?
    assert "kill " in src                           # close-on-second-click path
