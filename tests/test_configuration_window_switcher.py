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
C tests (tests/test_ordering.c, tests/test_window_resolve.c).
"""

import paths

from packages.window_switcher import window_switcher as ws


def _layout_c() -> str:
    """The switcher tile-strip C source (layout.c) as text."""
    return (paths.WINDOW_SWITCHER_DIR / "layout.c").read_text(encoding="utf-8")


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


# --- Live-render flush contract (layout.c) ----------------------------------
# The overlay is an override-redirect window shown by MOVING it on-screen (never re-mapped),
# so a gtk_widget_queue_draw is only QUEUED -- nothing pumps the frame -- and the change does
# not reach the screen until some unrelated event forces one. That is why moving the SELECTION
# updated the widget state correctly yet the highlighted-tile border did not visibly move (the
# reported "pressing Tab again doesn't move to the window on the right" bug), and why the live
# thumbnails streamed only sparsely. The fix pushes the toplevel's pending updates to the X
# server after a selection change AND after a thumbnail refresh. These pin that the flush stays
# wired on both paths so a refactor cannot silently reintroduce the frozen-overlay bug (this
# behaviour is GTK/X-level and cannot be exercised by these headless unit tests, so we pin it at
# the source, the same way the C ordering/resolver behaviour is covered by the headless C tests).
def test_selection_change_flushes_to_screen():
    src = _layout_c()
    sel = src[src.index("void az_strip_select("):]
    sel = sel[: sel.index("\n}") + 2]
    assert "az_strip_flush(s)" in sel, (
        "az_strip_select must flush the border change to the screen, or the selected-tile "
        "highlight will not visibly move on the override-redirect overlay"
    )


def test_thumbnail_refresh_flushes_to_screen():
    src = _layout_c()
    ref = src[src.index("void az_strip_refresh_thumbnails("):]
    ref = ref[: ref.index("\n}") + 2]
    assert "az_strip_flush(s)" in ref, (
        "az_strip_refresh_thumbnails must flush so the live tiles actually stream on the "
        "override-redirect overlay instead of updating only when another event forces a frame"
    )


def test_flush_helper_forces_pending_updates_out():
    # The helper must both process the toplevel's queued updates and flush the display -- a bare
    # gtk_widget_queue_draw does NOT repaint this override-redirect window on its own.
    src = _layout_c()
    assert "static void az_strip_flush(AzStrip *s)" in src
    helper = src[src.index("static void az_strip_flush(AzStrip *s)"):]
    helper = helper[: helper.index("\n}") + 2]
    assert "gdk_window_process_updates" in helper
    assert "gdk_display_flush" in helper
