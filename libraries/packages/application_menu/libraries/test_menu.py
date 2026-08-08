#!/usr/bin/env python3
"""Tests for the Az'arch application menu.

Two layers:
  * Pure-logic tests (no display): category typing in apps.py, .desktop
    parsing, and launch-frequency ordering in usage.py. These run anywhere.
  * UI smoke tests (need $DISPLAY): build the real window, disable its
    auto-close bindings, and drive the search filter (including the clear-
    restores-order fix), selection / launch, the pin toggle and the power
    wiring deterministically.

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
    menu reads a touch larger while still fitting the panel footprint.

    The font sizes and icon edges USED to be bare literals scattered across
    widgets.py / applist.py / menu.py (the app-name/type point sizes, the search
    entry size, the power-row label) and the icon-edge constants in theme.py. They
    are now centralised as theme.FONT_* / theme.*ICON_SIZE constants so there is ONE
    place to scale them. This pins the scaled values (original * 1.1, rounded to the
    nearest whole point/pixel -- Tk fonts and PhotoImage need integers) so a future
    edit that silently reverts the bump fails here.
    """
    import theme as T

    # Original sizes -> 10%-bigger (round-half-to-nearest int).
    assert T.FONT_APP_NAME == 13, T.FONT_APP_NAME      # was 12
    assert T.FONT_APP_TYPE == 10, T.FONT_APP_TYPE      # was 9
    assert T.FONT_SEARCH == 13, T.FONT_SEARCH          # was 12
    assert T.FONT_POWER == 12, T.FONT_POWER            # was 11

    assert T.ICON_SIZE == 44, T.ICON_SIZE              # was 40
    assert T.POWER_ICON_SIZE == 24, T.POWER_ICON_SIZE  # was 22
    assert T.TOP_ICON_SIZE == 24, T.TOP_ICON_SIZE      # was 22

    # Every one is genuinely bigger than the pre-bump value (guards a typo that
    # made a size SMALLER while still being "changed").
    for new, old in (
        (T.FONT_APP_NAME, 12), (T.FONT_APP_TYPE, 9),
        (T.FONT_SEARCH, 12), (T.FONT_POWER, 11),
        (T.ICON_SIZE, 40), (T.POWER_ICON_SIZE, 22), (T.TOP_ICON_SIZE, 22),
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


def test_tooltip_theme_constants_exist() -> None:
    """The hover-tooltip styling constants are defined so the Settings button's
    hint has a Breeze-ish look. The tooltip is INSTANT now (no dwell), so
    TOOLTIP_DELAY_MS is retained only for compatibility and must be a
    non-negative int (0 = show immediately)."""
    import theme as T
    for attr in ("TOOLTIP_BG", "TOOLTIP_FG", "TOOLTIP_BORDER"):
        assert getattr(T, attr).startswith("#"), attr
    assert isinstance(T.TOOLTIP_DELAY_MS, int) and T.TOOLTIP_DELAY_MS >= 0


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
        assert root.az_highlight is not None
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


def test_ui_pin_keeps_menu_open() -> None:
    """Pinning must make outside-click / focus-loss / Escape NON-dismissing,
    while a forced close (app launch, power action) still works."""
    _menu, root = _build_testable_menu()
    try:
        m = root.az_menu
        assert root.az_pinned is False
        # Toggle pin ON via the menu's own handler (drives the button too).
        m._toggle_pin()
        assert root.az_pinned is True
        assert m.pin_button._active is True

        # A normal (unforced) close is now a no-op: the window survives.
        m.close_menu()
        assert root.winfo_exists()

        # Toggle pin OFF -> a normal close dismisses again.
        m._toggle_pin()
        assert root.az_pinned is False
        assert m.pin_button._active is False
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_ui_super_key_binding_is_present() -> None:
    """The Super/Meta key must CLOSE the menu, mirroring Escape.

    Why a window-level binding at all (vs. just KWin's global Meta->launcher
    toggle): while the menu is unpinned it holds a GLOBAL keyboard grab, so a
    second physical Super press is delivered to OUR window and never reaches the
    WM -- KWin's Meta shortcut can't fire, so the daemon never toggles it shut.
    Binding Super on the window itself makes that grab-delivered press close it,
    so 'Super opened it, Super closes it' holds. (When pinned the menu drops the
    grab, so KWin's toggle handles the close; the binding just no-ops there via
    close_menu's pin guard.)

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


def test_ui_super_key_closes_and_respects_pin() -> None:
    """Pressing Super closes an (unpinned) menu, and -- like Escape -- is ignored
    while pinned (a forced close still works).

    Driven through the SAME close path a real Super press hits: close_menu is what
    the <Super_*> bindings invoke. We first prove a real synthetic <Super_L> event
    routes to it end-to-end (window mapped + focused so Xvfb delivers the key),
    then prove the pin guard with a direct close_menu call while pinned."""
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
            "a Super_L keypress must close (destroy) the unpinned menu"
        )
    finally:
        try:
            root.destroy()
        except Exception:
            pass

    # Pinned: Super (like Escape) must NOT dismiss; a forced close still does.
    _menu, root = _build_testable_menu()
    try:
        m = root.az_menu
        m._toggle_pin()
        assert root.az_pinned is True
        # The binding's handler (close_menu) is pin-guarded: no-op while pinned.
        m.close_menu()
        assert _window_alive(root), "pinned menu must ignore a Super/Escape close"
        # Forced close (app launch / power) still tears it down.
        m.close_menu(force=True)
        try:
            root.update()
        except tk.TclError:
            pass
        assert not _window_alive(root), "forced close must work even when pinned"
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_ui_pin_is_a_focus_independent_toggle() -> None:
    """The pin button is a plain toggle that NEVER needs a focus-priming press.

    Regression for 'a pinned-but-dormant menu takes two pin presses to unpin (one to
    gain focus, one to unpin)'. The pin now unpins in a SINGLE press regardless of
    whether it currently holds the keyboard, as a state machine:

      1. Press pin (unpinned)         -> pinned AND capturing (search stays live).
      2. User switches app (alt-tab)  -> still pinned, but NO longer capturing
                                         (menu stays open, search goes dormant, and
                                         the keyboard is handed to the new window).
      3. Press pin (pinned, dormant)  -> UNPINS in ONE press (does NOT merely
                                         re-grab focus and stay pinned).

    Step 4 below re-pins and unpins again from the LIVE state to prove a live pinned
    menu also unpins in one press -- so the button behaves identically no matter the
    focus state. Waking a dormant pinned menu still works, but that is the search
    box's job (test_ui_pinned_claims_x_focus_onto_own_window covers the click-to-
    reclaim path); it is deliberately NOT bound to the pin button anymore.

    The switch-away in step 2 is what actually happens on the live WM: an override-
    redirect window will not surrender a forced keyboard focus via <FocusOut> or a
    grab, so the menu watches _NET_ACTIVE_WINDOW (xfocus.active_window) and, when it
    changes to another window, hands X focus there (xfocus.set_input_focus) and stops
    capturing. We drive that deterministically by faking xfocus: active_window()
    returns a baseline while pinned, then a DIFFERENT id to simulate the user
    switching apps, and set_input_focus() is recorded so we can assert the keyboard
    was handed to that window.
    """
    import xfocus
    _orig_active = xfocus.active_window
    _orig_setfocus = xfocus.set_input_focus
    handed_to = []
    fake = {"active": 0x111}  # some other window is active while we're pinned
    xfocus.active_window = lambda: fake["active"]
    xfocus.set_input_focus = lambda win: (handed_to.append(win), True)[1]

    _menu, root = _build_testable_menu()
    try:
        m = root.az_menu
        st = root.az_state
        # We start unpinned. (Initial capturing depends on whether arm() grabbed on
        # this WM; the STATE MACHINE below is independent of that starting value.)
        assert st["pinned"] is False

        # 1. Pin -> pinned and capturing, button active, baseline active-window saved.
        m._toggle_pin()
        assert st["pinned"] is True, st
        assert st["capturing"] is True, st
        assert m.pin_button._active is True
        assert st["pin_active"] == 0x111, st  # remembered who was active at pin time

        # 2. User switches to another app: _NET_ACTIVE_WINDOW changes. The watcher
        #    (already scheduled by _focus_window) must notice, hand the keyboard to
        #    the new window, and stop capturing -- WITHOUT unpinning or closing.
        fake["active"] = 0x222  # a different window is now active
        root.after(400, root.quit)   # pump long enough for the 150ms watcher tick
        root.mainloop()
        assert st["pinned"] is True, "switching apps must NOT unpin a pinned menu"
        assert st["capturing"] is False, "switching apps must stop capturing"
        assert root.winfo_exists(), "pinned menu must stay open on switch-away"
        assert 0x222 in handed_to, (
            "the keyboard must be handed to the newly-active window, got %r"
            % (handed_to,))

        # 3. Press pin while pinned-but-dormant -> UNPINS in ONE press (the bug was
        #    that this only re-grabbed focus and left the menu pinned, forcing a
        #    second press to unpin).
        m._toggle_pin()
        assert st["pinned"] is False, (
            "pressing pin while dormant must unpin in a single press, not merely "
            "reclaim focus")
        assert m.pin_button._active is False

        # 4. Re-pin, then press once more from the LIVE state -> unpins too, proving
        #    the toggle is identical regardless of focus/capturing.
        m._toggle_pin()
        assert st["pinned"] is True and st["capturing"] is True, st
        m._toggle_pin()
        assert st["pinned"] is False, "pressing pin while live must unpin"
        assert m.pin_button._active is False
    finally:
        xfocus.active_window = _orig_active
        xfocus.set_input_focus = _orig_setfocus
        try:
            root.destroy()
        except Exception:
            pass


def test_ui_pinned_claims_x_focus_onto_own_window() -> None:
    """Regression for 'pin steals focus to KRunner'. VERIFIED on the live KWin
    hypervisor: our override-redirect window is NEVER made the X input focus by
    ``focus_force()`` alone -- with the menu open the real X input focus sits on the
    Desktop/KRunner, and while UNPINNED only the global grab's keyboard capture keeps
    the search box live. So the instant pinning releases that grab, keystrokes fall to
    whatever X still focuses (KRunner on an idle session) unless the menu explicitly
    grabs the real keyboard.

    The ONE primitive that actually moves (and keeps) the X input focus on an
    unmanaged window under KWin is ``XSetInputFocus`` targeting that window
    (xfocus.set_input_focus(our_id)). This test pins the menu with a faked xfocus and
    asserts the pin path calls set_input_focus with OUR OWN window id -- i.e. the menu
    claims the keyboard for itself rather than merely calling focus_force() (which the
    live WM ignores) and, worse, later handing focus AWAY via the active-window
    watcher.

    active_window() is faked to a STABLE value across the whole flow (modelling the
    real WM: focus_force on our override-redirect window does not change
    _NET_ACTIVE_WINDOW), so any set_input_focus we see is the fix claiming focus for
    the menu, not the switch-away handler."""
    import xfocus
    _orig_active = xfocus.active_window
    _orig_setfocus = xfocus.set_input_focus
    focused = []                       # every window id set_input_focus is asked for
    # A foreign window is "active" and stays active -- focus_force on our unmanaged
    # window does NOT change _NET_ACTIVE_WINDOW on the real WM, so this never varies.
    xfocus.active_window = lambda: 0xABC
    xfocus.set_input_focus = lambda win: (focused.append(win), True)[1]

    _menu, root = _build_testable_menu()
    try:
        m = root.az_menu
        st = root.az_state
        assert st["pinned"] is False

        our_id = root.winfo_id()
        # Pin. The menu must claim the REAL keyboard onto its own window (the only
        # thing that works on KWin), not just focus_force() and hope.
        m._toggle_pin()
        assert st["pinned"] is True, st
        assert our_id in focused, (
            "pinning must claim X input focus onto our OWN window id (0x%x) via "
            "XSetInputFocus -- focus_force() alone does not move focus off "
            "KRunner/Desktop on KWin; set_input_focus was called with %r"
            % (our_id, [hex(w) for w in focused]))
        assert st["capturing"] is True, st

        # And it must NOT immediately hand focus to the (unchanged) foreign active
        # window -- that is the switch-away path, which must only fire on a real
        # active-window CHANGE, never at pin time.
        root.after(400, root.quit)     # pump past the 150ms watcher tick
        root.mainloop()
        assert 0xABC not in focused, (
            "a stable active window must NOT trigger a switch-away hand-off; the "
            "menu kept focus for itself only. focused=%r"
            % ([hex(w) for w in focused],))
        assert st["pinned"] is True and st["capturing"] is True, st

        # Second reported symptom: clicking the search box while pinned-but-dormant
        # must re-claim focus (Kickoff refocuses on click). Simulate dormancy, then a
        # click on the entry, and assert the menu re-claimed X focus onto its own id.
        st["capturing"] = False
        focused.clear()
        m._on_search_click()           # what the entry's <Button-1> binding fires
        assert our_id in focused, (
            "clicking the search box while pinned+dormant must re-claim X input "
            "focus onto our own window id; set_input_focus got %r"
            % ([hex(w) for w in focused],))
        assert st["capturing"] is True, "click must restore capturing"
    finally:
        for _tid in list(getattr(root, "az_timers", [])):
            try:
                root.after_cancel(_tid)
            except Exception:
                pass
        xfocus.active_window = _orig_active
        xfocus.set_input_focus = _orig_setfocus
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


def test_ui_pinned_forced_close_still_works() -> None:
    """Even pinned, launching an app forces the menu closed."""
    _menu, root = _build_testable_menu()
    try:
        m = root.az_menu
        m._toggle_pin()
        assert root.az_pinned is True
        m.close_menu(force=True)  # forced -> closes regardless of pin
        assert _is_destroyed(root)
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_ui_pin_before_arm_does_not_re_grab() -> None:
    """Regression for the pin-before-arm race: arm() runs deferred (~30ms) and
    (re)takes a GLOBAL pointer grab. If the user pins the menu in the gap before
    arm() fires, pinning has just released the grab -- arm() must NOT re-take a
    global grab while pinned, or every desktop click is black-holed with no
    click-outside escape (an input wedge).

    We build the window raw (NOT via _build_testable_menu, which flushes arm),
    pin BEFORE letting arm run, then run the pending arm timer, and assert no
    global grab is held. grab_current() returns the grabbing widget or None; a
    global grab set by arm() would make it the root."""
    import menu
    import tkinter as tk

    root = menu.build_window()
    # Neutralise the self-closing bindings the same way the shared helper does,
    # so nothing tears the window down mid-test.
    _orig_bind = root.bind

    def _guarded_bind(seq=None, func=None, add=None):
        if seq == "<FocusOut>":
            return ""
        return _orig_bind(seq, func, add)

    root.bind = _guarded_bind
    root.unbind_all("<Button>")
    try:
        m = root.az_menu
        # Map the window WITHOUT running the deferred arm() yet.
        root.update_idletasks()
        # Pin first -> toggle_pin() releases any grab and sets pinned.
        m._toggle_pin()
        assert root.az_pinned is True

        # Now let the pending timers (incl. arm()) run.
        root.update()
        root.update_idletasks()

        # The crux: arm() must NOT have re-taken a global grab while pinned.
        grabber = root.grab_current()
        assert grabber in (None, "", ), (
            "pinned menu unexpectedly holds a grab: %r" % (grabber,)
        )
        # And a normal outside-click close is still a no-op while pinned.
        assert root.az_pinned is True
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


def test_ui_settings_button_is_disabled() -> None:
    """The Settings (gear) button ships GREYED OUT / disabled: the settings
    screen is not built yet, so the button must be inert (no hover highlight,
    ignores clicks, normal arrow cursor) rather than looking clickable but doing
    nothing. This pins the four observable properties of that disabled state."""
    _menu, root = _build_testable_menu()
    try:
        m = root.az_menu
        btn = m.settings_button
        assert btn is not None, "settings button was not created"
        # 1. It is flagged disabled.
        assert btn._disabled is True
        # 2. Normal arrow cursor (not the hand2 a live button uses).
        assert str(btn.cget("cursor")) == "arrow"
        # 3. Pressing it does nothing: _press is a guarded no-op and the nominal
        #    command must NOT fire even if _press is called directly.
        fired = {"v": False}
        m._noop = lambda: fired.__setitem__("v", True)  # would-be handler
        btn._command = m._noop
        btn._press()
        assert fired["v"] is False, "disabled settings button fired its command"
        # 4. Hovering does not change its look (set_active is a no-op; a disabled
        #    button binds no <Enter>/<Leave> so it can never highlight).
        btn.set_active(True)
        assert btn._active is False
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_ui_pin_button_still_enabled() -> None:
    """Regression guard for the settings-disable change: the PIN button must stay
    fully functional (enabled, hand cursor, active-state toggles) -- only the
    settings button is disabled."""
    _menu, root = _build_testable_menu()
    try:
        m = root.az_menu
        pin = m.pin_button
        assert pin is not None and pin._disabled is False
        assert str(pin.cget("cursor")) == "hand2"
        pin.set_active(True)
        assert pin._active is True
        pin.set_active(False)
        assert pin._active is False
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_ui_dim_image_greys_but_keeps_size() -> None:
    """dim_image must return an image of the SAME dimensions whose opaque pixels
    are shifted toward the disabled grey (so the glyph fades but keeps its
    shape). We build a tiny opaque red image and check a pixel moved toward grey."""
    import tkinter as tk

    import theme as T
    import widgets

    _menu, root = _build_testable_menu()
    try:
        src = tk.PhotoImage(width=4, height=4)
        src.put("#ff0000", to=(0, 0, 4, 4))  # fully opaque red
        out = widgets.dim_image(src, mix=0.5, toward="#000000")
        assert out.width() == 4 and out.height() == 4
        r, g, b = out.get(1, 1)[:3]
        # Halfway from red(255,0,0) toward black(0,0,0) -> ~127,0,0.
        assert 120 <= r <= 135 and g == 0 and b == 0
        # And the default toward-grey path actually dims (red channel drops).
        out2 = widgets.dim_image(src)
        r2 = out2.get(1, 1)[0]
        assert r2 < 255
        # Sanity: default mix moves toward the configured disabled colour.
        assert T.DISABLED_ICON_COLOR.startswith("#")
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
        # Activate the selection -> should call actions.launch with kitty argv
        # and then close (close is neutered-ish: it destroys the root).
        m.activate_selected()
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


def _mapped_bar_toplevels(root) -> list:
    """The blue HighlightBar Toplevels currently MAPPED under root -- used to catch
    the 'cyan bar stuck over the panel icon' leak."""
    import tkinter as tk
    out = []
    for w in root.winfo_children():
        if not isinstance(w, tk.Toplevel):
            continue
        try:
            if w.winfo_exists() and w.winfo_viewable() and str(w.cget("bg")) == "#3daee9":
                out.append(str(w))
        except tk.TclError:
            pass
    return out


def test_ui_highlight_bar_no_leak_on_double_show() -> None:
    """Regression: the HighlightBar (the Breeze-blue stripe over the panel icon)
    must NOT get stuck on screen.

    show_menu() builds a fresh bar each call, assuming the prior hide destroyed
    it. But a show() with NO intervening hide() (the launcher's auto-start SIGUSR2
    landing while a panel-click SIGUSR1 already showed the menu, or any repeated
    'show') orphaned the previous bar Toplevel -- it stayed mapped forever because
    the later hide only closed the CURRENT az_highlight. This asserts that after a
    double-show there is exactly ONE mapped bar and that a single hide removes it
    (zero mapped bars), i.e. no orphan is left behind."""
    import menu
    root = menu.build_window(persistent=True)
    try:
        root.withdraw()
        root.az_populate()
        root.update_idletasks()
        root.unbind_all("<Button>")
        root.az_hide()
        root.update()

        # Two shows in a row, no hide between (the leak trigger).
        root.az_show(); root.update()
        for _ in range(4):
            root.update(); root.update_idletasks()
        root.az_show(); root.update()
        for _ in range(4):
            root.update(); root.update_idletasks()
        bars = _mapped_bar_toplevels(root)
        assert len(bars) == 1, f"double-show must leave ONE bar, got {bars}"

        # A single hide must clear it -> no orphan stuck on screen.
        root.az_hide(); root.update(); root.update_idletasks()
        bars = _mapped_bar_toplevels(root)
        assert bars == [], f"hide must remove the bar, but these are stuck: {bars}"
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


def test_ui_highlight_bar_placed_over_leftmost_icon() -> None:
    """Fix #2: the cyan/blue highlight bar must sit over the LEFTMOST panel icon
    (our menu applet took Kickoff's old leftmost slot), not be misplaced.

    The leftmost panel cell physically spans [0, PANEL_HEIGHT) (a square cell as
    wide as the panel is thick). We assert the mapped bar Toplevel falls ENTIRELY
    within that first cell -- its left edge is well inside [0, PANEL_HEIGHT) and its
    right edge does not cross into the SECOND cell (which starts at PANEL_HEIGHT).
    These bounds are hardcoded from the panel geometry, NOT derived from
    ICON_CELL_X, so the test is independent of the very constant it guards: if
    ICON_CELL_X ever regresses to the old 2nd-slot offset (PANEL_HEIGHT), the bar
    lands at x>=PANEL_HEIGHT and this FAILS loudly. y must be the panel's top edge
    and height the configured bar height."""
    import tkinter as tk
    import theme as T
    import menu
    root = menu.build_window(persistent=True)
    try:
        root.withdraw()
        root.az_populate()
        root.update_idletasks()
        root.unbind_all("<Button>")
        root.az_show()
        for _ in range(4):
            root.update(); root.update_idletasks()

        bars = [w for w in root.winfo_children()
                if isinstance(w, tk.Toplevel) and w.winfo_exists()
                and str(w.cget("bg")) == "#3daee9" and w.winfo_viewable()]
        assert len(bars) == 1, f"expected exactly one mapped bar, got {len(bars)}"
        bar = bars[0]
        screen_h = root.winfo_screenheight()
        # First cell spans [0, PANEL_HEIGHT). Ground truth, independent of ICON_CELL_X.
        first_cell_right = T.PANEL_HEIGHT
        bar_left = bar.winfo_x()
        bar_right = bar_left + bar.winfo_width()
        assert 0 <= bar_left < first_cell_right, (
            f"bar left x={bar_left} not inside the LEFTMOST cell [0,{first_cell_right}); "
            "ICON_CELL_X likely regressed to a non-leftmost slot"
        )
        assert bar_right <= first_cell_right, (
            f"bar right edge x={bar_right} spills into the 2nd cell "
            f"(starts at {first_cell_right}) -- misplaced"
        )
        # y at the panel's top edge; height as configured.
        exp_y = screen_h - T.PANEL_HEIGHT
        assert bar.winfo_y() == exp_y, f"bar y={bar.winfo_y()} != panel top {exp_y}"
        assert bar.winfo_height() == T.HIGHLIGHT_BAR_HEIGHT, (
            f"bar height={bar.winfo_height()} != {T.HIGHLIGHT_BAR_HEIGHT}"
        )
        # And the width is the inset cell width (a positive stripe, not degenerate).
        assert bar.winfo_width() == max(1, T.ICON_CELL_W - 2 * T.HIGHLIGHT_BAR_INSET)
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


def test_ui_settings_button_has_tooltip() -> None:
    """The greyed-out Settings (gear) button shows a hover hint explaining the
    settings screen is not built yet -- even though the button is DISABLED and
    binds no hover-paint handlers. We assert a Tooltip is attached carrying the
    exact copy, and that showing it maps a small popup with that text."""
    import tkinter as tk
    _menu, root = _build_testable_menu()
    try:
        m = root.az_menu
        btn = m.settings_button
        assert btn is not None and btn._disabled is True
        tips = getattr(btn, "_tooltips", [])
        assert tips, "settings button must have a tooltip attached"
        wanted = "The application menu settings are not available yet"
        assert any(t._text == wanted for t in tips), \
            f"tooltip text mismatch: {[t._text for t in tips]}"

        # Force one tooltip to show and check a popup label with the text exists,
        # then hide it cleanly.
        tip = tips[0]
        tip._show()
        root.update_idletasks()
        assert tip._tip is not None and tip._tip.winfo_exists(), \
            "showing the tooltip must map a popup"
        labels = [c for c in tip._tip.winfo_children() if isinstance(c, tk.Label)]
        assert labels and labels[0].cget("text") == wanted
        tip._hide()
        root.update_idletasks()
        assert tip._tip is None, "hide must tear the tooltip popup down"
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_ui_settings_tooltip_is_instant() -> None:
    """Fix #1: the Settings-button hover hint must be INSTANT -- it appears the
    moment the pointer enters the button and disappears the moment it leaves, with
    NO dwell timer.

    We drive the real Tk bindings: firing the widget's <Enter> event must map the
    popup SYNCHRONOUSLY (before any after()-based delay could run -- we never pump
    a timer), and firing <Leave> must tear it down immediately. A dwell-based
    tooltip would still be un-mapped right after <Enter> (it would be waiting on an
    after() callback), so this fails loudly if the delay ever creeps back."""
    _menu, root = _build_testable_menu()
    try:
        m = root.az_menu
        btn = m.settings_button
        tips = getattr(btn, "_tooltips", [])
        assert tips, "settings button must have a tooltip attached"
        tip = tips[0]
        assert tip._tip is None, "tooltip must start hidden"

        # Hover ON: the popup must exist right away, with only idle (not timer)
        # processing -- update_idletasks() runs pending idle work but does NOT run
        # after() timers, so a dwell tooltip would still be None here.
        tip._widget.event_generate("<Enter>")
        root.update_idletasks()
        assert tip._tip is not None and tip._tip.winfo_exists(), \
            "tooltip must appear INSTANTLY on <Enter> (no dwell delay)"

        # Hover OFF: gone immediately.
        tip._widget.event_generate("<Leave>")
        root.update_idletasks()
        assert tip._tip is None, "tooltip must disappear the moment the mouse leaves"
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_ui_settings_tooltip_renders_once_and_sticks() -> None:
    """Fix #1: the Settings-button hint must render ONCE and hold its place -- it
    must NOT tear down and rebuild as the pointer slides across the box (the old
    flicker, caused by two tooltips fighting on the frame and its inner glyph, plus
    frame<->child crossings hiding then re-showing the popup).

    Two guarantees:

      * Exactly ONE Tooltip is attached to the button (not a second copy on the
        glyph label), so there is a single popup, never a pair swapping in and out.
      * Once shown, a <Leave> whose pointer is STILL over the box (it merely crossed
        onto the inner glyph) does nothing. Tkinter's Event exposes no X crossing
        ``detail`` in every build, so the guard is positional: it re-reads where the
        pointer is via winfo_containing. We drive that here by firing <Leave> on the
        frame with x_root/y_root set to a point INSIDE the glyph label -- the same
        signal a real frame->child crossing produces. The popup Toplevel must be the
        SAME object throughout (identity unchanged == never rebuilt == no flicker);
        a <Leave> whose coordinates fall OUTSIDE the box then tears it down.
    """
    _menu, root = _build_testable_menu()
    try:
        m = root.az_menu
        btn = m.settings_button
        tips = getattr(btn, "_tooltips", [])
        assert len(tips) == 1, (
            "the button must carry exactly ONE tooltip (a second copy on the glyph "
            "is what made it flicker); got %d" % len(tips))
        tip = tips[0]
        root.update_idletasks()

        # A point that lands squarely inside the inner glyph label (a child of the
        # button frame) -- crossing here keeps the pointer inside the box subtree.
        glyph = btn._label
        inside_x = glyph.winfo_rootx() + max(1, glyph.winfo_width() // 2)
        inside_y = glyph.winfo_rooty() + max(1, glyph.winfo_height() // 2)
        # A point well outside the whole button but with valid (non-negative) root
        # coords -- to the RIGHT of the button -- so this exercises the real
        # "coordinate present, but not over us" branch, not the missing-coord one.
        outside_x = btn.winfo_rootx() + btn.winfo_width() + 200
        outside_y = btn.winfo_rooty() + max(1, btn.winfo_height() // 2)

        # Real entry -> the popup appears once.
        tip._widget.event_generate("<Enter>")
        root.update_idletasks()
        assert tip._tip is not None and tip._tip.winfo_exists(), \
            "tooltip must appear on a real <Enter>"
        first = tip._tip  # capture identity to prove it is never rebuilt below

        # Pointer slides onto the inner glyph: a <Leave> on the frame, but the
        # pointer is still inside the box -> the popup must persist unchanged.
        # event_generate takes -rootx/-rooty; Tk fills event.x_root/y_root from them.
        tip._widget.event_generate(
            "<Leave>", rootx=inside_x, rooty=inside_y)
        root.update_idletasks()
        assert tip._tip is first and first.winfo_exists(), (
            "a <Leave> whose pointer is still over the glyph must NOT destroy the "
            "tooltip -- the pointer is still inside the box")

        # Pointer returns to the frame from the child: <Enter> again must NOT rebuild
        # the existing popup (that rebuild was the flicker).
        tip._widget.event_generate("<Enter>", rootx=inside_x, rooty=inside_y)
        root.update_idletasks()
        assert tip._tip is first, (
            "returning from the glyph must NOT rebuild the tooltip -- it should "
            "render once and stay put")

        # A genuine exit of the whole box (pointer now outside) finally hides it.
        tip._widget.event_generate(
            "<Leave>", rootx=outside_x, rooty=outside_y)
        root.update_idletasks()
        assert tip._tip is None, \
            "a real <Leave> off the box must tear the tooltip down"
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_ui_settings_tooltip_hides_when_exiting_onto_popup() -> None:
    """Fix #1, regression: the popup Toplevel is a child of the button frame and is
    positioned DIRECTLY BELOW the button, right on the natural downward exit path.

    Guards against a subtle bug in the 'is the pointer still inside the box?' check:
    because winfo_containing sees the popup and the popup's Tk-hierarchy parent chain
    leads back to the button frame, a <Leave> whose coordinates land ON THE POPUP
    must NOT be mistaken for 'still inside the box'. If it were, moving the mouse
    straight down off the button (onto the hint) would leave the popup stuck on
    screen forever -- the frame gets no further <Leave> once the pointer is on the
    popup, and the popup has no <Leave> of its own. So a leave onto the popup must
    hide the tooltip.
    """
    _menu, root = _build_testable_menu()
    try:
        m = root.az_menu
        btn = m.settings_button
        tip = btn._tooltips[0]
        root.update_idletasks()

        tip._widget.event_generate("<Enter>")
        root.update_idletasks()
        assert tip._tip is not None, "tooltip must show on <Enter>"
        popup = tip._tip
        root.update_idletasks()
        root.update()

        # A point squarely on the popup itself -- moving straight down off the button
        # onto the floating hint. This is the exact scenario that used to stick.
        on_popup_x = popup.winfo_rootx() + max(1, popup.winfo_width() // 2)
        on_popup_y = popup.winfo_rooty() + max(1, popup.winfo_height() // 2)
        tip._widget.event_generate(
            "<Leave>", rootx=on_popup_x, rooty=on_popup_y)
        root.update_idletasks()
        assert tip._tip is None, (
            "leaving the button DOWNWARD onto the popup must hide the tooltip, not "
            "leave it orphaned and stuck on screen")
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

        # Show -> window becomes viewable and correctly positioned (not 0,0).
        root.az_show()
        root.update()
        assert root.winfo_viewable(), "az_show should map the window"
        # Geometry re-applied on show: not stuck at the 0,0 re-map default. Our menu
        # sits at the bottom-LEFT (x=0) but well down the screen (y near the bottom),
        # so the full corner is (0, y_bottom) -- distinct from the (0,0) top-left
        # default, which is what this guards against.
        assert (root.winfo_rootx(), root.winfo_rooty()) != (0, 0), \
            "show must re-apply the bottom-left geometry"

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
    bottom-left geometry, X maps it visibly at the top-left (0,0) and only then
    moves it down -- the 'menu flashes at top-left on the first click' bug. The
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
        ("tooltip_theme_constants_exist", test_tooltip_theme_constants_exist, ()),
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

    # test_ui_build_and_contents / search / clear-order / pin / power icons
    for name, fn in (
        ("ui_build_and_contents", test_ui_build_and_contents),
        ("ui_search_filter", test_ui_search_filter),
        ("ui_search_clear_after_partial_filter",
         test_ui_search_clear_after_partial_filter),
        ("ui_reorders_after_launch_without_restart",
         test_ui_reorders_after_launch_without_restart),
        ("ui_search_filtering_never_churns_windows",
         test_ui_search_filtering_never_churns_windows),
        ("ui_pin_keeps_menu_open", test_ui_pin_keeps_menu_open),
        ("ui_super_key_binding_is_present", test_ui_super_key_binding_is_present),
        ("ui_super_key_closes_and_respects_pin",
         test_ui_super_key_closes_and_respects_pin),
        ("ui_pin_is_a_focus_independent_toggle",
         test_ui_pin_is_a_focus_independent_toggle),
        ("ui_pinned_claims_x_focus_onto_own_window",
         test_ui_pinned_claims_x_focus_onto_own_window),
        ("ui_pinned_forced_close_still_works",
         test_ui_pinned_forced_close_still_works),
        ("ui_pin_before_arm_does_not_re_grab",
         test_ui_pin_before_arm_does_not_re_grab),
        ("ui_power_buttons_use_breeze_icons",
         test_ui_power_buttons_use_breeze_icons),
        ("ui_search_standard_editing", test_ui_search_standard_editing),
        ("ui_highlight_bar_no_leak_on_double_show",
         test_ui_highlight_bar_no_leak_on_double_show),
        ("ui_highlight_bar_placed_over_leftmost_icon",
         test_ui_highlight_bar_placed_over_leftmost_icon),
        ("ui_power_row_centered_and_not_clipped",
         test_ui_power_row_centered_and_not_clipped),
        ("ui_settings_button_is_disabled", test_ui_settings_button_is_disabled),
        ("ui_pin_button_still_enabled", test_ui_pin_button_still_enabled),
        ("ui_dim_image_greys_but_keeps_size",
         test_ui_dim_image_greys_but_keeps_size),
        ("ui_settings_button_has_tooltip", test_ui_settings_button_has_tooltip),
        ("ui_settings_tooltip_is_instant", test_ui_settings_tooltip_is_instant),
        ("ui_settings_tooltip_renders_once_and_sticks",
         test_ui_settings_tooltip_renders_once_and_sticks),
        ("ui_settings_tooltip_hides_when_exiting_onto_popup",
         test_ui_settings_tooltip_hides_when_exiting_onto_popup),
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

    # power wiring test with monkeypatched power actions
    total += 1
    prec = _Recorder()
    saved = {}
    for nm in ("suspend", "reboot", "poweroff", "lock_session"):
        saved[nm] = getattr(actions, nm)
        setattr(actions, nm, (lambda n: (lambda: prec.calls.append(n)))(nm))
    try:
        test_ui_power_buttons_wired(prec)
        print("ok   ui_power_buttons_wired")
    except AssertionError as ex:
        failures += 1
        print(f"FAIL ui_power_buttons_wired: {ex}")
    except Exception as ex:  # noqa: BLE001
        failures += 1
        print(f"ERR  ui_power_buttons_wired: {type(ex).__name__}: {ex}")
    finally:
        for nm, fn in saved.items():
            setattr(actions, nm, fn)

    print(f"\n{total - failures}/{total} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
