"""packages.window_switcher -- OUR alt-tab window switcher, baked into the ISO.

OpenBox's built-in NextWindow switcher is a vertical, icon-only list; this package
replaces it with a horizontal, Windows-like overlay of LIVE window thumbnails, ordered
librewolf / kitty / hypervisor / thunar / alphabetical. Like the application menu it is a
COMPILED C / GTK3 resident daemon (built once, kept hidden) driven by a thin Python
launcher that signals it (--next -> SIGUSR1, --prev -> SIGUSR2).

These pin the packaging contract (pure, no X/GTK): the install paths, that emit_plan()
ships the launcher executable, that the launcher text carries the direction flags + the
signal mapping, and that the build-dep list names the XComposite stack the live
thumbnails require. The C-level ordering + resolver behaviour is covered by the headless
C tests (tests/test_ordering.c, tests/test_win_resolve.c).
"""

from packages.window_switcher import window_switcher as ws


def test_install_paths_are_under_usr_local():
    assert ws.SWITCHER_DAEMON_BIN_SYSTEM_PATH == (
        "/usr/local/lib/azarch-window-switcher/azarch-window-switcher-daemon"
    )
    assert ws.SWITCHER_LAUNCHER_SYSTEM_PATH == "/usr/local/bin/azarch-window-switcher"


def test_emit_plan_ships_launcher_executable():
    plan = ws.emit_plan()
    dests = {e["dest"]: e for e in plan}
    assert ws.SWITCHER_LAUNCHER_SYSTEM_PATH in dests
    assert dests[ws.SWITCHER_LAUNCHER_SYSTEM_PATH]["mode"] == 0o755


def test_emit_plan_does_not_ship_the_daemon_binary():
    # The binary is produced by build_daemon() (make), not a content builder in the plan.
    dests = [e["dest"] for e in ws.emit_plan()]
    assert ws.SWITCHER_DAEMON_BIN_SYSTEM_PATH not in dests


def test_launcher_text_parses_next_and_prev():
    txt = ws.launcher_py()
    assert "--next" in txt and "--prev" in txt
    assert "SIGUSR1" in txt and "SIGUSR2" in txt


def test_launcher_text_is_executable_shebang():
    txt = ws.launcher_py()
    assert txt.startswith("#!/usr/bin/env python3")


def test_build_deps_include_xcomposite_stack():
    for dep in ("gtk3", "pkgconf", "gcc", "libxcomposite", "libxrender", "libxdamage"):
        assert dep in ws.SWITCHER_BUILD_DEPS


def test_runtime_deps_require_picom():
    assert "picom" in ws.SWITCHER_RUNTIME_DEPS
