"""packages.application_menu -- OUR application menu, baked into the ISO.

KDE Plasma was removed; the desktop is OpenBox with no panel, so this menu is the
WHOLE shell -- a borderless launcher CENTERED on the screen, opened by the Super key
(via xcape + the OpenBox rc.xml keybind).

The menu is a COMPILED C / GTK3 program now (the earlier Tkinter/Python port was
replaced). The C sources live directly in the package dir with a Makefile; the build
wiring here COMPILES them into a single resident daemon binary
(azarch-application-menu-daemon) and installs it under MENU_LIB_DIR. A thin Python
launcher (installed as the bin entry point) signals that daemon.

These pin the contract that (a) the build compiles + installs the daemon binary and
emits the launcher + .desktop to the fixed system paths the launcher/session expect,
(b) the constants shared with patches/openbox.py agree, (c) the launcher execs the
BINARY (not a python module), and (d) the C menu keeps its pinned behaviour -- most
importantly, TAB lands on "Shut Down".

The menu dismisses like Plasma's Kickoff did -- a global pointer/keyboard grab plus an
outside-click hit-test, with focus-loss and Escape backing it up. There is NO pin and NO
panel-icon highlight bar anymore (both were removed with the panel).
"""

from __future__ import annotations

import configparser
import io
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from packages.application_menu import application_menu as am
from patches import openbox as desktop

CSRC_DIR = Path(am.paths.APPLICATION_MENU_DIR)


# --- Structure: the Python menu is gone, the C sources are flattened up ------

def test_python_menu_modules_are_deleted():
    # The whole Tkinter menu (menu.py + siblings + daemon.py + its tests) was removed
    # when the C port landed. Only the pure-Python LAUNCHER and this build-wiring module
    # remain as Python in the package. Guard against any of them creeping back.
    gone = [
        "menu.py", "applist.py", "widgets.py", "theme.py", "applications.py", "winwatch.py",
        "icons.py", "usage.py", "actions.py", "editing.py", "xfocus.py", "daemon.py",
        "test_menu.py", "conftest.py",
    ]
    for name in gone:
        assert not (CSRC_DIR / name).exists(), f"{name} should have been deleted"
    # The only Python left is the launcher + the build wiring.
    pyfiles = sorted(p.name for p in CSRC_DIR.glob("*.py"))
    assert pyfiles == ["application_menu.py", "launcher.py"], pyfiles


def test_csrc_dir_is_flattened_up():
    # The C sources were moved OUT of a nested csrc/ up into the package dir, and csrc/
    # was deleted. menu.c + the Makefile now sit directly beside application_menu.py.
    assert not (CSRC_DIR / "csrc").exists(), "csrc/ should have been removed"
    assert (CSRC_DIR / "menu.c").is_file()
    assert (CSRC_DIR / "Makefile").is_file()
    assert (CSRC_DIR / "theme.h").is_file()
    # A representative spread of the sibling translation units is present at top level.
    for name in ("applist.c", "applications.c", "usage.c", "icons.c", "actions.c",
                 "winwatch.c", "kscroll.c", "power.c"):
        assert (CSRC_DIR / name).is_file(), name


# --- Emit plan: the launcher + .desktop (the daemon binary is compiled) ------

def test_emit_plan_targets_expected_system_paths():
    # emit_plan() covers the two generated TEXT artifacts: the launcher (run by the
    # Super key / .desktop) and the app-launcher .desktop. The daemon BINARY is NOT in
    # the plan -- it is compiled + installed by build_daemon() -- so it must NOT appear
    # here, but its install path is still a defined constant under MENU_LIB_DIR.
    dests = {e["dest"] for e in am.emit_plan()}
    assert am.MENU_LAUNCHER_SYSTEM_PATH in dests
    assert am.MENU_DESKTOP_SYSTEM_PATH in dests
    assert am.MENU_DAEMON_BIN_SYSTEM_PATH not in dests   # compiled, not text-emitted
    assert am.MENU_DAEMON_BIN_SYSTEM_PATH == f"{am.MENU_LIB_DIR}/azarch-application-menu-daemon"


def test_launcher_is_executable_desktop_is_conf():
    modes = {e["dest"]: e["mode"] for e in am.emit_plan()}
    assert modes[am.MENU_LAUNCHER_SYSTEM_PATH] == 0o755   # runnable by the icon
    assert modes[am.MENU_DESKTOP_SYSTEM_PATH] == 0o644


def test_emitted_content_is_nonempty():
    for e in am.emit_plan():
        assert e["builder"]().strip(), f"empty content for {e['dest']}"


def test_desktop_entry_launches_the_installed_launcher():
    # The generated .desktop must Exec the installed launcher and carry a menu icon,
    # so launching it by name (or the Super key) runs our menu.
    cp = configparser.ConfigParser(interpolation=None)
    cp.read_file(io.StringIO(am.menu_desktop()))
    entry = cp["Desktop Entry"]
    assert entry["Exec"] == am.MENU_LAUNCHER_SYSTEM_PATH
    assert entry["Type"] == "Application"


def test_constants_match_desktop_module():
    # openbox.py binds the Super key to the menu LAUNCHER and starts the DAEMON BINARY
    # from the OpenBox autostart; a drift in these paths would wire the session to a path
    # we never installed.
    assert desktop.MENU_LAUNCHER == am.MENU_LAUNCHER_SYSTEM_PATH
    assert desktop.MENU_DAEMON_BIN == am.MENU_DAEMON_BIN_SYSTEM_PATH
    # The launcher rc.xml keybind and the autostart daemon line reference exactly these.
    assert am.MENU_LAUNCHER_SYSTEM_PATH in desktop.openbox_rc_xml()
    assert am.MENU_DAEMON_BIN_SYSTEM_PATH in desktop.openbox_autostart()


# --- The launcher drives the compiled daemon, not a python module -----------

def test_launcher_runs_the_daemon_binary_not_python():
    # The menu now runs as a resident C DAEMON (built once, kept hidden) so the icon
    # opens it INSTANTLY. The launcher (pure Python bin entry point) starts the compiled
    # BINARY directly and signals it -- it does NOT exec a python module or interpreter.
    src = am.launcher_py()
    assert src.startswith("#!/usr/bin/env python3")            # the launcher is Python
    assert am.MENU_LIB_DIR in src                              # default install dir
    assert "azarch-application-menu-daemon" in src             # ...runs the binary under it
    # It starts the binary as its own argv[0] (no `sys.executable` / `python3` prefix).
    assert "[DAEMON_BIN]" in src
    assert "sys.executable" not in src
    # The daemon-signalling contract is unchanged (PID file + SIGUSR1/SIGUSR2).
    assert "SIGUSR1" in src and "SIGUSR2" in src


def test_launcher_is_a_single_instance_toggle():
    # A second click must CLOSE the menu, not open another: the launcher tracks a PID
    # file and SIGUSR1-toggles the live instance instead of stacking a new window.
    src = am.launcher_py()
    assert "PID_FILE" in src                        # tracks the running instance
    assert "azarch-application-menu.pid" in src
    assert "XDG_RUNTIME_DIR" in src                 # PID file under the runtime dir
    assert "os.kill(pid, 0)" in src                 # is the recorded instance alive?
    assert "SIGUSR1" in src                         # toggle (show/hide) on second click
    assert "SIGUSR2" in src                         # force-show right after auto-start


# --- The C menu keeps its pinned behaviour ----------------------------------

def _menu_c() -> str:
    return (CSRC_DIR / "menu.c").read_text(encoding="utf-8")


def test_menu_tab_lands_on_shut_down():
    # THE headline behaviour: pressing TAB moves focus into the power row and lands on
    # "Shut Down" (the rightmost of {Sleep, Lock, Restart, Shut Down}, index 3), so the
    # commonest session action is one TAB + Enter away. Pin both the button ORDER (so
    # index 3 really is Shut Down) and the TAB handler forcing that index on entry.
    src = _menu_c()
    # The power row order: Shut Down is the 4th (index 3) button. Pin it from the actual
    # PowerItem initializer table (not free-floating strings in comments): grab the
    # `PowerItem items[4] = { ... };` block and read its labels in order.
    table = re.search(r"PowerItem\s+items\[4\]\s*=\s*\{(.*?)\};", src, re.S)
    assert table, "could not find the PowerItem items[4] table in menu.c"
    order = re.findall(r'"([^"]+)"\s*,\s*az_\w+\s*\}', table.group(1))
    assert order == ["Sleep", "Lock", "Restart", "Shut Down"], order
    # A named constant pins the Shut Down index to 3.
    assert "AZ_POWER_SHUTDOWN_INDEX 3" in src
    # The TAB handler, when entering the power zone, forces the index to Shut Down.
    tab_block = src.split("GDK_KEY_Tab", 1)[1].split("return TRUE;", 1)[0]
    assert "power_index = AZ_POWER_SHUTDOWN_INDEX" in tab_block
    assert "set_focus_zone(m, FOCUS_POWER)" in tab_block


def test_menu_has_tab_focus_toggle_between_search_and_power():
    # TWO keyboard focus zones toggled with TAB: the default is the search box + app
    # list (arrows navigate apps), and TAB moves focus to the power row (arrows move
    # between the power buttons); TAB again returns to the default. Pin the wiring.
    src = _menu_c()
    assert "FOCUS_APPS" in src and "FOCUS_POWER" in src   # the two zones
    assert "set_focus_zone" in src                         # moves + repaints focus
    assert "GDK_KEY_Tab" in src                            # TAB is bound
    assert "az_applist_set_selection_enabled" in src       # app-list dims when TAB'd away


def test_menu_is_borderless_and_centered():
    # The menu must be chromeless (override-redirect, no titlebar) and CENTERED on the
    # screen (there is no panel to anchor to anymore).
    src = _menu_c()
    assert "gdk_window_set_override_redirect" in src        # no window chrome
    # Centered placement: (screen - size) / 2 on both axes.
    assert "win_x" in src and "win_y" in src


def test_menu_closes_on_outside_click_and_escape():
    # Ported behaviour: the menu dismisses like Plasma's Kickoff when anything outside it
    # is pressed (a global grab + a hit-test), and Escape / a physical Super press also
    # close it.
    src = _menu_c()
    assert "gdk_seat_grab" in src                           # global pointer/keyboard grab
    assert "on_button_press" in src                         # outside-click hit-test handler
    assert "GDK_KEY_Escape" in src                          # Escape dismisses


def test_menu_open_is_instant_warmup_maps_once_offscreen():
    # Opening the menu must be INSTANT even on the FIRST Super press: the expensive part
    # under X is the MAP itself. The daemon maps the window ONCE, OFF-screen, at login
    # (warmup), then HIDES by moving it off-screen and SHOWS by moving it back -- never
    # re-mapping.
    src = _menu_c()
    assert "warmup" in src                                  # one-time off-screen map at login
    assert "shown" in src                                   # tracks shown/hidden explicitly


def test_menu_is_a_single_instance_daemon():
    # The daemon is single-instance (PID file) and speaks the launcher's protocol:
    # SIGUSR1 = toggle, SIGUSR2 = show. Same contract the launcher relies on.
    src = _menu_c()
    assert "azarch-application-menu.pid" in src             # same PID file the launcher reads
    assert "SIGUSR1" in src and "SIGUSR2" in src            # toggle / show
    assert "claim_pidfile" in src                           # single-instance guard


# --- build_daemon(): compiles the C sources into the installed binary --------

def _have_toolchain() -> bool:
    if shutil.which("gcc") is None and shutil.which("cc") is None:
        return False
    if shutil.which("make") is None or shutil.which("pkg-config") is None:
        return False
    return subprocess.run(
        ["pkg-config", "--exists", "gtk+-3.0"],
    ).returncode == 0


def test_build_daemon_inputs_are_the_c_sources():
    # The build copies exactly the C sources/headers + the Makefile into its scratch dir
    # (so the repo tree is never dirtied). No Python is compiled; the Makefile drives it.
    names = {p.name for p in am._csrc_files()}
    assert "menu.c" in names
    assert "Makefile" in names
    assert "theme.h" in names
    assert not any(n.endswith(".py") for n in names)        # only C inputs
    # The binary name the build produces matches the installed daemon path's basename.
    assert am.MENU_DAEMON_BIN_NAME == os.path.basename(am.MENU_DAEMON_BIN_SYSTEM_PATH)


def test_build_daemon_does_not_pollute_the_repo_tree():
    # build_daemon() must build in a TEMP dir, not in the source tree -- no object files
    # or binary may be left behind next to the sources (they would otherwise get tracked
    # / shipped). Assert the tree is clean of build artifacts before AND after a build.
    def _artifacts():
        return sorted(
            p.name for p in CSRC_DIR.iterdir()
            if p.suffix == ".o" or p.name == am.MENU_DAEMON_BIN_NAME
        )

    assert _artifacts() == [], f"stale build artifacts in the source tree: {_artifacts()}"
    if not _have_toolchain():
        pytest.skip("no gcc/GTK3 toolchain on this host")
    out = CSRC_DIR / "_test_build_out" / am.MENU_DAEMON_BIN_NAME
    try:
        am.build_daemon(out)
        assert out.is_file() and os.access(out, os.X_OK)    # produced an executable
        assert _artifacts() == [], f"build polluted the source tree: {_artifacts()}"
    finally:
        shutil.rmtree(CSRC_DIR / "_test_build_out", ignore_errors=True)


def test_gtk3_build_deps_are_provisioned_on_the_build_host():
    # REGRESSION GUARD: the menu is compiled DURING the ISO build (build_daemon -> make)
    # BEFORE the makepkg makedepends step, so its GTK3 dev deps must be provisioned by the
    # build-host toolchain, not deferred. This test would fail (not just skip on a bare
    # host) if the Dockerfile or the host-dep check ever dropped them again -- exactly the
    # gap that let a green dev-host suite hide a broken Docker build.
    #
    # 1. The single source of truth names the GTK3 dev stack.
    assert "gtk3" in am.MENU_BUILD_DEPS, am.MENU_BUILD_DEPS

    repo = Path(am.paths.APPLICATION_MENU_DIR).parents[2]   # .../libraries/packages/x -> repo root

    # 2. The Docker build image (where the real ISO is built) bakes them in -- the menu
    #    compile runs before makepkg._install_host_build_deps, so they can't be deferred.
    dockerfile = (repo / "Dockerfile").read_text(encoding="utf-8")
    for dep in am.MENU_BUILD_DEPS:
        if dep == "gcc":
            continue                                        # gcc rides in via base-devel
        assert re.search(rf"^\s*{re.escape(dep)}\s*\\?\s*$", dockerfile, re.M), (
            f"Dockerfile must install '{dep}' (needed to compile the menu daemon)"
        )

    # 3. compiler._check_host_deps installs the SAME set on a non-Docker Arch host (and so
    #    its 'already present' early-return can't skip a host missing only the GTK3 stack).
    compiler_src = (repo / "libraries" / "compiler.py").read_text(encoding="utf-8")
    assert "application_menu.MENU_BUILD_DEPS" in compiler_src, (
        "compiler._check_host_deps must fold in application_menu.MENU_BUILD_DEPS"
    )


# --- Usage seed (unchanged contract: LibreWolf, kitty, Dolphin) --------------

def test_usage_seed_orders_the_default_top_three():
    # A fresh profile has no launch history, so the menu would sort alphabetically. The
    # seed store fixes the STARTING top THREE to LibreWolf, kitty, Dolphin (descending),
    # keyed by .desktop id -- EXACTLY three per the user's request.
    seed = json.loads(am.usage_seed_json())
    ranked = sorted(seed.items(), key=lambda kv: -kv[1])
    assert [k for k, _ in ranked] == [
        "librewolf.desktop",
        "kitty.desktop",
        "org.kde.dolphin.desktop",
    ], ranked
    assert len(seed) == 3, seed
    assert "gimp.desktop" not in seed
    assert "systemsettings.desktop" not in seed


def test_usage_seed_matches_store_format_and_is_home_owned():
    # The seed must be byte-for-byte what the usage store writes (compact json with
    # separators (",", ":")), so the store reads it straight back.
    seed_txt = am.usage_seed_json()
    assert seed_txt == json.dumps(am.MENU_USAGE_SEED, separators=(",", ":"))
    assert " " not in seed_txt  # compact form -> no spaces after ',' or ':'

    # It is emitted as a per-user (home-owned) data file so a fresh profile inherits it
    # (and compiler.py mirrors it into /etc/skel for Calamares-installed users).
    plan = {e["dest"]: e for e in desktop.emit_plan()}
    assert am.MENU_USAGE_SEED_SYSTEM_PATH in plan, am.MENU_USAGE_SEED_SYSTEM_PATH
    entry = plan[am.MENU_USAGE_SEED_SYSTEM_PATH]
    assert entry["owner"] == "home"          # chowned 1000:998 + mirrored to skel
    assert entry["mode"] == 0o644
    assert entry["dest"].startswith(desktop.HOME + "/")  # under /home/main
    assert entry["builder"]() == seed_txt
