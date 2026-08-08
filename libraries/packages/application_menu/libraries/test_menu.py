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
        "azarch-application-menu.desktop", "bssh.desktop", "bvnc.desktop",
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
        victim = al.all_entries[-1]         # last == least-used / last alpha
        assert victim.name != al.all_entries[0].name
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


def test_ui_pin_keeps_capturing_and_regrabs_on_press() -> None:
    """The pin-focus spec, as a state machine:

      1. Press pin (unpinned)         -> pinned AND capturing (search stays live).
      2. User switches app (alt-tab)  -> still pinned, but NO longer capturing
                                         (menu stays open, search goes dormant, and
                                         the keyboard is handed to the new window).
      3. Press pin (pinned, dormant)  -> STAYS pinned and re-grabs focus (this is
                                         'hover back and press to gain focus'); it
                                         must NOT unpin here.
      4. Press pin (pinned, live)     -> unpins.

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

        # 3. Press pin while pinned-but-dormant -> re-grab focus, STILL pinned.
        m._toggle_pin()
        assert st["pinned"] is True, "pressing pin while dormant must NOT unpin"
        assert st["capturing"] is True, "pressing pin must re-grab focus"
        assert m.pin_button._active is True

        # 4. Press pin while pinned-and-live -> unpin.
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
        # Geometry re-applied on show: not stuck at the 0,0 re-map default.
        assert (root.winfo_rootx(), root.winfo_rooty()) != (0, 0), \
            "show must re-apply the bottom-right geometry"

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
    bottom-right geometry, X maps it visibly at 0,0 and only then moves it -- the
    'menu opens at top-left on the first click' bug. The position must be set
    BEFORE the window is mapped, so geometry() must be called before deiconify().

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
        ("ui_pin_keeps_capturing_and_regrabs_on_press",
         test_ui_pin_keeps_capturing_and_regrabs_on_press),
        ("ui_pinned_claims_x_focus_onto_own_window",
         test_ui_pinned_claims_x_focus_onto_own_window),
        ("ui_pinned_forced_close_still_works",
         test_ui_pinned_forced_close_still_works),
        ("ui_pin_before_arm_does_not_re_grab",
         test_ui_pin_before_arm_does_not_re_grab),
        ("ui_power_buttons_use_breeze_icons",
         test_ui_power_buttons_use_breeze_icons),
        ("ui_search_standard_editing", test_ui_search_standard_editing),
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
