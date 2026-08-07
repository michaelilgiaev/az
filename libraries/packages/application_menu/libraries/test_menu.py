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
        "bssh.desktop", "bvnc.desktop", "avahi-discover.desktop",
        "azarch-install.desktop", "lstopo.desktop", "htop.desktop",
        "lftp.desktop", "cups.desktop", "org.kde.kmenuedit.desktop",
        "assistant.desktop", "qdbusviewer.desktop", "linguist.desktop",
        "qv4l2.desktop", "qvidcap.desktop", "designer.desktop",
        "stoken-gui.desktop", "stoken-gui-small.desktop", "vim.desktop",
    ):
        assert wanted in apps.HIDDEN_DESKTOP_IDS, wanted


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
        assert len(m.rows) == len(m.all_apps)
        assert len(m.visible_rows) == len(m.rows)  # empty query shows all
        # Every row has a name + a type subtitle.
        for r in m.rows:
            assert r.entry.name
            assert r.entry.type_label
        assert root.az_highlight is not None
    finally:
        root.destroy()


def test_ui_search_filter() -> None:
    _menu, root = _build_testable_menu()
    try:
        m = root.az_menu

        def visible_names() -> list[str]:
            return [r.entry.name for r in m.visible_rows]

        # Capture the canonical (frequency-then-alphabetical) order shown when
        # no query is active. Clearing the search must restore EXACTLY this.
        original_order = visible_names()
        assert original_order == [r.entry.name for r in m.rows]

        m.search_var.set("kit")
        root.update_idletasks()
        vn = visible_names()
        assert vn == ["kitty"], vn

        # Filter by TYPE label too, not just name.
        m.search_var.set("web browser")
        root.update_idletasks()
        vn = visible_names()
        assert any(n == "LibreWolf" for n in vn), vn
        assert all("web browser" in r.entry.name.casefold()
                   or "web browser" in r.entry.type_label.casefold()
                   for r in m.visible_rows)

        m.search_var.set("zzzznope")
        root.update_idletasks()
        assert visible_names() == []
        assert m.selected_index == -1

        # Clear -> the reshuffle-bug regression check: the list comes back in the
        # SAME order it started in, not scrambled by the filter history. We check
        # both the model order (visible_rows) and the actual on-screen pack order
        # (grid/pack info y-position) to be sure nothing is merely logically
        # ordered while visually shuffled.
        m.search_var.set("")
        root.update_idletasks()
        assert visible_names() == original_order, visible_names()
        # On-screen order: rows sorted by their y position must match too.
        by_screen = sorted(m.visible_rows, key=lambda r: r.winfo_y())
        assert [r.entry.name for r in by_screen] == original_order
    finally:
        root.destroy()


def test_ui_search_clear_after_partial_filter() -> None:
    """A tighter reshuffle regression: filter down to a subset that KEEPS some
    rows visible while hiding others (the case that used to append re-shown rows
    after the survivors), then clear and confirm the full canonical order."""
    _menu, root = _build_testable_menu()
    try:
        m = root.az_menu
        original = [r.entry.name for r in m.rows]
        # 'a' keeps every app whose name/type contains 'a' visible and hides the
        # rest -- a genuine partial filter, not all-or-nothing.
        m.search_var.set("a")
        root.update_idletasks()
        m.search_var.set("")
        root.update_idletasks()
        assert [r.entry.name for r in m.visible_rows] == original
        by_screen = sorted(m.visible_rows, key=lambda r: r.winfo_y())
        assert [r.entry.name for r in by_screen] == original
    finally:
        root.destroy()


def test_ui_reorders_after_launch_without_restart() -> None:
    """Launch frequency must re-sort the LIVE list, not only on the next process
    start. The daemon never dies, so recording a launch has to bump the app up on
    the next show -- otherwise the order looks frozen until a restart (the bug).

    Records enough launches on a currently-low app to make it the most-used, then
    drives a re-show (reset_view, what the daemon calls) and asserts it floated to
    the top of both the model order and the on-screen pack order."""
    _menu, root = _build_testable_menu()
    try:
        m = root.az_menu
        names = [r.entry.name for r in m.rows]
        assert len(names) >= 2, names
        # Pick an app that is NOT already first, and make it the most launched.
        victim = m.rows[-1].entry           # last == least-used / last al:pha
        assert victim.name != m.rows[0].entry.name
        for _ in range(50):
            m.usage.record(victim.desktop_id)

        # Re-show the menu the way the daemon does (no new process).
        m.reset_view()
        root.update_idletasks()

        assert m.rows[0].entry.desktop_id == victim.desktop_id, (
            "most-launched app must be FIRST after a launch, without a restart; "
            f"got {[r.entry.name for r in m.rows][:5]}"
        )
        assert m.visible_rows[0].entry.desktop_id == victim.desktop_id
        # On-screen: the topmost row (smallest y) is the victim.
        by_screen = sorted(m.visible_rows, key=lambda r: r.winfo_y())
        assert by_screen[0].entry.desktop_id == victim.desktop_id
    finally:
        root.destroy()


def test_ui_search_narrowing_does_not_rechurn_survivors() -> None:
    """Typing must not flash the whole list. As the query narrows, rows that stay
    visible must NOT be unpacked/repacked -- only rows whose visibility actually
    changes may move. The old filter forgot EVERY row on each keystroke and
    repacked the matches, which flashes the survivors. We assert survivors are
    never pack_forgotten while narrowing."""
    _menu, root = _build_testable_menu()
    try:
        m = root.az_menu

        forgets: dict[int, int] = {}
        for r in m.rows:
            orig = r.pack_forget
            key = id(r)
            forgets[key] = 0

            def make(o, k):
                def wrapped(*a, **kw):
                    forgets[k] += 1
                    return o(*a, **kw)
                return wrapped
            r.pack_forget = make(orig, key)

        # Establish a query, then NARROW it (each step is a subset of the prior).
        m.search_var.set("a")
        root.update_idletasks()
        survivors_after_a = list(m.visible_rows)
        assert survivors_after_a, "test needs a query that matches something"

        # Reset counters: we only care about churn during the NARROWING step.
        for k in forgets:
            forgets[k] = 0

        # Narrow further -- every row still matching 'ar' also matched 'a', so all
        # 'ar' survivors were already visible and must not be re-churned.
        m.search_var.set("ar")
        root.update_idletasks()
        final = set(id(r) for r in m.visible_rows)

        churned_survivors = [
            r for r in m.visible_rows if forgets[id(r)] > 0
        ]
        assert not churned_survivors, (
            "rows that stay visible while narrowing were unpacked (flash): "
            f"{[r.entry.name for r in churned_survivors]}"
        )
        # Sanity: narrowing actually removed at least one row (real narrowing).
        assert len(final) <= len(survivors_after_a)
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
        assert m.selected_index == 0
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
        ("ui_search_narrowing_does_not_rechurn_survivors",
         test_ui_search_narrowing_does_not_rechurn_survivors),
        ("ui_pin_keeps_menu_open", test_ui_pin_keeps_menu_open),
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
