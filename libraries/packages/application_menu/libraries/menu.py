#!/usr/bin/env python3
"""Az'arch application menu -- a borderless Tkinter panel styled like Plasma's
Kickoff (the "hamburger") menu, pinned flush to the RIGHT edge of the screen.

This is OUR application menu, a companion to KDE's Kickoff. It shows a search
box, the list of installed applications ordered by how often they are launched
(most-used first), each with a big Name and a small "type" subtitle derived from
its freedesktop category (Kitty / Terminal), and a bottom row of session actions
(Sleep, Lock, Restart, Shut Down) drawn with real Breeze icons. It is opened by
a dedicated panel icon (see the install script).

Behaviour (matched to Plasma's Kickoff popup):
  * NO window chrome -- overrideredirect(True) removes the titlebar/toolbar and
    its min/max/close buttons entirely (KDE cannot decorate it).
  * Same SIZE as the live Plasma Kickoff popup (read from its popupWidth/
    popupHeight, with a sensible fallback), pinned to the bottom-RIGHT corner
    just above the bottom panel.
  * Breeze-like flat styling (see theme.py) so it reads as part of the desktop.
  * CLOSES ON ANY CLICK OUTSIDE ITSELF, exactly like Kickoff -- UNLESS the user
    has PINNED it. The pin button (top-right) toggles a "stay open" state: when
    pinned, clicks outside / focus loss are ignored and the menu stays put; when
    unpinned it dismisses normally. This mirrors Kickoff's pin. The close path
    always releases the global pointer grab, so it can never wedge the session.
  * HIGHLIGHT BAR over the panel icon while the menu is open.

Layout (see rough-design.png):
  [ search......................... ] [settings] [pin]   <- top row
  ------------------------------------------------------
   [icon]  Application Name                              <- scrollable app list
           type of application                              (freq-ordered)
   ...
  ------------------------------------------------------
     [sleep] Sleep   [lock] Lock  [reboot] Restart ...   <- bottom row (Breeze)

The settings (gear) button is pressable but intentionally does nothing. The pin
button is fully functional.

Kept dependency-free on purpose: Tkinter ships in the Python standard library
(backed by the system `tk` package) and Breeze icons are rasterised via the
system `rsvg-convert`. App discovery lives in apps.py, icon rasterising in
icons.py, launch/power in actions.py, usage tracking in usage.py, the widgets in
widgets.py and the palette in theme.py -- all imported from the install dir.
"""

from __future__ import annotations

import os
import re
import sys
import tkinter as tk

# Sibling modules live next to this file (installed together under
# /usr/local/lib/azarch-application-menu). Make sure that dir is importable even
# when run by absolute path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import actions  # noqa: E402
import theme as T  # noqa: E402
from apps import AppEntry, scan_applications  # noqa: E402
from icons import IconResolver  # noqa: E402
from usage import UsageStore  # noqa: E402
from widgets import AppRow, HighlightBar, IconButton, PowerButton  # noqa: E402


# --- Geometry helper ------------------------------------------------------
def kickoff_popup_size() -> tuple[int, int]:
    """Return (width, height) of the live Kickoff popup, read from Plasma's
    appletsrc (popupWidth / popupHeight). Falls back to theme defaults if the
    file or keys are absent, so the menu still matches Kickoff's footprint."""
    w = h = None
    try:
        with open(T.APPLETSRC, encoding="utf-8") as fh:
            for ln in fh:
                m = re.match(r"popupWidth=(\d+)", ln)
                if m:
                    w = int(m.group(1))
                m = re.match(r"popupHeight=(\d+)", ln)
                if m:
                    h = int(m.group(1))
    except OSError:
        pass
    return (w or T.DEFAULT_WIDTH, h or T.DEFAULT_HEIGHT)


# --- The menu content -----------------------------------------------------
class AppMenu:
    """Builds and drives the menu content inside an already-created root window:
    the search row, the frequency-ordered scrollable application list, and the
    power row. Holds the app model + icon resolver + usage store and wires search
    filtering, launching (which records usage), and the pin toggle."""

    def __init__(self, root: tk.Tk, close_menu, on_pin_toggle) -> None:
        self.root = root
        self.close_menu = close_menu
        self._on_pin_toggle = on_pin_toggle
        self.icons = IconResolver(size=T.ICON_SIZE)
        # A second resolver at the (smaller) session-icon size for the bottom
        # bar and top buttons, so those icons are crisp rather than downscaled.
        self.small_icons = IconResolver(size=T.POWER_ICON_SIZE)
        self.usage = UsageStore()
        # Canonical order: most-launched first, then alphabetical. This is the
        # ONE true order the list is always restored to (see _apply_filter).
        self.all_apps: list[AppEntry] = self.usage.sorted_apps(
            scan_applications()
        )
        self.rows: list[AppRow] = []
        self.visible_rows: list[AppRow] = []
        self.selected_index = -1
        self.search_var = tk.StringVar()
        self.pin_button: IconButton | None = None

        self._build()

    # -- construction ------------------------------------------------------
    def _build(self) -> None:
        inner = tk.Frame(self.root, bg=T.BG_COLOR)
        inner.pack(fill="both", expand=True)

        self._build_search_row(inner)
        self._divider(inner)
        self._build_app_list(inner)
        self._divider(inner)
        self._build_power_row(inner)

        # Populate the list (already in canonical order) and focus the search.
        self._populate(self.all_apps)
        self.search_var.trace_add("write", lambda *_: self._on_search())
        self.root.after(40, self._focus_search)

    def _divider(self, parent: tk.Widget) -> None:
        tk.Frame(parent, bg=T.DIVIDER_COLOR, height=1).pack(fill="x")

    def _focus_search(self) -> None:
        try:
            self.search_entry.focus_set()
        except tk.TclError:
            pass

    # -- top: search + settings(no-op) + pin -------------------------------
    def _build_search_row(self, parent: tk.Widget) -> None:
        # The row fills the width; the search box expands to take all the space
        # left of the two right-aligned buttons (settings, pin) -- matching the
        # design where the box spans nearly the full width.
        row = tk.Frame(parent, bg=T.BG_COLOR)
        row.pack(fill="x", padx=12, pady=(12, 8))

        # -- settings + pin buttons, packed to the RIGHT (pin outermost) ----
        gear_img = self.small_icons.load("configure")
        pin_img = self.small_icons.load("window-pin")
        self.pin_button = IconButton(row, pin_img, self._toggle_pin)
        self.pin_button.pack(side="right", padx=(8, 0))
        IconButton(row, gear_img, self._noop).pack(side="right", padx=(8, 0))

        # -- search box: a rounded surface frame with magnifier + entry ------
        box = tk.Frame(
            row, bg=T.SURFACE_COLOR, highlightthickness=1,
            highlightbackground=T.DIVIDER_COLOR, highlightcolor=T.BORDER_COLOR,
        )
        box.pack(side="left", fill="x", expand=True)

        search_img = self.small_icons.load("edit-find")
        mag = tk.Label(box, image=search_img, bg=T.SURFACE_COLOR)
        mag.image = search_img
        mag.pack(side="left", padx=(8, 4), pady=6)

        # The entry frame holds the entry plus an overlay placeholder label so
        # the placeholder NEVER lives inside the StringVar (keeping the query
        # clean). The label is lifted over the entry while it is empty.
        entry_wrap = tk.Frame(box, bg=T.SURFACE_COLOR)
        entry_wrap.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.search_entry = tk.Entry(
            entry_wrap, textvariable=self.search_var,
            bg=T.SURFACE_COLOR, fg=T.TEXT_COLOR, insertbackground=T.TEXT_COLOR,
            relief="flat", font=("Noto Sans", 12),
            highlightthickness=0, borderwidth=0,
        )
        self.search_entry.pack(fill="both", expand=True, ipady=6)

        self._placeholder_lbl = tk.Label(
            entry_wrap, text="Search...", bg=T.SURFACE_COLOR,
            fg=T.PLACEHOLDER_COLOR, font=("Noto Sans", 12), anchor="w",
        )
        self._placeholder_lbl.place(in_=self.search_entry, x=2, rely=0.5,
                                    anchor="w")
        self._placeholder_lbl.bind(
            "<Button-1>", lambda _e: self.search_entry.focus_set()
        )
        self._update_placeholder()

    def _noop(self) -> None:
        """Settings (gear) button: deliberately does nothing (placeholder)."""
        self._focus_search()

    def _toggle_pin(self) -> None:
        """Flip the pinned state and reflect it on the button + close logic."""
        pinned = self._on_pin_toggle()
        if self.pin_button is not None:
            self.pin_button.set_active(pinned)
        self._focus_search()

    def _update_placeholder(self) -> None:
        """Show the 'Search...' overlay only while the query is empty."""
        try:
            if self.search_var.get():
                self._placeholder_lbl.place_forget()
            else:
                self._placeholder_lbl.place(
                    in_=self.search_entry, x=2, rely=0.5, anchor="w"
                )
        except tk.TclError:
            pass

    # -- middle: scrollable application list -------------------------------
    def _build_app_list(self, parent: tk.Widget) -> None:
        wrap = tk.Frame(parent, bg=T.BG_COLOR)
        wrap.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(
            wrap, bg=T.BG_COLOR, highlightthickness=0, borderwidth=0
        )
        self.canvas.pack(side="left", fill="both", expand=True)

        self.scrollbar = tk.Scrollbar(
            wrap, orient="vertical", command=self.canvas.yview,
            troughcolor=T.BG_COLOR, bg=T.SURFACE_COLOR, borderwidth=0,
            highlightthickness=0, activebackground=T.HOVER_COLOR, width=10,
        )
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.list_frame = tk.Frame(self.canvas, bg=T.BG_COLOR)
        self._list_window = self.canvas.create_window(
            (0, 0), window=self.list_frame, anchor="nw"
        )

        def on_frame_config(_e=None) -> None:
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))

        def on_canvas_config(e) -> None:
            self.canvas.itemconfigure(self._list_window, width=e.width)

        self.list_frame.bind("<Configure>", on_frame_config)
        self.canvas.bind("<Configure>", on_canvas_config)

        # Mouse-wheel scrolling (X11 delivers Button-4/5).
        for seq, delta in (("<Button-4>", -1), ("<Button-5>", 1)):
            self.canvas.bind_all(seq, self._make_wheel(delta))
        self.canvas.bind_all("<MouseWheel>", self._wheel_win)

    def _make_wheel(self, direction: int):
        def handler(_e=None) -> None:
            self.canvas.yview_scroll(direction, "units")
        return handler

    def _wheel_win(self, e) -> None:
        self.canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")

    def _populate(self, apps: list[AppEntry]) -> None:
        """Build (once) all rows in canonical order; shown/hidden by the search
        filter so we never rebuild widgets on each keystroke."""
        for entry in apps:
            img = self.icons.load(entry.icon)
            row = AppRow(self.list_frame, entry, img, self._activate_entry)
            self.rows.append(row)
        self._apply_filter("")

    # -- search filtering --------------------------------------------------
    def _on_search(self) -> None:
        self._update_placeholder()
        self._apply_filter(self.search_var.get())

    def _apply_filter(self, query: str) -> None:
        # The StringVar trace can fire during teardown; bail if the window is
        # already gone.
        try:
            if not self.root.winfo_exists():
                return
        except tk.TclError:
            return
        q = query.strip().casefold()

        # Re-pack EVERY row from scratch in the canonical self.rows order so the
        # list is always in the same order regardless of filter history. This is
        # what fixes the "clear the search and the rows shuffle" bug: without the
        # unconditional forget-then-repack, re-showing hidden rows appends them
        # after rows that stayed visible, scrambling the order.
        self.visible_rows = []
        for row in self.rows:
            row.pack_forget()
        for row in self.rows:
            e = row.entry
            if not q or q in e.name.casefold() or q in e.type_label.casefold():
                row.pack(fill="x")
                self.visible_rows.append(row)

        # Reset selection to the first visible row so Enter launches something.
        self.selected_index = 0 if self.visible_rows else -1
        self._refresh_selection()
        self.canvas.yview_moveto(0.0)

    def _refresh_selection(self) -> None:
        for i, row in enumerate(self.visible_rows):
            row.set_selected(i == self.selected_index)

    # -- keyboard navigation ----------------------------------------------
    def move_selection(self, delta: int) -> None:
        if not self.visible_rows:
            return
        self.selected_index = max(
            0, min(len(self.visible_rows) - 1, self.selected_index + delta)
        )
        self._refresh_selection()
        self._scroll_to_selected()

    def _scroll_to_selected(self) -> None:
        if not (0 <= self.selected_index < len(self.visible_rows)):
            return
        row = self.visible_rows[self.selected_index]
        self.root.update_idletasks()
        try:
            top = row.winfo_y()
            height = row.winfo_height()
            total = self.list_frame.winfo_height() or 1
            view_top, view_bot = self.canvas.yview()
            frac_top = top / total
            frac_bot = (top + height) / total
            if frac_top < view_top:
                self.canvas.yview_moveto(frac_top)
            elif frac_bot > view_bot:
                self.canvas.yview_moveto(frac_bot - (view_bot - view_top))
        except (tk.TclError, ZeroDivisionError):
            pass

    def activate_selected(self) -> None:
        if 0 <= self.selected_index < len(self.visible_rows):
            self.visible_rows[self.selected_index].activate()

    def _activate_entry(self, entry: AppEntry) -> None:
        # Record the launch BEFORE closing so the count is bumped even though the
        # menu is about to be destroyed; next open reflects the new frequency.
        self.usage.record(entry.desktop_id)
        actions.launch(entry.exec_argv)
        self.close_menu(force=True)

    # -- bottom: power row (Breeze icons, filling the bar) -----------------
    def _build_power_row(self, parent: tk.Widget) -> None:
        row = tk.Frame(parent, bg=T.BG_COLOR)
        row.pack(fill="x", pady=(4, 6))

        # (icon-name, label, callback). Lock added per spec, between Sleep and
        # Restart. Icons are the same Breeze session icons Kickoff's leave
        # buttons use, rasterised via IconResolver.
        items = (
            ("system-suspend", "Sleep", self._do(actions.suspend)),
            ("system-lock-screen", "Lock", self._do(actions.lock_session)),
            ("system-reboot", "Restart", self._do(actions.reboot)),
            ("system-shutdown", "Shut Down", self._do(actions.poweroff)),
        )
        # expand=True on each -> the four buttons share the bar evenly and fill
        # the whole window width (bigger buttons, per spec).
        for icon_name, label, cb in items:
            img = self.small_icons.load(icon_name)
            PowerButton(row, img, label, cb).pack(
                side="left", expand=True, fill="x"
            )

    def _do(self, fn):
        """Wrap a power action so it closes the menu, then fires the action."""
        def run() -> None:
            self.close_menu(force=True)
            fn()
        return run


# --- Window assembly ------------------------------------------------------
def build_window() -> tk.Tk:
    """Create and lay out the menu window WITHOUT entering the event loop, so it
    is unit-testable: a caller can build it, assert on it, and destroy it without
    ever calling mainloop().

    The returned root carries the highlight bar, the AppMenu content, the pin
    state and the close wiring; a test can inspect ``root.az_highlight``,
    ``root.az_menu``, ``root.az_pinned`` and the bound events."""
    root = tk.Tk()
    root.title("Az'arch Menu")

    # Remove ALL window-manager chrome: no titlebar, no min/max/close buttons.
    root.overrideredirect(True)

    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()

    # Same footprint as the live Kickoff popup, pinned to the bottom-RIGHT
    # corner sitting just above the bottom panel (flush to the right edge).
    win_w, win_h = kickoff_popup_size()
    x = screen_w - win_w
    y = screen_h - T.PANEL_HEIGHT - win_h
    root.geometry(f"{win_w}x{win_h}+{x}+{y}")
    root.configure(bg=T.BG_COLOR)

    # --- Pin + close-on-outside-click, Kickoff style ----------------------
    state = {"closed": False, "pinned": False}
    # Pending after() timer ids, cancelled on close so no deferred callback ever
    # runs against a destroyed interpreter (which Tk would report as a spurious
    # "invalid command name ...arm_focus_out" on stderr).
    timers: list[str] = []

    def _later(ms: int, fn) -> None:
        try:
            timers.append(root.after(ms, fn))
        except tk.TclError:
            pass

    def toggle_pin() -> bool:
        """Flip pinned; return the new pinned state (for the button to reflect).

        When becoming pinned we also drop the global pointer grab so clicks land
        normally on other windows (a pinned menu must not eat the whole desktop's
        input); when unpinning we re-take it so the next outside click dismisses.
        """
        state["pinned"] = not state["pinned"]
        root.az_pinned = state["pinned"]
        try:
            if state["pinned"]:
                root.grab_release()
            else:
                root.grab_set_global()
        except tk.TclError:
            pass
        return state["pinned"]

    def close_menu(*_a, force: bool = False) -> None:
        # A pinned menu ignores dismissal requests (outside click / focus loss /
        # Escape) UNLESS forced -- launching an app or a power action always
        # closes, pinned or not.
        if state["closed"]:
            return
        if state["pinned"] and not force:
            return
        state["closed"] = True
        # Cancel any pending deferred callbacks before tearing the window down.
        for tid in timers:
            try:
                root.after_cancel(tid)
            except tk.TclError:
                pass
        timers.clear()
        try:
            root.grab_release()
        except tk.TclError:
            pass
        bar = getattr(root, "az_highlight", None)
        if bar is not None:
            bar.close()
        try:
            root.destroy()
        except tk.TclError:
            pass

    def on_button(event: tk.Event) -> None:
        """Global button handler: close when the press is OUTSIDE the menu and
        we are not pinned; otherwise let it through."""
        if state["pinned"]:
            return
        x0, y0 = root.winfo_rootx(), root.winfo_rooty()
        x1, y1 = x0 + root.winfo_width(), y0 + root.winfo_height()
        inside = (x0 <= event.x_root < x1 and y0 <= event.y_root < y1)
        if not inside:
            close_menu()

    def on_focus_out(_event: tk.Event) -> None:
        """Close when focus genuinely leaves our application (the user activated
        another window), NOT when focus merely moves between our own widgets, and
        NOT when pinned. Deferred one tick so the internal focus churn on open
        (force focus -> focus the search box) cannot self-close the menu."""
        if state["closed"] or state["pinned"]:
            return

        def check() -> None:
            if state["closed"] or state["pinned"]:
                return
            try:
                focused = root.focus_displayof()
            except (tk.TclError, KeyError):
                focused = None
            if focused is None:
                close_menu()

        try:
            root.after(1, check)
        except tk.TclError:
            pass

    # Build the menu content (search + app list + power row).
    menu = AppMenu(root, close_menu, toggle_pin)
    root.az_menu = menu
    root.az_pinned = False

    # Escape closes (unless pinned); arrows move selection; Enter launches.
    root.bind("<Escape>", close_menu)
    root.bind("<Down>", lambda _e: menu.move_selection(1))
    root.bind("<Up>", lambda _e: menu.move_selection(-1))
    root.bind("<Return>", lambda _e: menu.activate_selected())
    root.bind("<KP_Enter>", lambda _e: menu.activate_selected())
    root.bind_all("<Button>", on_button)

    def arm() -> None:
        """Once mapped: take the global pointer grab so clicks anywhere reach
        on_button, pull keyboard focus, pop in the icon highlight bar, and only
        THEN arm the focus-out backup (so the focus churn during open cannot
        self-close the menu).

        arm() runs deferred (~30ms after open), so a very fast user could PIN the
        menu in the gap before it fires. Pinning releases the global grab on
        purpose (a pinned menu must not eat the whole desktop's clicks), so arm()
        must NOT re-take that grab if we are already pinned -- otherwise it would
        re-black-hole every desktop click with no click-outside escape (a
        potential input wedge). Hence the pinned guard on the grab below."""
        if state["closed"]:
            return
        if not state["pinned"]:
            try:
                root.grab_set_global()
            except tk.TclError:
                pass
        try:
            root.focus_force()
        except tk.TclError:
            pass
        menu._focus_search()
        bar = getattr(root, "az_highlight", None)
        if bar is not None:
            bar.show()

        def arm_focus_out() -> None:
            if state["closed"]:
                return
            try:
                root.bind("<FocusOut>", on_focus_out)
            except tk.TclError:
                pass

        _later(150, arm_focus_out)

    root.az_highlight = HighlightBar(root, screen_w, screen_h)
    _later(30, arm)

    # Exposed for tests: the deferred-timer list and a direct close hook, so a
    # test can tear the window down cleanly (cancelling timers) instead of a
    # bare destroy() that leaves after() callbacks dangling.
    root.az_timers = timers
    root.az_close = close_menu

    return root


def main() -> None:
    """Entry point: build the window and run the Tk event loop."""
    root = build_window()
    root.mainloop()


if __name__ == "__main__":
    main()
