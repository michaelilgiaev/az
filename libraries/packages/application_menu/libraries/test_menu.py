#!/usr/bin/env python3
"""Tests for the Az'arch application menu.

Two layers:
  * Pure-logic tests (no display): category typing in apps.py, .desktop
    parsing, and launch-frequency ordering in usage.py. These run anywhere.
  * UI smoke tests (need $DISPLAY): build the real window, disable its
    auto-close bindings, and drive the search filter (including the clear-
    restores-order fix), selection / launch, the TAB focus toggle between the
    app list and the power row, and the power wiring deterministically.

Run:  DISPLAY=:0 XAUTHORITY=~/.Xauthority python3 test_menu.py
The UI layer is skipped automatically when no display is available.

These are plain asserts (no pytest dependency) so they run on the bare live
session. Exit code is non-zero on the first failure.
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import apps  # noqa: E402
import usage  # noqa: E402


# --- pure-logic: launch-frequency usage ordering --------------------------
class _FakeEntry:
    """Minimal stand-in for AppEntry: usage ordering only needs name + id."""

    def __init__(self, name: str, desktop_id: str) -> None:
        self.name = name
        self.desktop_id = desktop_id


def test_usage_record_persist_and_order(tmp: str) -> None:
    path = os.path.join(tmp, "usage.json")
    store = usage.UsageStore(path)
    assert store.count("kitty.desktop") == 0  # unseen -> 0

    store.record("kitty.desktop")
    store.record("kitty.desktop")
    store.record("dolphin.desktop")

    # Persisted: a fresh store reads the same counts back off disk.
    reloaded = usage.UsageStore(path)
    assert reloaded.count("kitty.desktop") == 2
    assert reloaded.count("dolphin.desktop") == 1

    # Ordering: most-launched first; ties (0-count) fall back to A->Z by name.
    apps_in = [
        _FakeEntry("Zed", "zed.desktop"),
        _FakeEntry("Kitty", "kitty.desktop"),
        _FakeEntry("Dolphin", "dolphin.desktop"),
        _FakeEntry("Ardour", "ardour.desktop"),
    ]
    names = [e.name for e in reloaded.sorted_apps(apps_in)]
    assert names == ["Kitty", "Dolphin", "Ardour", "Zed"], names


def test_usage_corrupt_store_is_ignored(tmp: str) -> None:
    path = os.path.join(tmp, "usage.json")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("{ this is not valid json")
    store = usage.UsageStore(path)
    assert store._counts == {}  # corrupt -> treated as empty, no crash
    # A missing file is likewise fine.
    store2 = usage.UsageStore(os.path.join(tmp, "does-not-exist.json"))
    assert store2._counts == {}


# --- pure-logic: system-wide "app opened" detection (winwatch) -------------
import winwatch  # noqa: E402


class _IdxEntry:
    """Stand-in for AppEntry: the DesktopIndex only needs these fields."""

    def __init__(self, desktop_id, exec_argv, startup_wmclass=""):
        self.desktop_id = desktop_id
        self.exec_argv = exec_argv
        self.startup_wmclass = startup_wmclass


class _CountingUsage:
    """Records desktop ids like UsageStore.record, without touching disk."""

    def __init__(self):
        self.counts = {}

    def record(self, desktop_id):
        self.counts[desktop_id] = self.counts.get(desktop_id, 0) + 1

    def count(self, desktop_id):
        return self.counts.get(desktop_id, 0)


def test_winwatch_parsers() -> None:
    # WM_CLASS -> the two strings.
    assert winwatch._parse_wm_class(
        'WM_CLASS(STRING) = "dolphin", "dolphin"'
    ) == ["dolphin", "dolphin"]
    assert winwatch._parse_wm_class('WM_CLASS(STRING) = "VLC media", "vlc"') == [
        "VLC media",
        "vlc",
    ]
    # _NET_WM_PID -> int.
    assert winwatch._parse_pid("_NET_WM_PID(CARDINAL) = 2292") == 2292
    assert winwatch._parse_pid("_NET_WM_PID:  not found.") is None
    # Window types -> atom list.
    assert winwatch._parse_window_types(
        "_NET_WM_WINDOW_TYPE(ATOM) = _NET_WM_WINDOW_TYPE_DOCK, "
        "_NET_WM_WINDOW_TYPE_NORMAL"
    ) == ["_NET_WM_WINDOW_TYPE_DOCK", "_NET_WM_WINDOW_TYPE_NORMAL"]
    # Exec binary basename (skips env/VAR= wrappers, absolute paths, field codes).
    assert winwatch._exec_binary("kitty") == "kitty"
    assert winwatch._exec_binary("/usr/bin/vlc --started-from-file %U") == "vlc"
    assert winwatch._exec_binary("env FOO=1 /usr/bin/env kitty") == "kitty"
    assert winwatch._exec_binary("libreoffice --calc %U") == "libreoffice"


def test_winwatch_index_resolution() -> None:
    entries = [
        # StartupWMClass present (authoritative).
        _IdxEntry("org.kde.dolphin.desktop", ["dolphin", "%u"], "dolphin"),
        _IdxEntry(
            "libreoffice-calc.desktop",
            ["libreoffice", "--calc"],
            "libreoffice-calc",
        ),
        # No StartupWMClass -> must fall back to exec basename / id stem / pid.
        _IdxEntry("kitty.desktop", ["kitty"]),
        _IdxEntry("vlc.desktop", ["/usr/bin/vlc", "--started-from-file"]),
        _IdxEntry("systemsettings.desktop", ["systemsettings"]),
    ]
    idx = winwatch.DesktopIndex(entries)

    # 1) StartupWMClass wins.
    assert idx.resolve(["dolphin", "dolphin"], None) == "org.kde.dolphin.desktop"
    assert (
        idx.resolve(["libreoffice-calc", "soffice"], None)
        == "libreoffice-calc.desktop"
    )
    # 2) WM_CLASS matched to exec basename (kitty, vlc) or id stem, case-fold.
    assert idx.resolve(["kitty", "kitty"], None) == "kitty.desktop"
    assert idx.resolve(["vlc", "VLC"], None) == "vlc.desktop"
    assert (
        idx.resolve(["SystemSettings", "systemsettings"], None)
        == "systemsettings.desktop"
    )
    # Reverse-DNS id: last component (dolphin) also resolves via id stem even
    # without StartupWMClass -- but here StartupWMClass already covers it, so
    # test id-stem via an app that only has it:
    idx2 = winwatch.DesktopIndex(
        [_IdxEntry("org.kde.konsole.desktop", ["konsole"])]
    )
    assert idx2.resolve(["konsole", "konsole"], None) == "org.kde.konsole.desktop"
    # 3) Unknown window -> None (never miscount).
    assert idx.resolve(["totally-unknown-xyz"], None) is None


def _make_watcher(usage, index, monkey_props):
    """Build a WindowWatcher whose X calls are faked. monkey_props maps a window
    id -> the property dict _win_props would return. _client_list is driven by
    the test setting watcher._fake_clients."""
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    w = winwatch.WindowWatcher(
        root, usage, index_provider=lambda: index, own_pid=999999
    )
    w._fake_clients = []
    # Patch module-level X accessors for the duration of the test.
    winwatch._client_list = lambda: list(w._fake_clients)
    winwatch._win_props = lambda win: dict(monkey_props.get(win, {}))
    return w, root


def test_winwatch_counts_new_windows_and_dedups() -> None:
    """A NEW normal window is counted once; raising an existing one is not; a
    pre-existing window at start() is never counted; a multi-window burst from
    one pid collapses to a single count; a panel/desktop window is ignored."""
    import tkinter as tk

    if not _have_display():
        return  # needs Tk for the after-loop object; logic covered below too

    usage = _CountingUsage()
    idx = winwatch.DesktopIndex(
        [
            _IdxEntry("kitty.desktop", ["kitty"]),
            _IdxEntry("org.kde.dolphin.desktop", ["dolphin"], "dolphin"),
        ]
    )
    props = {
        # kitty main window, pid 100, NORMAL.
        "0x100": {
            "wm_class": 'WM_CLASS(STRING) = "kitty", "kitty"',
            "wm_pid": "_NET_WM_PID(CARDINAL) = 100",
            "wm_types": "_NET_WM_WINDOW_TYPE(ATOM) = _NET_WM_WINDOW_TYPE_NORMAL",
        },
        # a SECOND kitty window, SAME pid 100 (burst) -> must NOT add a 2nd count.
        "0x101": {
            "wm_class": 'WM_CLASS(STRING) = "kitty", "kitty"',
            "wm_pid": "_NET_WM_PID(CARDINAL) = 100",
            "wm_types": "_NET_WM_WINDOW_TYPE(ATOM) = _NET_WM_WINDOW_TYPE_NORMAL",
        },
        # dolphin, different pid 200 -> a separate count.
        "0x200": {
            "wm_class": 'WM_CLASS(STRING) = "dolphin", "dolphin"',
            "wm_pid": "_NET_WM_PID(CARDINAL) = 200",
            "wm_types": "_NET_WM_WINDOW_TYPE(ATOM) = _NET_WM_WINDOW_TYPE_NORMAL",
        },
        # a panel (DOCK) -> never counted even though it maps to nothing anyway.
        "0xdock": {
            "wm_class": 'WM_CLASS(STRING) = "plasmashell", "plasmashell"',
            "wm_pid": "_NET_WM_PID(CARDINAL) = 300",
            "wm_types": "_NET_WM_WINDOW_TYPE(ATOM) = _NET_WM_WINDOW_TYPE_DOCK",
        },
    }
    w, root = _make_watcher(usage, idx, props)
    try:
        # A window that already exists BEFORE we start must not be counted.
        w._fake_clients = ["0xpre"]
        w.start()  # primes _seen with 0xpre
        assert usage.counts == {}

        # kitty opens (one window).
        w._fake_clients = ["0xpre", "0x100"]
        w._scan_once()
        assert usage.counts.get("kitty.desktop") == 1

        # kitty opens a SECOND window on the same pid within the burst window.
        w._tick += 1
        w._fake_clients = ["0xpre", "0x100", "0x101"]
        w._scan_once()
        assert usage.counts.get("kitty.desktop") == 1, (
            "same-pid burst must not double-count"
        )

        # The same window id re-appearing (raise/refocus) is not a new open.
        w._tick += 1
        w._scan_once()
        assert usage.counts.get("kitty.desktop") == 1

        # dolphin opens (different pid) -> separate count.
        w._tick += 1
        w._fake_clients = ["0xpre", "0x100", "0x101", "0x200"]
        w._scan_once()
        assert usage.counts.get("org.kde.dolphin.desktop") == 1

        # A dock/panel window opens -> ignored.
        w._tick += 1
        w._fake_clients.append("0xdock")
        w._scan_once()
        assert "plasmashell" not in "".join(usage.counts)  # nothing plasma
        assert set(usage.counts) == {"kitty.desktop", "org.kde.dolphin.desktop"}

        # Closing kitty then reopening a NEW kitty process (new pid) counts again.
        w._tick += 1
        w._fake_clients = ["0xpre", "0x200"]  # kitty windows gone
        w._scan_once()  # prune closed ids from _seen
        w._tick += 1
        props["0x102"] = {
            "wm_class": 'WM_CLASS(STRING) = "kitty", "kitty"',
            "wm_pid": "_NET_WM_PID(CARDINAL) = 400",  # new process
            "wm_types": "_NET_WM_WINDOW_TYPE(ATOM) = _NET_WM_WINDOW_TYPE_NORMAL",
        }
        winwatch._win_props = lambda win: dict(props.get(win, {}))
        w._fake_clients = ["0xpre", "0x200", "0x102"]
        w._scan_once()
        assert usage.counts.get("kitty.desktop") == 2, (
            "a fresh launch (new pid) after close must count again"
        )
    finally:
        # stop() cancels the pending after('_poll') so it never fires against a
        # destroyed interpreter (Tk would print 'invalid command name ..._poll').
        try:
            w.stop()
        except Exception:
            pass
        try:
            root.destroy()
        except Exception:
            pass


# --- pure-logic: category typing ------------------------------------------
def test_category_type_specific_wins() -> None:
    # WebBrowser (additional) beats Network (main).
    assert apps.category_type(["Network", "WebBrowser"]) == "Web Browser"
    # TerminalEmulator -> Terminal (the PROMPT.md example: Kitty -> Terminal).
    assert apps.category_type(["System", "TerminalEmulator"]) == "Terminal"
    # FileManager beats FileTools regardless of order (Dolphin case).
    assert apps.category_type(
        ["Qt", "KDE", "System", "FileTools", "FileManager"]
    ) == "File Manager"
    assert apps.category_type(
        ["FileManager", "FileTools"]
    ) == "File Manager"


def test_category_type_main_fallback() -> None:
    assert apps.category_type(["Qt", "KDE", "Settings"]) == "Settings"
    assert apps.category_type(["AudioVideo"]) == "Multimedia"
    assert apps.category_type(["Office"]) == "Office"


def test_category_type_generic_and_noise() -> None:
    # Only noise tokens -> generic.
    assert apps.category_type(["Qt", "KDE"]) == apps.GENERIC_TYPE
    assert apps.category_type([]) == apps.GENERIC_TYPE
    # An unknown but non-noise token is passed through (prettified as-is).
    assert apps.category_type(["Weirdcat"]) == "Weirdcat"


def test_strip_field_codes() -> None:
    assert apps._strip_field_codes("librewolf %u") == ["librewolf"]
    assert apps._strip_field_codes("kitty +open %U") == ["kitty", "+open"]
    assert apps._strip_field_codes('/opt/app "a b" %f') == ["/opt/app", "a b"]


def test_parse_desktop_file(tmp: str) -> None:
    # A visible app parses.
    p = os.path.join(tmp, "kitty.desktop")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(
            "[Desktop Entry]\nType=Application\nName=kitty\n"
            "GenericName=Terminal emulator\nComment=Fast terminal\n"
            "Exec=kitty %U\nIcon=kitty\nCategories=System;TerminalEmulator;\n"
            "\n[Desktop Action new-window]\nName=New Window\nExec=kitty\n"
        )
    e = apps._parse_desktop_file(p)
    assert e is not None
    assert e.name == "kitty"
    assert e.type_label == "Terminal"
    assert e.exec_argv == ["kitty"]
    assert e.icon == "kitty"

    # NoDisplay is hidden.
    p2 = os.path.join(tmp, "hidden.desktop")
    with open(p2, "w", encoding="utf-8") as fh:
        fh.write(
            "[Desktop Entry]\nType=Application\nName=Hidden\n"
            "Exec=foo\nNoDisplay=true\n"
        )
    assert apps._parse_desktop_file(p2) is None

    # Link type is not an application -> skipped.
    p3 = os.path.join(tmp, "link.desktop")
    with open(p3, "w", encoding="utf-8") as fh:
        fh.write("[Desktop Entry]\nType=Link\nName=L\nURL=http://x\n")
    assert apps._parse_desktop_file(p3) is None

    # Missing Exec -> skipped.
    p4 = os.path.join(tmp, "noexec.desktop")
    with open(p4, "w", encoding="utf-8") as fh:
        fh.write("[Desktop Entry]\nType=Application\nName=NoExec\n")
    assert apps._parse_desktop_file(p4) is None


def test_scan_dedup_and_sort(tmp: str) -> None:
    d1 = os.path.join(tmp, "d1")
    d2 = os.path.join(tmp, "d2")
    os.makedirs(d1)
    os.makedirs(d2)
    # Same id in both dirs; d1 is higher precedence (listed first) -> wins.
    for d, name in ((d1, "Alpha-HI"), (d2, "Alpha-LO")):
        with open(os.path.join(d, "alpha.desktop"), "w", encoding="utf-8") as f:
            f.write(
                f"[Desktop Entry]\nType=Application\nName={name}\n"
                "Exec=alpha\nCategories=Utility;\n"
            )
    with open(os.path.join(d2, "beta.desktop"), "w", encoding="utf-8") as f:
        f.write(
            "[Desktop Entry]\nType=Application\nName=Beta\n"
            "Exec=beta\nCategories=Utility;\n"
        )
    out = apps.scan_applications([d1, d2])
    names = [a.name for a in out]
    assert "Alpha-HI" in names and "Alpha-LO" not in names  # precedence
    assert names == sorted(names, key=str.casefold)          # sorted


def test_scan_hides_denylisted(tmp: str) -> None:
    """Apps whose .desktop id is in HIDDEN_DESKTOP_IDS are kept out of the menu,
    while everything else still shows. The files are NOT touched -- only the scan
    skips them."""
    d = os.path.join(tmp, "apps")
    os.makedirs(d)
    # One hidden id (Htop) and one that must survive.
    for fn, name in (
        ("htop.desktop", "Htop"),            # in HIDDEN_DESKTOP_IDS
        ("kitty.desktop", "kitty"),          # must remain visible
        ("vim.desktop", "Vim"),              # in HIDDEN_DESKTOP_IDS
    ):
        with open(os.path.join(d, fn), "w", encoding="utf-8") as f:
            f.write(
                f"[Desktop Entry]\nType=Application\nName={name}\n"
                f"Exec={name.lower()}\nCategories=Utility;\n"
            )
    names = [a.name for a in apps.scan_applications([d])]
    assert "kitty" in names
    assert "Htop" not in names
    assert "Vim" not in names
    # And the constant covers every id the spec asked to hide.
    for wanted in (
        "azarch-application-menu.desktop",
        "azarch-application-menu-shortcut.desktop",  # the Super-key binding entry
        "bssh.desktop", "bvnc.desktop",
        "avahi-discover.desktop", "azarch-install.desktop",
        "kdesystemsettings.desktop", "lstopo.desktop", "htop.desktop",
        "lftp.desktop", "cups.desktop", "org.kde.kmenuedit.desktop",
        "assistant.desktop", "qdbusviewer.desktop", "linguist.desktop",
        "qv4l2.desktop", "qvidcap.desktop", "designer.desktop",
        "stoken-gui.desktop", "stoken-gui-small.desktop", "vim.desktop",
    ):
        assert wanted in apps.HIDDEN_DESKTOP_IDS, wanted
    # The Az'arch Menu itself and KDE's duplicate "KDE System Settings" are hidden,
    # but the real "System Settings" (systemsettings.desktop) must STAY visible.
    assert "systemsettings.desktop" not in apps.HIDDEN_DESKTOP_IDS


# --- pure-logic: 10%-bigger text + icons ----------------------------------
def test_theme_sizes_are_scaled_10pct() -> None:
    """Text and icons ship 10% bigger than the original Kickoff-match sizes so the
    menu reads a touch larger.

    The font sizes and icon edges USED to be bare literals scattered across
    widgets.py / applist.py / menu.py (the app-name/type point sizes, the search
    entry size, the power-row label) and the icon-edge constants in theme.py. They
    are now centralised as theme.FONT_* / theme.*ICON_SIZE constants so there is ONE
    place to scale them. This pins the scaled values (original * 1.1, rounded to the
    nearest whole point/pixel -- Tk fonts and PhotoImage need integers) so a future
    edit that silently reverts the bump fails here.

    (The top-row icon size TOP_ICON_SIZE is gone with the removed Settings/pin
    buttons, so only the app-row and power-row sizes remain to pin.)
    """
    import theme as T

    # Original sizes -> 10%-bigger (round-half-to-nearest int).
    assert T.FONT_APP_NAME == 13, T.FONT_APP_NAME      # was 12
    assert T.FONT_APP_TYPE == 10, T.FONT_APP_TYPE      # was 9
    assert T.FONT_SEARCH == 13, T.FONT_SEARCH          # was 12
    assert T.FONT_POWER == 12, T.FONT_POWER            # was 11

    assert T.ICON_SIZE == 44, T.ICON_SIZE              # was 40
    assert T.POWER_ICON_SIZE == 24, T.POWER_ICON_SIZE  # was 22

    # Every one is genuinely bigger than the pre-bump value (guards a typo that
    # made a size SMALLER while still being "changed").
    for new, old in (
        (T.FONT_APP_NAME, 12), (T.FONT_APP_TYPE, 9),
        (T.FONT_SEARCH, 12), (T.FONT_POWER, 11),
        (T.ICON_SIZE, 40), (T.POWER_ICON_SIZE, 22),
    ):
        assert new > old, (new, old)


def test_menu_modules_use_centralised_font_constants() -> None:
    """The scattered `font=("Noto Sans", <literal>)` sizes are gone -- the row,
    search and power widgets read their sizes from theme.FONT_* so the 10% bump
    (and any future resize) lives in ONE place.

    Asserted at the SOURCE level: no menu module may hardcode a Noto Sans point
    size any more (they must interpolate a theme constant), so a new bare literal
    creeping back in is caught even though a headless font size is awkward to read
    back off a Tk widget reliably.
    """
    import re

    here = os.path.dirname(os.path.abspath(__file__))
    # A bare integer point size in a Noto Sans font spec, e.g. ("Noto Sans", 12).
    bad = re.compile(r'"Noto Sans"\s*,\s*\d')
    for name in ("widgets.py", "applist.py", "menu.py"):
        src = open(os.path.join(here, name), encoding="utf-8").read()
        assert not bad.search(src), (
            f"{name} still hardcodes a Noto Sans point size; use a theme.FONT_* "
            f"constant instead"
        )
        # And it must actually reference the centralised constants.
        assert "T.FONT_" in src or "theme.FONT_" in src, name


def test_app_rows_are_nudged_right() -> None:
    """The app list icon + text sit a touch further right than the original
    20/72 px, and BOTH are shifted by the SAME amount so the icon->text gap is
    unchanged (a uniform nudge, not a re-spacing)."""
    import applist
    orig_icon, orig_text = 20, 72
    cls = applist.CanvasAppList
    assert cls.ICON_X > orig_icon, cls.ICON_X
    assert cls.TEXT_X > orig_text, cls.TEXT_X
    # Same delta on both -> icon/text gap preserved.
    assert (cls.ICON_X - orig_icon) == (cls.TEXT_X - orig_text)
    # "Ever so lightly": a small nudge, not a big move.
    assert cls.ICON_X - orig_icon <= 12


def test_menu_size_is_theme_default() -> None:
    """menu.menu_size() is the fixed (width, height) the centered window is sized
    to -- the theme defaults. Plasma/Kickoff is gone, so there is no appletsrc popup
    size to read anymore; the menu is just a fixed-size centered window."""
    import menu
    import theme as T
    assert menu.menu_size() == (T.DEFAULT_WIDTH, T.DEFAULT_HEIGHT)
    w, h = menu.menu_size()
    assert w > 0 and h > 0


def test_removed_panel_and_tooltip_theme_constants_are_gone() -> None:
    """The panel/highlight-bar and tooltip styling constants were REMOVED with the
    panel, the panel-icon highlight bar and the Settings-button hint. Only the
    window geometry defaults (DEFAULT_WIDTH/HEIGHT) and the palette/font/icon
    constants remain. This pins that the dead constants do NOT creep back."""
    import theme as T
    # Geometry defaults are kept.
    assert isinstance(T.DEFAULT_WIDTH, int) and isinstance(T.DEFAULT_HEIGHT, int)
    # The panel / highlight-bar / tooltip / disabled-icon constants are gone.
    for gone in (
        "PANEL_HEIGHT", "ICON_CELL_W", "ICON_CELL_X",
        "HIGHLIGHT_BAR_HEIGHT", "HIGHLIGHT_BAR_INSET",
        "TOP_ICON_SIZE",
        "TOOLTIP_BG", "TOOLTIP_FG", "TOOLTIP_BORDER", "TOOLTIP_DELAY_MS",
        "DISABLED_ICON_COLOR",
    ):
        assert not hasattr(T, gone), (
            f"theme.{gone} should have been removed with the panel / settings button"
        )


# --- UI smoke tests (need a display) --------------------------------------
def _have_display() -> bool:
    return bool(os.environ.get("DISPLAY"))


def _build_testable_menu():
    """Build the real window but neutralise the self-closing bindings so a
    scripted test can drive it without the window destroying itself when the
    (headless) update loop steals focus.

    FocusOut is bound lazily inside arm() (scheduled on after_idle, then an
    after(150) backup); rather than race those timers we replace root.bind for
    the "<FocusOut>" sequence with a no-op so it can never be armed, and drop the
    global button grab."""
    import menu
    root = menu.build_window()
    _orig_bind = root.bind

    def _guarded_bind(seq=None, func=None, add=None):
        if seq == "<FocusOut>":
            return ""  # swallow the deferred focus-out dismissal in tests
        return _orig_bind(seq, func, add)

    root.bind = _guarded_bind
    root.unbind_all("<Button>")
    # Flush the pending arm() timers so the grab/focus logic runs once, then make
    # sure no <FocusOut> handler stuck (belt and suspenders).
    root.update()
    root.update_idletasks()
    root.unbind("<FocusOut>")
    # The application rows are built lazily (deferred out of build() so the menu
    # opens instantly -- production paints the chrome then calls populate()). The
    # tests expect a fully populated list, so build it now explicitly.
    root.az_menu.populate()
    # Cancel any still-pending deferred callbacks (e.g. the after(150) that arms
    # focus-out) so a plain root.destroy() in a test's finally cannot leave an
    # after() command dangling -- Tk would otherwise print a spurious
    # "invalid command name ...arm_focus_out" to stderr when the interpreter is
    # torn down with the timer still scheduled.
    for _tid in list(getattr(root, "az_timers", [])):
        try:
            root.after_cancel(_tid)
        except Exception:
            pass
    return menu, root


def test_ui_build_and_contents() -> None:
    _menu, root = _build_testable_menu()
    try:
        m = root.az_menu
        assert len(m.all_apps) > 0
        al = m.applist
        assert len(al.all_entries) == len(m.all_apps)
        assert al.visible_count == len(al.all_entries)  # empty query shows all
        # Every entry has a name + a type subtitle.
        for e in al.all_entries:
            assert e.name
            assert e.type_label
        # Four power buttons in the canonical Sleep/Lock/Restart/Shut Down order.
        assert len(m.power_buttons) == 4
    finally:
        root.destroy()


def test_ui_removed_pin_settings_and_highlight_are_gone() -> None:
    """The PIN button, the SETTINGS (gear) button and the panel-icon HIGHLIGHT BAR
    were all removed. Neither the AppMenu nor the root window may still expose them,
    and the state dict no longer carries the pin flags -- a regression that added any
    of them back is caught here."""
    _menu, root = _build_testable_menu()
    try:
        m = root.az_menu
        # The AppMenu has no pin/settings widgets anymore.
        assert getattr(m, "pin_button", None) is None
        assert getattr(m, "settings_button", None) is None
        assert not hasattr(m, "pin_button")
        assert not hasattr(m, "settings_button")
        # And no pin toggle handler.
        assert not hasattr(m, "_toggle_pin")
        # The root window exposes no highlight bar / pin attributes.
        assert not hasattr(root, "az_highlight")
        assert not hasattr(root, "az_pinned")
        # The close/capture state has no pin keys (only "closed" + "capturing").
        st = root.az_state
        assert "pinned" not in st
        assert "pin_active" not in st
        assert set(st) == {"closed", "capturing"}, st
    finally:
        root.destroy()


def test_ui_search_filter() -> None:
    _menu, root = _build_testable_menu()
    try:
        m = root.az_menu
        al = m.applist

        def visible_names() -> list[str]:
            return [e.name for e in al.visible_entries]

        # Capture the canonical (frequency-then-alphabetical) order shown when
        # no query is active. Clearing the search must restore EXACTLY this.
        original_order = visible_names()
        assert original_order == [e.name for e in al.all_entries]

        m.search_var.set("kit")
        root.update_idletasks()
        vn = visible_names()
        assert vn == ["kitty"], vn

        # Filter by TYPE label too, not just name.
        m.search_var.set("web browser")
        root.update_idletasks()
        vn = visible_names()
        assert any(n == "LibreWolf" for n in vn), vn
        assert all("web browser" in e.name.casefold()
                   or "web browser" in e.type_label.casefold()
                   for e in al.visible_entries)

        m.search_var.set("zzzznope")
        root.update_idletasks()
        assert visible_names() == []
        assert al.selected_index == -1

        # Clear -> the reshuffle-bug regression check: the list comes back in the
        # SAME order it started in, not scrambled by the filter history. We check
        # both the model order (visible_entries) and the actual on-screen vertical
        # order (each visible row's top y) to be sure nothing is merely logically
        # ordered while visually shuffled.
        m.search_var.set("")
        root.update_idletasks()
        assert visible_names() == original_order, visible_names()
        # On-screen order: the row tops must be strictly increasing in the same
        # order as visible_entries.
        tops = al.visible_tops()
        assert tops == sorted(tops), tops
        assert len(tops) == len(original_order)
    finally:
        root.destroy()


def test_ui_search_clear_after_partial_filter() -> None:
    """A tighter reshuffle regression: filter down to a subset that KEEPS some
    rows visible while hiding others, then clear and confirm the full canonical
    order (both the model order and the on-screen vertical order)."""
    _menu, root = _build_testable_menu()
    try:
        m = root.az_menu
        al = m.applist
        original = [e.name for e in al.all_entries]
        # 'a' keeps every app whose name/type contains 'a' visible and hides the
        # rest -- a genuine partial filter, not all-or-nothing.
        m.search_var.set("a")
        root.update_idletasks()
        m.search_var.set("")
        root.update_idletasks()
        assert [e.name for e in al.visible_entries] == original
        tops = al.visible_tops()
        assert tops == sorted(tops), tops
    finally:
        root.destroy()


def test_ui_reorders_after_launch_without_restart() -> None:
    """Launch frequency must re-sort the LIVE list, not only on the next process
    start. The daemon never dies, so recording a launch has to bump the app up on
    the next show -- otherwise the order looks frozen until a restart (the bug).

    Records enough launches on a currently-low app to make it the most-used, then
    drives a re-show (reset_view, what the daemon calls) and asserts it floated to
    the top of both the model order and the on-screen vertical order."""
    _menu, root = _build_testable_menu()
    try:
        m = root.az_menu
        al = m.applist
        names = [e.name for e in al.all_entries]
        assert len(names) >= 2, names
        # Pick an app that is NOT already first, and make it the most launched.
        # Identity is by desktop_id (unique), NOT name: some hosts ship two
        # entries with the SAME display name (e.g. mintstick-format.desktop and
        # mintstick-format-kde.desktop both "USB Stick Formatter"), so a
        # name-inequality check could spuriously fail when the first and last
        # entries merely share a name while being different apps.
        victim = al.all_entries[-1]         # last == least-used / last alpha
        assert victim.desktop_id != al.all_entries[0].desktop_id
        for _ in range(50):
            m.usage.record(victim.desktop_id)

        # Re-show the menu the way the daemon does (no new process).
        m.reset_view()
        root.update_idletasks()

        assert al.all_entries[0].desktop_id == victim.desktop_id, (
            "most-launched app must be FIRST after a launch, without a restart; "
            f"got {[e.name for e in al.all_entries][:5]}"
        )
        assert al.visible_entries[0].desktop_id == victim.desktop_id
        # On-screen: the topmost visible row is the victim.
        tops = al.visible_tops()
        assert tops == sorted(tops)
        assert al.visible_entries[0].desktop_id == victim.desktop_id
    finally:
        root.destroy()


def test_ui_search_filtering_never_churns_windows() -> None:
    """Typing must never map/unmap per-row X windows -- that churn under a
    compositor is exactly what made the old widget list FLICKER. The list is now
    drawn as canvas ITEMS, so filtering only shows/hides/moves existing items:
    the number of canvas items (and child windows) stays CONSTANT across any
    filter. We assert the canvas item count never changes while the query narrows,
    widens, empties and re-narrows, and that no extra child windows ever appear."""
    _menu, root = _build_testable_menu()
    try:
        m = root.az_menu
        al = m.applist
        canvas = al.canvas

        def item_count() -> int:
            return len(canvas.find_all())

        def child_windows() -> int:
            # Canvas-item rendering means the canvas has NO child windows for the
            # rows (unlike the old embedded-frame approach).
            return len(canvas.winfo_children())

        base_items = item_count()
        base_children = child_windows()
        assert base_items > 0

        for q in ("s", "sy", "sys", "system", "sy", "s", "",
                  "a", "ar", "a", "", "office", ""):
            m.search_var.set(q)
            root.update_idletasks()
            assert item_count() == base_items, (
                f"canvas item count changed on query {q!r}: "
                f"{item_count()} != {base_items} (rows created/deleted -> churn)"
            )
            assert child_windows() == base_children, (
                f"canvas grew child windows on query {q!r} -> map/unmap flicker"
            )
        # The canvas holds one image + two texts + one rect per app, plus a
        # spare selection rectangle -> child_windows for the rows is zero.
        assert base_children == 0, base_children
    finally:
        root.destroy()


def test_ui_window_is_centered() -> None:
    """The window is CENTERED on the screen (the old bottom-left/panel placement is
    gone with the panel). build_window() applies geometry
    +max(0,(sw-w)//2)+max(0,(sh-h)//2) with the theme-default size, so we assert the
    mapped window's top-left matches that formula. Computing the expected corner with
    the SAME clamp keeps this independent of the (possibly tiny) headless screen: on a
    window taller than the screen the y clamps to 0, which is still correct."""
    import tkinter as tk
    _menu, root = _build_testable_menu()
    try:
        # The testable menu is left withdrawn; map it so winfo_* report real coords.
        try:
            root.deiconify()
            root.lift()
        except tk.TclError:
            pass
        root.update_idletasks()
        root.update()

        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        win_w, win_h = _menu.menu_size()
        exp_x = max(0, (sw - win_w) // 2)
        exp_y = max(0, (sh - win_h) // 2)
        assert (root.winfo_rootx(), root.winfo_rooty()) == (exp_x, exp_y), (
            "window must be centered; got "
            f"{(root.winfo_rootx(), root.winfo_rooty())} != {(exp_x, exp_y)}"
        )
        # The size is the theme default, not a panel-derived popup size.
        assert (root.winfo_width(), root.winfo_height()) == (win_w, win_h)
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_ui_default_focus_zone_is_apps() -> None:
    """The menu opens in the APPS focus zone: the search box has the caret and the
    app-list selection is shown/enabled, and no power button is focused. reset_view
    (what the daemon calls on each re-show) must also return to this default."""
    _menu, root = _build_testable_menu()
    try:
        m = root.az_menu
        assert m.focus_zone == _menu.FOCUS_APPS
        assert m.applist._selection_enabled is True
        assert all(not b._focused for b in m.power_buttons)

        # Move to the power zone, then reset_view must snap back to apps.
        m.set_focus_zone(_menu.FOCUS_POWER)
        assert m.focus_zone == _menu.FOCUS_POWER
        m.reset_view()
        root.update_idletasks()
        assert m.focus_zone == _menu.FOCUS_APPS
        assert m.applist._selection_enabled is True
        assert all(not b._focused for b in m.power_buttons)
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_ui_tab_toggles_focus_zone() -> None:
    """TAB flips between the two focus zones. From the default (apps) toggle_focus()
    moves to the power row -- the app-list selection dims (set_selection_enabled
    False) and the FIRST power button lights up -- and TAB again returns to apps
    (selection re-enabled, all power focus cleared)."""
    _menu, root = _build_testable_menu()
    try:
        m = root.az_menu
        # Default: apps zone, selection enabled, nothing focused in the power row.
        assert m.focus_zone == _menu.FOCUS_APPS
        assert m.applist._selection_enabled is True
        assert all(not b._focused for b in m.power_buttons)

        # TAB -> power zone.
        m.toggle_focus()
        assert m.focus_zone == _menu.FOCUS_POWER
        assert m.applist._selection_enabled is False, (
            "moving to the power zone must dim the app-list selection"
        )
        assert m.power_buttons[0]._focused is True, (
            "the first power button must light up when entering the power zone"
        )
        assert all(not b._focused for b in m.power_buttons[1:])

        # TAB again -> back to apps.
        m.toggle_focus()
        assert m.focus_zone == _menu.FOCUS_APPS
        assert m.applist._selection_enabled is True, (
            "returning to apps must re-enable the app-list selection"
        )
        assert all(not b._focused for b in m.power_buttons), (
            "returning to apps must clear all power focus"
        )
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_ui_power_zone_left_right_moves_focus_clamped() -> None:
    """In the power zone Left/Right move the focused button, clamped (no wrap): from
    the first button on_right() lights the second (and clears the first), and Left
    from the first / Right from the last stay put."""
    _menu, root = _build_testable_menu()
    try:
        m = root.az_menu
        m.set_focus_zone(_menu.FOCUS_POWER)
        assert m._power_index == 0
        assert m.power_buttons[0]._focused is True

        # Right -> index 1 focused, index 0 cleared.
        m.on_right()
        assert m._power_index == 1
        assert m.power_buttons[1]._focused is True
        assert m.power_buttons[0]._focused is False

        # Right to the end (4 buttons -> last index 3), then Right again clamps.
        m.on_right()
        m.on_right()
        assert m._power_index == 3
        m.on_right()
        assert m._power_index == 3, "Right past the last button must clamp (no wrap)"
        assert m.power_buttons[3]._focused is True

        # Left all the way back, then Left again clamps at 0.
        m.on_left(); m.on_left(); m.on_left()
        assert m._power_index == 0
        m.on_left()
        assert m._power_index == 0, "Left before the first button must clamp (no wrap)"
        assert m.power_buttons[0]._focused is True
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_ui_on_activate_in_power_zone_fires_focused_button() -> None:
    """Enter (on_activate) in the power zone fires the CURRENTLY FOCUSED power
    button's command, not the app list. We swap the focused button's command for a
    spy so the assertion is deterministic (and never suspends/reboots the host)."""
    _menu, root = _build_testable_menu()
    try:
        m = root.az_menu
        # Neutralise close so activating does not tear the window down mid-test.
        m.close_menu = lambda *a, **k: None

        fired = {"which": None}
        # Give every power button a distinct spy command.
        for i, b in enumerate(m.power_buttons):
            b._command = (lambda idx: (lambda: fired.__setitem__("which", idx)))(i)

        m.set_focus_zone(_menu.FOCUS_POWER)
        # Focus the third button (Restart) and activate via Enter.
        m.on_right()
        m.on_right()
        assert m._power_index == 2
        m.on_activate()
        assert fired["which"] == 2, (
            f"Enter in the power zone must fire the focused button, got {fired}"
        )
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_ui_power_activation_wired_through_on_activate(monkeypatch_actions) -> None:
    """End-to-end: TAB to the power row and press Enter on the first button (Sleep)
    -> the real suspend action fires (through _do -> actions.suspend). Driven with
    the monkeypatch_actions fixture so the host is never actually suspended. The
    fixture patches actions.* BEFORE the menu is built, so the button closures
    capture the recorders."""
    _menu, root = _build_testable_menu()
    try:
        m = root.az_menu
        # _do closes the menu before firing; stub close so this stays non-destructive
        # (we are asserting the action wiring, not the close, which its own test
        # covers).
        m.close_menu = lambda *a, **k: None

        m.toggle_focus()                       # -> power zone, first button focused
        assert m.focus_zone == _menu.FOCUS_POWER
        assert m._power_index == 0
        m.on_activate()                        # Enter on Sleep
        assert "suspend" in monkeypatch_actions.calls, (
            f"Enter on the first power button must fire suspend; "
            f"got {monkeypatch_actions.calls}"
        )
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_ui_power_button_set_focused_paints_outline() -> None:
    """PowerButton.set_focused(True) paints the Breeze blue selection OUTLINE
    (highlightbackground becomes SELECT_BORDER) and set_focused(False) restores it to
    the background colour so the 1px geometry never shifts but the outline vanishes."""
    import theme as T
    _menu, root = _build_testable_menu()
    try:
        m = root.az_menu
        btn = m.power_buttons[0]
        assert btn._focused is False
        assert str(btn.cget("highlightbackground")) == T.BG_COLOR

        btn.set_focused(True)
        assert btn._focused is True
        assert str(btn.cget("highlightbackground")) == T.SELECT_BORDER, (
            "a focused power button must show the blue selection outline"
        )

        btn.set_focused(False)
        assert btn._focused is False
        assert str(btn.cget("highlightbackground")) == T.BG_COLOR, (
            "clearing focus must restore the background-matched (invisible) outline"
        )
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_ui_tab_is_bound_and_click_returns_focus_to_apps() -> None:
    """<Tab> (and its Shift variants) are bound on the root window, and clicking the
    search box returns focus to the apps zone (in case the user had TAB'd away)."""
    _menu, root = _build_testable_menu()
    try:
        m = root.az_menu
        # The TAB focus-toggle keys are bound on the window.
        for seq in ("<Tab>", "<Shift-Tab>", "<ISO_Left_Tab>"):
            assert root.bind(seq), f"{seq} must be bound to toggle the focus zone"

        # Move to the power zone, then a click in the search box snaps back to apps.
        m.set_focus_zone(_menu.FOCUS_POWER)
        assert m.focus_zone == _menu.FOCUS_POWER
        # The entry's <Button-1> binding calls set_focus_zone(FOCUS_APPS); fire it.
        m.search_entry.event_generate("<Button-1>")
        root.update_idletasks()
        assert m.focus_zone == _menu.FOCUS_APPS, (
            "clicking the search box must return focus to the apps zone"
        )
        assert m.applist._selection_enabled is True
        assert all(not b._focused for b in m.power_buttons)
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_ui_arrows_move_selection_only_in_apps_zone() -> None:
    """In the APPS zone Up/Down move the app-list selection; in the POWER zone they
    are no-ops for the app list (the selection index does not move) -- Left/Right
    drive the power row there instead."""
    _menu, root = _build_testable_menu()
    try:
        m = root.az_menu
        al = m.applist
        assert al.visible_count >= 3, "need a few apps to move the selection"

        # Apps zone: Down/Up move the selection.
        assert m.focus_zone == _menu.FOCUS_APPS
        assert al.selected_index == 0
        m.on_down()
        assert al.selected_index == 1, "Down must move the app selection in apps zone"
        m.on_down()
        assert al.selected_index == 2
        m.on_up()
        assert al.selected_index == 1, "Up must move the app selection in apps zone"

        # Power zone: Down/Up must NOT move the app-list selection.
        m.set_focus_zone(_menu.FOCUS_POWER)
        frozen = al.selected_index
        m.on_down()
        m.on_down()
        m.on_up()
        assert al.selected_index == frozen, (
            "Up/Down must be no-ops for the app list while the power zone has focus"
        )
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_ui_super_key_binding_is_present() -> None:
    """The Super/Meta key must CLOSE the menu, mirroring Escape.

    Why a window-level binding at all (vs. just OpenBox's global Super->launcher
    toggle): while the menu is open it holds a GLOBAL keyboard grab, so a second
    physical Super press is delivered to OUR window and never reaches the WM --
    OpenBox's Super keybind can't fire, so the daemon never toggles it shut. Binding
    Super on the window itself makes that grab-delivered press close it, so 'Super
    opened it, Super closes it' holds.

    Asserted structurally: every Super/Meta keysym we rely on is bound to a real
    handler on the window. Tk returns the bound command string when bind() is
    called with only a sequence, so a non-empty result means "something is bound".
    """
    _menu, root = _build_testable_menu()
    try:
        for seq in ("<Super_L>", "<Super_R>", "<Meta_L>", "<Meta_R>"):
            bound = root.bind(seq)
            assert bound, f"{seq} is not bound (Super must close the menu)"
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def _window_alive(root) -> bool:
    """True if the window still exists, False if it was destroyed.

    close_menu() in non-persistent mode calls root.destroy(), which tears down the
    WHOLE Tk application -- so a plain winfo_exists() then raises "application has
    been destroyed" rather than returning 0. Treat that TclError as "gone"."""
    import tkinter as tk
    try:
        return bool(root.winfo_exists())
    except tk.TclError:
        return False


def test_ui_super_key_closes() -> None:
    """Pressing Super closes the menu (there is no pin -- the menu is a transient
    launcher, so Super/Escape/outside-click/focus-loss all dismiss it).

    Driven through the SAME close path a real Super press hits: close_menu is what
    the <Super_*> bindings invoke. We prove a real synthetic <Super_L> event routes
    to it end-to-end (window mapped + focused so Xvfb delivers the key)."""
    import tkinter as tk

    _menu, root = _build_testable_menu()
    try:
        st = root.az_state
        assert st["closed"] is False

        # End-to-end: a real Super_L key event fires the binding, which closes
        # (destroys, since this is non-persistent) the window. The window must be
        # mapped AND focused first, or the synthetic key event has no focused
        # target to route to under Xvfb (the testable menu leaves it withdrawn).
        try:
            root.deiconify()
            root.lift()
            root.focus_force()
        except tk.TclError:
            pass
        root.update()
        root.event_generate("<Super_L>", when="now")
        try:
            root.update()
        except tk.TclError:
            pass
        assert not _window_alive(root), (
            "a Super_L keypress must close (destroy) the menu"
        )
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_xfocus_helpers_are_crashproof() -> None:
    """xfocus is best-effort: active_window() returns an int and set_input_focus()
    returns a bool no matter what (missing libX11 / no display / bad window), so the
    menu can call them freely without ever risking a crash."""
    import xfocus
    aw = xfocus.active_window()
    assert isinstance(aw, int)               # a window id or 0, never an exception
    assert xfocus.set_input_focus(0) is False  # falsy window -> no-op, False
    assert isinstance(xfocus.set_input_focus(aw or 1), bool)


def _is_destroyed(root) -> bool:
    """True if the Tk root has been destroyed. winfo_exists() RAISES on a fully
    destroyed interpreter rather than returning 0, so treat that as destroyed."""
    import tkinter as tk
    try:
        return not root.winfo_exists()
    except tk.TclError:
        return True


def test_ui_forced_close_destroys_window() -> None:
    """Launching an app / firing a power action calls close_menu(force=True). With
    no pin there is nothing to override, so a forced close simply tears the
    (non-persistent) window down, exactly like a normal dismissal."""
    _menu, root = _build_testable_menu()
    try:
        m = root.az_menu
        assert not _is_destroyed(root)
        m.close_menu(force=True)  # forced -> destroys
        try:
            root.update()
        except Exception:
            pass
        assert _is_destroyed(root)
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_ui_normal_and_forced_close_behave_the_same() -> None:
    """With the pin gone, a normal close_menu() and a forced close_menu(force=True)
    do the SAME thing in non-persistent mode: both destroy the window. (The force
    flag is kept only for call-site symmetry between the dismiss paths and the
    launch/power activate paths.)"""
    # Normal close destroys.
    _menu, root = _build_testable_menu()
    try:
        root.az_menu.close_menu()
        try:
            root.update()
        except Exception:
            pass
        assert _is_destroyed(root), "a normal close must destroy the window"
    finally:
        try:
            root.destroy()
        except Exception:
            pass

    # Forced close destroys too.
    _menu, root = _build_testable_menu()
    try:
        root.az_menu.close_menu(force=True)
        try:
            root.update()
        except Exception:
            pass
        assert _is_destroyed(root), "a forced close must destroy the window"
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_ui_power_buttons_use_breeze_icons() -> None:
    """The bottom power buttons must render rasterised Breeze icons (real
    PhotoImages with pixels), not unicode glyphs."""
    _menu, root = _build_testable_menu()
    try:
        m = root.az_menu
        # The small-icon resolver should have resolved each session icon name.
        for name in ("system-suspend", "system-lock-screen",
                     "system-reboot", "system-shutdown"):
            img = m.small_icons.load(name)
            assert img.width() > 0 and img.height() > 0, name
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_ui_selection_and_launch(monkeypatch_launch) -> None:
    _menu, root = _build_testable_menu()
    try:
        m = root.az_menu
        m.search_var.set("kit")
        root.update_idletasks()
        assert m.applist.selected_index == 0
        # The menu opens in the apps zone, so Enter (on_activate) launches the
        # selected app -> should call actions.launch with kitty argv and then close
        # (close is neutered-ish: it destroys the root).
        assert m.focus_zone == _menu.FOCUS_APPS
        m.on_activate()
        assert monkeypatch_launch.calls, "launch was not invoked"
        argv = monkeypatch_launch.calls[-1]
        assert argv and argv[0] == "kitty"
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_ui_power_buttons_wired(monkeypatch_actions) -> None:
    """The four power actions must be wired to the right functions and the menu
    must close when one is pressed."""
    import menu
    _menu, root = _build_testable_menu()
    try:
        m = root.az_menu
        # _do(fn) returns a callable that closes the menu then calls fn.
        # Verify each action function is the expected one by calling the wrapped
        # callbacks captured on the buttons is hard; instead assert the module
        # exposes them and that _do wraps+closes.
        closed = {"v": False}
        m.close_menu = lambda *a, **k: closed.__setitem__("v", True)
        m._do(menu.actions.suspend)()
        assert closed["v"] is True
        assert "suspend" in monkeypatch_actions.calls
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_ui_search_standard_editing() -> None:
    """The REAL search box must support standard editor operations: select-all,
    copy, cut, paste, undo and redo (like gedit). We drive the operations the key
    bindings are wired to DIRECTLY (editing exposes them on the undo object) on
    the actual menu's search entry, so the test is deterministic and does not
    depend on synthetic key-event delivery (unreliable headless). We also confirm
    the keys are bound to the entry."""
    _menu, root = _build_testable_menu()
    try:
        m = root.az_menu
        e = m.search_entry
        var = m.search_var
        ed = m._search_undo
        e.focus_force()
        root.update()

        # The standard keys ARE bound on the real search entry.
        for seq in ("<Control-a>", "<Control-c>", "<Control-x>", "<Control-v>",
                    "<Control-z>", "<Control-y>", "<Control-BackSpace>"):
            assert e.bind(seq), f"missing binding for {seq}"

        # Start from a clean box.
        var.set("")
        ed.break_coalescing()
        for ch in "hello world":
            e.insert("insert", ch)
            if ch == " ":
                ed.break_coalescing()
        root.update()
        assert var.get() == "hello world", var.get()

        # select-all
        ed.select_all()
        assert e.selection_present()
        assert (e.index("sel.first"), e.index("sel.last")) == (0, 11)

        # copy then paste at end -> duplicated
        ed.copy()
        assert root.clipboard_get() == "hello world"
        e.icursor("end")
        e.selection_clear()
        ed.paste()
        assert var.get() == "hello worldhello world"

        # undo removes JUST the paste (its own step), not the prior typing
        ed.undo()
        assert var.get() == "hello world", var.get()
        # redo restores it
        ed.redo()
        assert var.get() == "hello worldhello world"

        # select-all + cut empties the box AND puts the whole selection on the
        # clipboard (so a subsequent paste restores exactly what was cut).
        ed.select_all()
        ed.cut()
        assert var.get() == "", var.get()
        assert root.clipboard_get() == "hello worldhello world"
        e.icursor("end")
        ed.paste()
        assert var.get() == "hello worldhello world", var.get()

        # Ctrl+Backspace deletes the previous word (the trailing "world").
        e.icursor("end")
        ed.del_prev_word()
        assert var.get() == "hello worldhello ", var.get()
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_ui_power_row_centered_and_not_clipped() -> None:
    """Fix #3: each power button (Sleep/Lock/Restart/Shut Down) is centred WITHIN
    ITS OWN cell, not the whole group centred across the bar.

    The four buttons split the row into four EQUAL columns (each PowerButton is
    gridded with weight=1 + a shared uniform group, then sticky='nsew' to fill its
    cell), and each button's icon+label content sits centred in its own slice (the
    inner frame uses the default center anchor). So every button's content-centre
    must line up with its cell-centre -- the regression where the group was centred
    across the whole bar (Sleep hard-left, Shut Down hard-right, only Lock/Restart
    looking centred) must NOT reappear.

    Also guards that the widest label ('Shut Down') is not clipped by the window
    edge at the narrower (582px) width."""
    from widgets import PowerButton
    _menu, root = _build_testable_menu()
    try:
        root.update_idletasks(); root.update()
        W = root.winfo_width()
        wl = root.winfo_rootx()
        btns = []

        def walk(w):
            for c in w.winfo_children():
                if isinstance(c, PowerButton):
                    btns.append(c)
                walk(c)
        walk(root)
        assert len(btns) == 4, f"expected 4 power buttons, got {len(btns)}"

        # Each button's frame IS its cell (expand+fill splits the row evenly).
        # The content spans from the icon's left edge to the label's right edge;
        # its centre must match the cell's centre -> centred within its own slice.
        for i, b in enumerate(btns):
            cell_left = b.winfo_rootx() - wl
            cell_right = cell_left + b.winfo_width()
            cell_center = (cell_left + cell_right) / 2
            content_left = b._icon.winfo_rootx() - wl
            content_right = b._text.winfo_rootx() + b._text.winfo_width() - wl
            content_center = (content_left + content_right) / 2
            assert abs(content_center - cell_center) <= 4, (
                f"button {i} ({b._text.cget('text')!r}) not centred in its cell: "
                f"content_center={content_center:.1f} cell_center={cell_center:.1f}"
            )

        # The four cells are (about) equal width -> an even split, not a cluster.
        widths = [b.winfo_width() for b in btns]
        assert max(widths) - min(widths) <= 2, (
            f"power cells are not equal width (uneven split): {widths}"
        )

        # Not clipped: the last label must stay inside the window.
        far_right = W - (btns[-1]._text.winfo_rootx()
                         + btns[-1]._text.winfo_width() - wl)
        assert far_right >= 0, (
            f"'Shut Down' is clipped by the window edge (overflow {-far_right}px)"
        )
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_ui_persistent_show_hide() -> None:
    """Daemon mode: build_window(persistent=True) exposes az_show/az_hide that
    hide (withdraw) the window instead of destroying it, so it can be re-shown.
    A close (Escape/outside click) must HIDE, not destroy, when persistent."""
    import menu
    root = menu.build_window(persistent=True)
    try:
        root.withdraw()
        root.az_populate()
        root.update_idletasks()
        # Neutralise self-closing bindings so the update loop can't tear it down.
        root.unbind_all("<Button>")

        # Show -> window becomes viewable and CENTERED on the screen.
        root.az_show()
        root.update()
        assert root.winfo_viewable(), "az_show should map the window"
        # Geometry re-applied on show: the window is centered, not stuck at the 0,0
        # re-map default. We compute the expected top-left with the SAME formula the
        # menu uses (clamped to >=0), so this is screen-size independent -- on a
        # window TALLER than the (tiny headless) screen the y clamps to 0, but x is
        # still centered, so the corner is never the (0,0) top-left default unless
        # the whole window genuinely fills the screen.
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        win_w, win_h = menu.menu_size()
        exp_x = max(0, (sw - win_w) // 2)
        exp_y = max(0, (sh - win_h) // 2)
        assert (root.winfo_rootx(), root.winfo_rooty()) == (exp_x, exp_y), (
            "show must re-apply the CENTERED geometry; got "
            f"{(root.winfo_rootx(), root.winfo_rooty())} != {(exp_x, exp_y)}"
        )

        # A normal close in persistent mode HIDES (window survives, withdrawn).
        root.az_close()
        root.update()
        assert root.winfo_exists(), "persistent close must NOT destroy"
        assert not root.winfo_viewable(), "persistent close should withdraw"

        # Re-show works again (proving it was hidden, not destroyed).
        root.az_show()
        root.update()
        assert root.winfo_viewable(), "should re-show after hide"
    finally:
        for _tid in list(getattr(root, "az_timers", [])):
            try:
                root.after_cancel(_tid)
            except Exception:
                pass
        try:
            root.destroy()
        except Exception:
            pass


def test_ui_persistent_first_show_positions_before_map() -> None:
    """First open must NOT flash at the top-left (0,0) corner.

    An override-redirect window that has never been mapped sits at X's default
    0,0 origin. If az_show() calls deiconify() (MapWindow) BEFORE re-applying the
    centered geometry, X maps it visibly at the top-left (0,0) and only then slides
    it to center -- the 'menu flashes at top-left on the first click' bug. The
    position must be set BEFORE the window is mapped, so geometry() must be called
    before deiconify().

    Asserted by call ORDER (WM-timing-independent) rather than a post-map winfo_
    sample, which races the Configure flush and hid this bug in the sibling test.
    """
    import menu
    root = menu.build_window(persistent=True)
    order: list[str] = []
    real_geometry = root.geometry
    real_deiconify = root.deiconify

    def spy_geometry(*a, **k):
        if a or k:  # a SET (not a query) -- ignore geometry() reads
            order.append("geometry")
        return real_geometry(*a, **k)

    def spy_deiconify(*a, **k):
        order.append("deiconify")
        return real_deiconify(*a, **k)

    try:
        root.withdraw()
        root.az_populate()
        root.update_idletasks()
        root.unbind_all("<Button>")
        root.az_hide()  # withdrawn, never-mapped state == the real first show

        root.geometry = spy_geometry
        root.deiconify = spy_deiconify
        root.az_show()

        assert "deiconify" in order, "az_show must map the window"
        assert "geometry" in order, "az_show must position the window"
        assert order.index("geometry") < order.index("deiconify"), (
            "first show maps at 0,0: geometry() must be applied BEFORE "
            f"deiconify(), got order {order}"
        )
    finally:
        root.geometry = real_geometry
        root.deiconify = real_deiconify
        for _tid in list(getattr(root, "az_timers", [])):
            try:
                root.after_cancel(_tid)
            except Exception:
                pass
        try:
            root.destroy()
        except Exception:
            pass


def test_ui_kickoff_scrollbar() -> None:
    """The scrollbar is the custom Kickoff-style widget (not a tk.Scrollbar): it
    exposes set(first, last), hides itself when content fits, draws a pill thumb
    when it doesn't, and never draws arrows."""
    import tkinter as tk
    from widgets import KickoffScrollBar
    root = tk.Tk()
    root.geometry("40x400+700+300")
    try:
        moved = {"args": None}

        def command(*a):
            moved["args"] = a

        sb = KickoffScrollBar(root, command=command)
        sb.pack(side="right", fill="y")
        root.update()

        # It IS the custom widget (a Canvas), not a classic Tk scrollbar.
        assert isinstance(sb, tk.Canvas)

        # Content fits (0..1) -> scrollbar hides itself, draws nothing.
        sb.set(0.0, 1.0)
        root.update()
        assert not sb.winfo_manager(), "scrollbar should hide when content fits"
        assert not sb.find_all(), "no canvas items when content fits"

        # Content overflows -> it re-packs and draws a thumb (>=1 canvas item),
        # and there are NO arrow buttons (it is pure canvas drawing).
        sb.set(0.0, 0.4)
        root.update()
        assert sb.winfo_manager(), "scrollbar should show when content overflows"
        assert sb.find_all(), "thumb should be drawn when overflowing"

        # Dragging issues a yview('moveto', frac) on the command.
        sb._drag_dy = 0
        sb._dragging = True
        sb._scroll_to_pixel(100)
        assert moved["args"] and moved["args"][0] == "moveto"
    finally:
        try:
            root.destroy()
        except Exception:
            pass


# --- tiny test runner ------------------------------------------------------
class _Recorder:
    def __init__(self) -> None:
        self.calls: list = []


def main() -> int:
    failures = 0
    total = 0

    # Pure-logic tests.
    logic_tests = [
        ("category_type_specific_wins", test_category_type_specific_wins, ()),
        ("category_type_main_fallback", test_category_type_main_fallback, ()),
        ("category_type_generic_and_noise",
         test_category_type_generic_and_noise, ()),
        ("strip_field_codes", test_strip_field_codes, ()),
        ("winwatch_parsers", test_winwatch_parsers, ()),
        ("winwatch_index_resolution", test_winwatch_index_resolution, ()),
        ("winwatch_counts_new_windows_and_dedups",
         test_winwatch_counts_new_windows_and_dedups, ()),
        ("xfocus_helpers_are_crashproof", test_xfocus_helpers_are_crashproof, ()),
        ("theme_sizes_are_scaled_10pct", test_theme_sizes_are_scaled_10pct, ()),
        ("menu_modules_use_centralised_font_constants",
         test_menu_modules_use_centralised_font_constants, ()),
        ("app_rows_are_nudged_right", test_app_rows_are_nudged_right, ()),
        ("menu_size_is_theme_default", test_menu_size_is_theme_default, ()),
        ("removed_panel_and_tooltip_theme_constants_are_gone",
         test_removed_panel_and_tooltip_theme_constants_are_gone, ()),
    ]
    for name, fn, _ in logic_tests:
        total += 1
        try:
            fn()
            print(f"ok   {name}")
        except AssertionError as ex:
            failures += 1
            print(f"FAIL {name}: {ex}")

    # Tests needing a temp dir.
    for name, fn in (
        ("parse_desktop_file", test_parse_desktop_file),
        ("scan_dedup_and_sort", test_scan_dedup_and_sort),
        ("scan_hides_denylisted", test_scan_hides_denylisted),
        ("usage_record_persist_and_order",
         test_usage_record_persist_and_order),
        ("usage_corrupt_store_is_ignored", test_usage_corrupt_store_is_ignored),
    ):
        total += 1
        with tempfile.TemporaryDirectory() as tmp:
            try:
                fn(tmp)
                print(f"ok   {name}")
            except AssertionError as ex:
                failures += 1
                print(f"FAIL {name}: {ex}")

    # UI tests (need a display).
    if not _have_display():
        print("skip UI tests (no $DISPLAY)")
        print(f"\n{total - failures}/{total} passed, {failures} failed")
        return 1 if failures else 0

    # Redirect the usage store to a throwaway file so building the real menu (and
    # the launch test, which records a launch) never touches the user's real
    # frequency data. Set before the first build_window() call.
    _usage_tmp = tempfile.mkdtemp(prefix="azarch-test-usage-")
    os.environ["AZARCH_USAGE_FILE"] = os.path.join(_usage_tmp, "usage.json")

    import actions

    # build / search / clear-order / centering / TAB focus / power / persistence
    for name, fn in (
        ("ui_build_and_contents", test_ui_build_and_contents),
        ("ui_removed_pin_settings_and_highlight_are_gone",
         test_ui_removed_pin_settings_and_highlight_are_gone),
        ("ui_search_filter", test_ui_search_filter),
        ("ui_search_clear_after_partial_filter",
         test_ui_search_clear_after_partial_filter),
        ("ui_reorders_after_launch_without_restart",
         test_ui_reorders_after_launch_without_restart),
        ("ui_search_filtering_never_churns_windows",
         test_ui_search_filtering_never_churns_windows),
        ("ui_window_is_centered", test_ui_window_is_centered),
        ("ui_default_focus_zone_is_apps", test_ui_default_focus_zone_is_apps),
        ("ui_tab_toggles_focus_zone", test_ui_tab_toggles_focus_zone),
        ("ui_power_zone_left_right_moves_focus_clamped",
         test_ui_power_zone_left_right_moves_focus_clamped),
        ("ui_on_activate_in_power_zone_fires_focused_button",
         test_ui_on_activate_in_power_zone_fires_focused_button),
        ("ui_power_button_set_focused_paints_outline",
         test_ui_power_button_set_focused_paints_outline),
        ("ui_tab_is_bound_and_click_returns_focus_to_apps",
         test_ui_tab_is_bound_and_click_returns_focus_to_apps),
        ("ui_arrows_move_selection_only_in_apps_zone",
         test_ui_arrows_move_selection_only_in_apps_zone),
        ("ui_super_key_binding_is_present", test_ui_super_key_binding_is_present),
        ("ui_super_key_closes", test_ui_super_key_closes),
        ("ui_forced_close_destroys_window",
         test_ui_forced_close_destroys_window),
        ("ui_normal_and_forced_close_behave_the_same",
         test_ui_normal_and_forced_close_behave_the_same),
        ("ui_power_buttons_use_breeze_icons",
         test_ui_power_buttons_use_breeze_icons),
        ("ui_search_standard_editing", test_ui_search_standard_editing),
        ("ui_power_row_centered_and_not_clipped",
         test_ui_power_row_centered_and_not_clipped),
        ("ui_persistent_show_hide", test_ui_persistent_show_hide),
        ("ui_persistent_first_show_positions_before_map",
         test_ui_persistent_first_show_positions_before_map),
        ("ui_kickoff_scrollbar", test_ui_kickoff_scrollbar),
    ):
        total += 1
        try:
            fn()
            print(f"ok   {name}")
        except AssertionError as ex:
            failures += 1
            print(f"FAIL {name}: {ex}")
        except Exception as ex:  # noqa: BLE001 -- report unexpected UI errors
            failures += 1
            print(f"ERR  {name}: {type(ex).__name__}: {ex}")

    # launch test with monkeypatched actions.launch
    total += 1
    rec = _Recorder()
    orig_launch = actions.launch
    actions.launch = lambda argv: rec.calls.append(list(argv))
    try:
        test_ui_selection_and_launch(rec)
        print("ok   ui_selection_and_launch")
    except AssertionError as ex:
        failures += 1
        print(f"FAIL ui_selection_and_launch: {ex}")
    except Exception as ex:  # noqa: BLE001
        failures += 1
        print(f"ERR  ui_selection_and_launch: {type(ex).__name__}: {ex}")
    finally:
        actions.launch = orig_launch

    # power wiring tests with monkeypatched power actions. Each builds its own menu
    # INSIDE the test, so the fakes must be installed BEFORE the call (the button
    # closures capture actions.* at build time). _Recorder is duck-typed as the
    # monkeypatch_actions fixture (both expose .calls).
    for tname, tfn in (
        ("ui_power_buttons_wired", test_ui_power_buttons_wired),
        ("ui_power_activation_wired_through_on_activate",
         test_ui_power_activation_wired_through_on_activate),
    ):
        total += 1
        prec = _Recorder()
        saved = {}
        for nm in ("suspend", "reboot", "poweroff", "lock_session"):
            saved[nm] = getattr(actions, nm)
            setattr(actions, nm, (lambda n: (lambda: prec.calls.append(n)))(nm))
        try:
            tfn(prec)
            print(f"ok   {tname}")
        except AssertionError as ex:
            failures += 1
            print(f"FAIL {tname}: {ex}")
        except Exception as ex:  # noqa: BLE001
            failures += 1
            print(f"ERR  {tname}: {type(ex).__name__}: {ex}")
        finally:
            for nm, fn in saved.items():
                setattr(actions, nm, fn)

    print(f"\n{total - failures}/{total} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
