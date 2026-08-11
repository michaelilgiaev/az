"""packages.application_menu -- OUR application menu, baked into the ISO.

KDE Plasma was removed; the desktop is OpenBox with no panel, so this menu is the
WHOLE shell -- a borderless launcher CENTERED on the screen, opened by the Super key
(via xcape + the OpenBox rc.xml keybind).

These pin the contract that (a) the runtime files are emitted to the fixed system
paths the launcher/session expect, (b) the constants shared with
patches/openbox.py agree, and (c) the emitted content is the real Tkinter menu
wired to the launcher.

They also pin the menu's look/behaviour: the window is borderless (overrideredirect,
no titlebar buttons) and CENTERED, and the launcher is a single-instance TOGGLE (a
second Super press closes it via a PID file / signalled daemon) rather than a
spawn-every-click opener.

The menu dismisses like Plasma's Kickoff did -- a global pointer grab (grab_set_global)
plus an outside-click hit-test, with <FocusOut> and Escape backing it up, and the grab
always released on close. There is NO pin and NO panel-icon highlight bar anymore (both
were removed with the panel), so nothing here asserts them.
"""

from __future__ import annotations

import configparser
import io
import json
import os

from packages.application_menu import application_menu as am
from patches import openbox as desktop


def test_emit_plan_targets_expected_system_paths():
    # The .desktop entry (MENU_DESKTOP_SYSTEM_PATH) and the Super-key binding both run
    # MENU_LAUNCHER_SYSTEM_PATH, which starts the daemon that builds MENU_PY_SYSTEM_PATH.
    # All three must be emitted, at these paths.
    dests = {e["dest"] for e in am.emit_plan()}
    assert am.MENU_PY_SYSTEM_PATH in dests
    assert am.MENU_LAUNCHER_SYSTEM_PATH in dests
    assert am.MENU_DESKTOP_SYSTEM_PATH in dests


def test_launcher_is_executable_others_are_conf():
    modes = {e["dest"]: e["mode"] for e in am.emit_plan()}
    assert modes[am.MENU_LAUNCHER_SYSTEM_PATH] == 0o755   # runnable by the icon
    assert modes[am.MENU_PY_SYSTEM_PATH] == 0o644
    assert modes[am.MENU_DESKTOP_SYSTEM_PATH] == 0o644


def test_content_is_nonempty_and_is_the_tkinter_menu():
    for e in am.emit_plan():
        assert e["builder"]().strip(), f"empty content for {e['dest']}"
    # The menu program is our real Tkinter menu (the "Hello World" stub is long
    # gone -- menu.py is now the Kickoff-style launcher's orchestrator).
    assert "tkinter" in am.menu_py()
    assert "def main" in am.menu_py()


def test_desktop_entry_launches_the_installed_launcher():
    # The generated .desktop must Exec the installed launcher and carry a menu icon,
    # so launching it by name (or the Super key) runs our menu.
    cp = configparser.ConfigParser(interpolation=None)
    cp.read_file(io.StringIO(am.menu_desktop()))
    entry = cp["Desktop Entry"]
    assert entry["Exec"] == am.MENU_LAUNCHER_SYSTEM_PATH
    assert entry["Type"] == "Application"


def test_constants_match_desktop_module():
    # openbox.py binds the Super key to the menu LAUNCHER and starts the DAEMON from the
    # OpenBox autostart; a drift in these paths would wire the session to a path we never
    # installed.
    assert desktop.MENU_LAUNCHER == am.MENU_LAUNCHER_SYSTEM_PATH
    assert desktop.MENU_DAEMON_PY == am.MENU_DAEMON_PY_SYSTEM_PATH
    # The launcher rc.xml keybind and the autostart daemon line reference exactly these.
    assert am.MENU_LAUNCHER_SYSTEM_PATH in desktop.openbox_rc_xml()
    assert am.MENU_DAEMON_PY_SYSTEM_PATH in desktop.openbox_autostart()


def test_launcher_runs_the_daemon_which_runs_the_menu_module():
    # The menu now runs as a resident DAEMON (built once, kept hidden) so the icon
    # opens it INSTANTLY. The launcher therefore starts daemon.py -- NOT menu.py
    # directly. This SUPERSEDES the earlier "launcher runs menu.py" contract, which
    # must not be re-asserted. The icon still opens our menu, just indirectly:
    #   launcher (launcher.py, pure Python) -> daemon.py -> imports menu.py
    src = am.launcher_py()
    # The launcher builds the daemon path as ${MENU_DIR}/daemon.py where MENU_DIR
    # defaults to MENU_LIB_DIR -- i.e. it resolves to MENU_DAEMON_PY_SYSTEM_PATH.
    # Assert both halves (the path is composed from a var, so it is not one literal).
    assert src.startswith("#!/usr/bin/env python3")            # it is Python, not shell
    assert am.MENU_LIB_DIR in src                              # default install dir
    assert "daemon.py" in src                                  # ...runs daemon.py under it
    assert am.MENU_DAEMON_PY_SYSTEM_PATH == f"{am.MENU_LIB_DIR}/daemon.py"
    assert "import menu" in am.daemon_py()                     # daemon builds our menu


def test_emit_ships_editing_and_daemon_modules():
    # menu.py imports `editing`, and the launcher execs daemon.py -- so BOTH must be
    # emitted into MENU_LIB_DIR, else the built ISO ships a menu.py that ImportErrors
    # (editing) or a launcher that can't find its daemon. Regression guard for the
    # daemon refactor drifting away from the build wiring.
    dests = {e["dest"] for e in am.emit_plan()}
    assert f"{am.MENU_LIB_DIR}/editing.py" in dests
    assert am.MENU_DAEMON_PY_SYSTEM_PATH in dests
    # menu.py really does depend on editing (so shipping it is not optional).
    assert "import editing" in am.menu_py()


def test_emit_ships_winwatch_module():
    # The menu is ordered most-USED first, and an open is counted however the app
    # was launched -- that counting lives in winwatch.py, which daemon.py imports
    # (`from winwatch import ...`). So winwatch.py MUST be emitted into MENU_LIB_DIR
    # too, else the built ISO ships a daemon that dies at launch with
    # `ImportError: No module named 'winwatch'`. This guards MENU_MODULES staying
    # complete: the repo tests would otherwise stay GREEN while the image shipped a
    # broken daemon.
    dests = {os.path.basename(e["dest"]) for e in am.emit_plan()}
    assert "winwatch.py" in dests
    assert f"{am.MENU_LIB_DIR}/winwatch.py" in {e["dest"] for e in am.emit_plan()}
    # daemon.py really does depend on winwatch (so shipping it is not optional).
    assert "from winwatch import" in am.daemon_py()


def test_emit_ships_xfocus_module():
    # The pinned menu hands the keyboard back to the newly-active app via xfocus.py
    # (ctypes/libX11 XSetInputFocus), which menu.py imports (`import xfocus`). It MUST
    # be emitted into MENU_LIB_DIR or the built ISO ships a menu.py that dies at launch
    # with `ImportError: No module named 'xfocus'`. Same manifest-drift guard as
    # winwatch: keep MENU_MODULES complete.
    dests = {e["dest"] for e in am.emit_plan()}
    assert f"{am.MENU_LIB_DIR}/xfocus.py" in dests
    # menu.py really does depend on xfocus (so shipping it is not optional).
    assert "import xfocus" in am.menu_py()


def test_menu_is_borderless_and_centered():
    # The menu must be chromeless (no titlebar/min/max/close) and CENTERED on the
    # screen (there is no panel to anchor to anymore). The old bottom-corner /
    # Kickoff-popup-size machinery is gone.
    src = am.menu_py()
    assert "overrideredirect(True)" in src          # no window chrome
    assert "menu_size" in src                        # fixed theme size (no appletsrc read)
    # Centered placement: (screen - size) / 2 on both axes.
    assert "screen_w - win_w" in src
    assert "screen_h - win_h" in src
    # The old Plasma/Kickoff popup-size read is gone (no appletsrc / popupWidth).
    assert "kickoff_popup_size" not in src
    assert "popupWidth" not in src


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


def test_menu_has_no_pin_or_settings_or_highlight_bar():
    # The pin button, the (greyed-out) Settings button, and the panel-icon highlight
    # bar were all REMOVED (the panel is gone and the menu is a plain transient
    # launcher). Guard against any of them being reintroduced. Check the RUNTIME
    # modules (menu.py + widgets.py + theme.py), not the whole package -- the menu's own
    # test suite (test_menu.py) legitimately mentions these names in its guards.
    runtime = am.menu_py() + am._module_src("widgets.py") + am._module_src("theme.py")
    assert "pin_button" not in runtime               # no pin control
    assert "settings_button" not in runtime          # no settings control
    assert "class HighlightBar" not in runtime       # no panel-icon highlight bar
    assert "az_highlight" not in runtime             # nor its root stash
    assert "class IconButton" not in runtime         # the pin/settings widget is gone
    # The full-width search box: the search entry still expands to fill the row.
    assert 'side="left", fill="x", expand=True' in am.menu_py()


def test_menu_has_tab_focus_toggle_between_search_and_power():
    # TWO keyboard focus zones toggled with TAB: the default is the search box + app
    # list (arrows navigate apps), and TAB moves focus to the power row (arrows move
    # between the power buttons); TAB again returns to the default. Pin the wiring.
    src = am.menu_py()
    assert "FOCUS_APPS" in src and "FOCUS_POWER" in src   # the two zones
    assert "def toggle_focus" in src                       # TAB flips zones
    assert "def set_focus_zone" in src                     # moves + repaints focus
    assert '"<Tab>"' in src                                # TAB is bound
    assert "set_selection_enabled" in src                  # app-list dims when TAB'd away
    # A power button can render a keyboard-focus outline (driven by the toggle).
    assert "set_focused" in am.menu_package_source()


def test_usage_seed_orders_the_default_top_three():
    # A fresh profile has no launch history, so the menu would sort alphabetically.
    # The seed store fixes the STARTING top THREE to LibreWolf, kitty, Dolphin
    # (descending), keyed by .desktop id -- EXACTLY three per the user's request, so the
    # freshly-installed menu leads with those and nothing else. Parse it and assert the
    # order the menu's sort (-count, name) would produce is exactly that.
    seed = json.loads(am.usage_seed_json())
    ranked = sorted(seed.items(), key=lambda kv: -kv[1])
    assert [k for k, _ in ranked] == [
        "librewolf.desktop",
        "kitty.desktop",
        "org.kde.dolphin.desktop",
    ], ranked
    # Exactly three are seeded: no fourth app (GIMP used to be seeded; it now starts in
    # the count-0 alphabetical tail), and KDE's "System Settings" is gone with Plasma.
    assert len(seed) == 3, seed
    assert "gimp.desktop" not in seed
    assert "systemsettings.desktop" not in seed


def test_usage_seed_matches_usagestore_format_and_is_home_owned():
    # The seed must be byte-for-byte what usage.py's UsageStore writes (compact
    # json.dumps with separators (",", ":")), so the store reads it straight back.
    seed_txt = am.usage_seed_json()
    assert seed_txt == json.dumps(am.MENU_USAGE_SEED, separators=(",", ":"))
    assert " " not in seed_txt  # compact form -> no spaces after ',' or ':'

    # It is emitted as a per-user (home-owned) data file so a fresh profile inherits
    # it (and compiler.py mirrors it into /etc/skel for Calamares-installed users).
    plan = {e["dest"]: e for e in desktop.emit_plan()}
    assert am.MENU_USAGE_SEED_SYSTEM_PATH in plan, am.MENU_USAGE_SEED_SYSTEM_PATH
    entry = plan[am.MENU_USAGE_SEED_SYSTEM_PATH]
    assert entry["owner"] == "home"          # chowned 1000:998 + mirrored to skel
    assert entry["mode"] == 0o644
    assert entry["dest"].startswith(desktop.HOME + "/")  # under /home/main
    assert entry["builder"]() == seed_txt


def test_menu_open_is_instant_no_rebuild_when_order_unchanged():
    # Opening the menu must be INSTANT. The daemon re-sorts the list on every show
    # (resort -> set_entries), and set_entries used to unconditionally rebuild every
    # canvas row AND reload a PhotoImage per app -- the dominant open cost -- so every
    # open paid a full rebuild even when nothing changed. Now set_entries fingerprints
    # the entry list (_signature) and SKIPS the rebuild when the drawn list is
    # unchanged, and resort skips the re-filter when set_entries reports no rebuild.
    applist = am._module_src("applist.py")
    assert "_signature" in applist                       # cheap entry fingerprint
    assert "_rows_signature" in applist                  # remembered across shows
    # set_entries returns whether it rebuilt (so resort can skip re-laying-out).
    assert "def set_entries(self, entries)" in applist
    menu_src = am.menu_py()
    assert "rebuilt = self.applist.set_entries" in menu_src
    assert "if rebuilt:" in menu_src                     # only re-filter on a real change


def test_menu_open_is_instant_window_stays_mapped_moved_not_remapped():
    # Opening the menu must be INSTANT even on the FIRST Super press. Under X the
    # expensive part of showing the window is the MAP itself: withdraw()/deiconify()
    # unmaps and re-maps the whole widget tree, and re-mapping re-exposes every child X
    # window (~120-600ms here, worst on the very first map) -- the "renders slowly the
    # first time / not snappy" bug. The fix: the daemon maps the window ONCE, OFF-screen,
    # at login (paying that first-map cost invisibly), and thereafter HIDES by moving it
    # off-screen and SHOWS by moving it back on-screen -- never re-mapping.
    menu_src = am.menu_py()
    # An off-screen park distance + a warm-up that maps once and a hide that MOVES.
    assert "OFFSCREEN_MARGIN" in menu_src                 # park distance beyond all screens
    assert "def warmup_menu(" in menu_src                 # one-time off-screen map at login
    assert "root.az_warmup = warmup_menu" in menu_src     # exposed for the daemon
    # hide_menu must NOT withdraw (that would force a re-map on the next show); it moves
    # the still-mapped window off-screen instead.
    hide_body = menu_src.split("def hide_menu(", 1)[1].split("def show_menu(", 1)[0]
    assert "root.withdraw(" not in hide_body, (
        "hide_menu must NOT call root.withdraw() (a re-map on next show is the slow path); "
        "it must MOVE the still-mapped window off-screen"
    )
    assert "OFFSCREEN_MARGIN" in hide_body                # parks off-screen
    assert "root.az_shown = False" in hide_body           # tracks shown/hidden explicitly
    # The daemon warms the window up at startup (maps off-screen once) and toggles on the
    # az_shown flag -- NOT winfo_viewable(), which is always True now the window stays
    # mapped while hidden.
    daemon_src = am.daemon_py()
    assert "az_warmup()" in daemon_src                    # prepay the first map at login
    assert "az_shown" in daemon_src                       # toggle reads the shown flag
    toggle_body = daemon_src.split("def toggle(", 1)[1].split("def quit(", 1)[0]
    assert "self.root.winfo_viewable" not in toggle_body, (
        "toggle() must decide shown/hidden by az_shown, not winfo_viewable() -- the hidden "
        "window stays mapped (moved off-screen), so winfo_viewable() is always True"
    )


def test_menu_repopulates_newly_installed_apps_on_open():
    # A long-lived daemon that scanned .desktop files only once at login would never
    # show a package installed later (e.g. `pacman -S firefox`). reset_view now
    # re-scans on every open (refresh_apps -> scan_applications) so new apps appear
    # without restarting the session; set_entries only rebuilds if the set changed, so
    # a rescan that finds nothing new stays instant.
    menu_src = am.menu_py()
    assert "def refresh_apps(self)" in menu_src
    assert "scan_applications()" in menu_src
    # reset_view (called by the daemon on each show) triggers the rescan.
    assert "self.refresh_apps()" in menu_src
    # The daemon also drops the WindowWatcher's cached desktop index on show, so a
    # newly-installed app's launches get COUNTED too (not just listed).
    daemon_src = am.daemon_py()
    assert "refresh_index" in daemon_src


def test_menu_pins_qalculate_first_for_calculator_query():
    # Typing "calculator" (or any prefix of it) must surface Qalculate! FIRST, even
    # though the app is named "Qalculate!". The alias table maps the target word to
    # the .desktop id, and apply_filter floats that app to the top of the matches
    # while the query is a prefix of the word -- and only when it is actually a match.
    applist = am._module_src("applist.py")
    assert "SEARCH_PIN_ALIASES" in applist
    assert "qalculate-gtk.desktop" in applist            # the pinned app
    assert '"calculator"' in applist                     # the trigger word
    assert "_pinned_desktop_id_for_query" in applist     # prefix-of-word logic
    # apply_filter honours the pin by moving the matched row to the front.
    assert "pinned_id" in applist


def test_launcher_is_a_single_instance_toggle():
    # A second click must CLOSE the menu, not open another: the launcher (now pure
    # Python) tracks a PID file and SIGUSR1-toggles the live instance instead of
    # stacking a new window.
    src = am.launcher_py()
    assert "PID_FILE" in src                        # tracks the running instance
    assert "azarch-application-menu.pid" in src
    assert "XDG_RUNTIME_DIR" in src                 # PID file under the runtime dir
    assert "os.kill(pid, 0)" in src                 # is the recorded instance alive?
    assert "SIGUSR1" in src                         # toggle (show/hide) on second click
    assert "SIGUSR2" in src                         # force-show right after auto-start
