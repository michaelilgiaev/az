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
import editing  # noqa: E402
import theme as T  # noqa: E402
from applist import CanvasAppList  # noqa: E402
from apps import AppEntry, scan_applications  # noqa: E402
from icons import IconResolver  # noqa: E402
from usage import UsageStore  # noqa: E402
from widgets import HighlightBar, IconButton, PowerButton  # noqa: E402


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
    filtering, launching, and the pin toggle. (Launch *counting* lives in the
    daemon's WindowWatcher, which records every real window-open -- see
    winwatch.py -- so this menu's job is just to show and launch.)"""

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
        # ONE true order the list is always restored to.
        self.all_apps: list[AppEntry] = self.usage.sorted_apps(
            scan_applications()
        )
        # The scrollable list is a CanvasAppList (all apps drawn ONCE as canvas
        # items, filtered by show/hide -- never mapping/unmapping per-row X
        # windows, which is what made the old widget list flicker). Created in
        # _build_app_list; rows are populated lazily via populate().
        self.applist: CanvasAppList | None = None
        self._populated = False
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

        self.search_var.trace_add("write", lambda *_: self._on_search())
        # NOTE: the application rows are NOT built here. Building them loads a
        # PhotoImage per app, which is by far the most expensive part of opening
        # the menu; doing it synchronously would keep the whole window off-screen
        # until every row existed (the visible delay the user hit). Instead the
        # caller paints the chrome first, then calls populate() -- see main().

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
        # Standard desktop text-editing (select-all, cut/copy/paste, undo/redo,
        # word delete) so the search box behaves like any editor's input, not the
        # emacs-ish Tk default. Keep the returned undo stack referenced so its
        # var-trace survives.
        self._search_undo = editing.enable_standard_editing(
            self.search_entry, self.search_var
        )

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
        # The list is a CanvasAppList: every app is a set of canvas ITEMS (image
        # + two text lines + a selection rectangle), drawn once and filtered by
        # showing/hiding/moving those items. There are NO per-row child windows,
        # so filtering never maps/unmaps X windows and thus never flickers. The
        # items themselves are filled lazily by populate() (icon loading is the
        # expensive part of opening the menu).
        self.applist = CanvasAppList(
            parent, [], self.icons.load, self._activate_entry
        )

    def populate(self) -> None:
        """Fill the list with every application in canonical order, then apply
        whatever is currently typed in the search box. Idempotent: a second call
        is a no-op, so main() and the tests can both invoke it without
        double-building.

        This is deliberately NOT run during _build(): it loads a PhotoImage per
        app (the bulk of the open cost). The window's chrome is painted first and
        THEN this fills the list, so the menu appears instantly (see main())."""
        if self._populated:
            return
        try:
            if not self.root.winfo_exists():
                return
        except tk.TclError:
            return
        self.applist.set_entries(self.all_apps)
        self._populated = True
        # Honour a query the user may have typed before the list was filled;
        # falls back to the empty (show-all) filter otherwise.
        self.applist.apply_filter(self.search_var.get())

    # -- search filtering --------------------------------------------------
    def _on_search(self) -> None:
        self._update_placeholder()
        # The StringVar trace can fire during teardown; bail if the window is
        # already gone.
        try:
            if not self.root.winfo_exists():
                return
        except tk.TclError:
            return
        if self.applist is not None:
            self.applist.apply_filter(self.search_var.get())

    def resort(self) -> None:
        """Re-order the list by the CURRENT launch counts (most-used first, then
        A->Z). The daemon is a long-lived process, so a launch only bumps the
        in-memory usage counter -- without this the visible order would stay
        frozen until the process restarted (the 'sort only updates on restart'
        bug). Called on each re-show so the just-launched app floats up next time.

        Re-sorts self.all_apps, hands the new order to the list, then re-applies
        the CURRENT filter so both order and visibility stay correct regardless
        of an active query. Safe to call standalone."""
        self.all_apps = self.usage.sorted_apps(self.all_apps)
        if not self._populated or self.applist is None:
            # List not filled yet -> just fix the model order; populate() will
            # fill in this order.
            return
        self.applist.set_entries(self.all_apps)
        self.applist.apply_filter(self.search_var.get())

    def reset_view(self) -> None:
        """Return the menu to its just-opened state: list filled, search cleared
        (which restores the canonical order and shows everything), scrolled to the
        top with the first row selected. Called by the daemon each time it
        re-shows the window so a stale query/scroll from last time never lingers.

        Also re-sorts by the latest launch counts (resort) so the app the user
        just opened floats to the top on this open rather than only after a
        restart."""
        self.populate()  # no-op if already filled
        # Re-order by the latest usage so a launch since the last show is
        # reflected now (not only after a restart). This also re-applies the
        # current filter.
        self.resort()
        if self.search_var.get():
            # A query is lingering: clear it -> the trace re-filters to the full
            # canonical list and resets selection + scroll.
            self.search_var.set("")
        else:
            # Already empty -> make sure the list shows everything from the top
            # with the first row selected (resort already re-applied "").
            if self.applist is not None:
                self.applist.apply_filter("")
        self._update_placeholder()

    # -- keyboard navigation ----------------------------------------------
    def move_selection(self, delta: int) -> None:
        if self.applist is not None:
            self.applist.move_selection(delta)

    def activate_selected(self) -> None:
        if self.applist is not None:
            self.applist.activate_selected()

    def _activate_entry(self, entry: AppEntry) -> None:
        # Launch, then close. We do NOT bump the usage counter here: an "open" is
        # counted uniformly by the daemon's WindowWatcher when the app's WINDOW
        # actually appears -- so a launch from the taskbar, a desktop icon, a
        # terminal or a file association counts exactly like one from this menu,
        # and a click that fails to spawn anything is not miscounted. (When the
        # menu runs without the daemon/watcher -- e.g. the non-persistent test
        # harness -- no auto-count happens, which is why those tests record()
        # directly.)
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
def build_window(persistent: bool = False) -> tk.Tk:
    """Create and lay out the menu window WITHOUT entering the event loop, so it
    is unit-testable: a caller can build it, assert on it, and destroy it without
    ever calling mainloop().

    The returned root carries the highlight bar, the AppMenu content, the pin
    state and the close wiring; a test can inspect ``root.az_highlight``,
    ``root.az_menu``, ``root.az_pinned`` and the bound events.

    persistent=True switches the window into DAEMON mode: closing (outside click,
    Escape, focus loss, launching an app) HIDES the window (withdraw) instead of
    destroying it, so the resident daemon can re-show it instantly. In that mode
    the caller drives visibility with root.az_show() / root.az_hide()."""
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

    def _cancel_timers() -> None:
        for tid in timers:
            try:
                root.after_cancel(tid)
            except tk.TclError:
                pass
        timers.clear()

    def close_menu(*_a, force: bool = False) -> None:
        # A pinned menu ignores dismissal requests (outside click / focus loss /
        # Escape) UNLESS forced -- launching an app or a power action always
        # closes, pinned or not.
        if state["closed"]:
            return
        if state["pinned"] and not force:
            return
        # In PERSISTENT (daemon) mode we never destroy the window -- we just hide
        # it so the next open is instant. hide_menu() is defined below; closures
        # resolve names at call time so it is available by the time this runs.
        if persistent:
            hide_menu()
            return
        state["closed"] = True
        # Cancel any pending deferred callbacks before tearing the window down.
        _cancel_timers()
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

        arm() is scheduled on after_idle so it fires the INSTANT the window is
        mapped (no artificial delay -- the menu must open instantly). A very fast
        user could still PIN the menu in the gap before it fires. Pinning releases
        the global grab on purpose (a pinned menu must not eat the whole desktop's
        clicks), so arm() must NOT re-take that grab if we are already pinned --
        otherwise it would re-black-hole every desktop click with no
        click-outside escape (a potential input wedge). Hence the pinned guard on
        the grab below.

        A global grab only works once the window is viewable; if after_idle beat
        the map, reschedule ourselves a beat later rather than silently dropping
        the grab (which would leave clicks-outside unable to dismiss the menu)."""
        if state["closed"]:
            return
        try:
            viewable = bool(root.winfo_viewable())
        except tk.TclError:
            viewable = False
        if not viewable:
            _later(10, arm)
            return
        if not state["pinned"]:
            try:
                root.grab_set_global()
            except tk.TclError:
                # Still not grabbable -> try again shortly instead of giving up.
                _later(10, arm)
                return
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

    def hide_menu() -> None:
        """DAEMON mode: hide (withdraw) the window instead of destroying it, so
        the next show is instant. Releases the grab, drops the highlight bar,
        unbinds the focus-out backup, cancels timers, and marks the menu closed
        so stray handlers no-op while hidden."""
        state["closed"] = True
        _cancel_timers()
        try:
            root.unbind("<FocusOut>")
        except tk.TclError:
            pass
        try:
            root.grab_release()
        except tk.TclError:
            pass
        bar = getattr(root, "az_highlight", None)
        if bar is not None:
            bar.close()
        try:
            root.withdraw()
        except tk.TclError:
            pass

    def show_menu() -> None:
        """DAEMON mode: (re)show the pre-built window instantly. Resets the menu
        to a clean state -- unpinned, search cleared, list scrolled to top and
        the first row selected -- then maps it, raises it and arms the grab/focus/
        highlight. Because the window and all rows already exist, this is
        essentially instant (no build, no icon loading)."""
        state["closed"] = False
        state["pinned"] = False
        root.az_pinned = False
        # Rebuild the highlight bar (the previous hide destroyed it).
        try:
            root.az_highlight = HighlightBar(root, screen_w, screen_h)
        except tk.TclError:
            pass
        # Clean slate: clear the query (repopulates the full list in order) and
        # scroll back to the top.
        try:
            menu.reset_view()
        except tk.TclError:
            pass
        try:
            # Apply the bottom-right geometry BEFORE mapping. An overrideredirect
            # window sits at X's default 0,0 origin until positioned, and on the
            # very FIRST show it has never been mapped, so a deiconify() (MapWindow)
            # issued before the move makes X map it VISIBLY at 0,0 and only then
            # slide it into place -- the 'menu opens at the top-left on the first
            # click' bug. Positioning first means the window is only ever mapped at
            # the correct spot. (Re-shows also need this: a withdrawn override-
            # redirect window forgets its position with no WM to remember it.)
            root.geometry(f"{win_w}x{win_h}+{x}+{y}")
            root.deiconify()
            root.lift()
        except tk.TclError:
            pass
        # Arm on the next idle so the grab/focus/highlight fire the instant the
        # window is mapped (arm() reschedules itself if it beats the map).
        try:
            timers.append(root.after_idle(arm))
        except tk.TclError:
            pass

    root.az_highlight = HighlightBar(root, screen_w, screen_h)
    if persistent:
        # Daemon mode: do NOT arm now. The window is built, then withdrawn by the
        # daemon; arm()/grab happen on each show_menu().
        pass
    else:
        # Fire arm() the instant the window is mapped (after_idle), not on a fixed
        # timer -- part of making the menu open instantly. arm() reschedules
        # itself if it somehow beats the map (see its viewable guard).
        try:
            timers.append(root.after_idle(arm))
        except tk.TclError:
            pass

    # Exposed for tests: the deferred-timer list and a direct close hook, so a
    # test can tear the window down cleanly (cancelling timers) instead of a
    # bare destroy() that leaves after() callbacks dangling. az_populate lets a
    # caller/test fill the (deferred) application rows explicitly. az_show/az_hide
    # drive daemon-mode visibility.
    root.az_timers = timers
    root.az_close = close_menu
    root.az_populate = menu.populate
    root.az_show = show_menu
    root.az_hide = hide_menu

    return root


def main() -> None:
    """Entry point: build the window, paint it INSTANTLY, then fill the list.

    The chrome (search box, empty list, power bar) is forced on screen first --
    a cheap, fast paint -- and only then are the application rows built (loading
    an icon each, the expensive part). So the menu window pops up instantly and
    the rows fill in a beat later, instead of the whole thing hanging off-screen
    until every icon has loaded."""
    root = build_window()
    try:
        # Force the chrome to actually map + render before we do the heavy work.
        root.update_idletasks()
        root.wait_visibility(root)  # block until the window is truly viewable
        root.update()               # flush the expose so pixels hit the screen
    except tk.TclError:
        pass
    # Window is visible now -> build the application rows.
    root.az_menu.populate()
    root.mainloop()


if __name__ == "__main__":
    main()
