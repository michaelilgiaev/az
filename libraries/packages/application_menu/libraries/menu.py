#!/usr/bin/env python3
"""Az'arch application menu -- a borderless Tkinter launcher CENTERED on the screen.

This is OUR application menu, and it is the WHOLE shell now: KDE Plasma was removed
and the desktop is OpenBox with no panel, so this menu -- opened by the Super key
(via xcape + the OpenBox rc.xml keybind) -- is the only launcher surface. It shows a search box, the list of installed applications ordered
by how often they are launched (most-used first), each with a big Name and a small
"type" subtitle derived from its freedesktop category, and a bottom row of session
actions (Sleep, Lock, Restart, Shut Down) drawn with real Breeze icons.

Behaviour:
  * NO window chrome -- overrideredirect(True) removes the titlebar/toolbar and its
    min/max/close buttons entirely (OpenBox also has a *azarch*menu* <decor>no</decor>
    rule as a belt).
  * CENTERED on the screen (there is no panel to anchor to anymore; the old
    bottom-left placement is gone).
  * Breeze-like flat dark styling (see theme.py).
  * CLOSES ON ANY CLICK OUTSIDE ITSELF, on Escape, on focus loss, and on a second
    Super press. There is NO pin: the menu is a transient launcher. While open it
    holds a global pointer grab so an outside click always dismisses it; the close
    path always releases the grab so it can never wedge the session.

Layout:
  [ search....................................................... ]  <- top row
  ---------------------------------------------------------------
   [icon]  Application Name                                          <- scrollable app
           type of application                                         list (freq-order)
   ...
  ---------------------------------------------------------------
     [sleep] Sleep   [lock] Lock  [reboot] Restart  [power] ...     <- power row

TWO KEYBOARD FOCUS ZONES, toggled with TAB:
  * DEFAULT = "apps": the search box has the caret and the app list is navigable --
    typing filters, Up/Down move the selection, Enter launches the selected app. This
    is where the menu opens.
  * TAB -> "power": the app-list selection outline dims and the power row takes focus
    (one button shows a blue focus outline). Left/Right move between the power buttons
    and Enter activates the focused one. TAB again returns focus to the search box +
    app list (the default). So TAB flips between the two zones and always brings you
    back to the default on the next press.

The top-row Settings (gear) and pin buttons were REMOVED (the search box now spans the
full width), and the panel-icon highlight bar is gone with the panel.

Kept dependency-free on purpose: Tkinter ships in the Python standard library (backed
by the system `tk` package) and Breeze icons are rasterised via the system
`rsvg-convert`. App discovery lives in apps.py, icon rasterising in icons.py,
launch/power in actions.py, usage tracking in usage.py, the widgets in widgets.py and
the palette/geometry in theme.py -- all imported from the install dir.
"""

from __future__ import annotations

import os
import sys
import tkinter as tk

# Sibling modules live next to this file (installed together under
# /usr/local/lib/azarch-application-menu). Make sure that dir is importable even when
# run by absolute path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import actions  # noqa: E402
import editing  # noqa: E402
import theme as T  # noqa: E402
import xfocus  # noqa: E402
from applist import CanvasAppList  # noqa: E402
from apps import AppEntry, scan_applications  # noqa: E402
from icons import IconResolver  # noqa: E402
from usage import UsageStore  # noqa: E402
from widgets import PowerButton  # noqa: E402


# Focus zone identifiers for the TAB toggle.
FOCUS_APPS = "apps"     # search box + application list (the default)
FOCUS_POWER = "power"   # the bottom power-button row


# --- Geometry helper ------------------------------------------------------
def menu_size() -> tuple[int, int]:
    """Return the (width, height) to size the menu window -- the theme defaults. The
    menu is a fixed-size centered window now (Plasma/Kickoff is gone, so there is no
    appletsrc popup size to read anymore)."""
    return (T.DEFAULT_WIDTH, T.DEFAULT_HEIGHT)


# --- The menu content -----------------------------------------------------
class AppMenu:
    """Builds and drives the menu content inside an already-created root window: the
    search row, the frequency-ordered scrollable application list, and the power row.
    Holds the app model + icon resolver + usage store and wires search filtering,
    launching, and the TAB focus toggle. (Launch *counting* lives in the daemon's
    WindowWatcher, which records every real window-open -- see winwatch.py -- so this
    menu's job is just to show and launch.)"""

    def __init__(self, root: tk.Tk, close_menu) -> None:
        self.root = root
        self.close_menu = close_menu
        self.icons = IconResolver(size=T.ICON_SIZE)
        # A second resolver at the (smaller) session-icon size for the bottom bar, so
        # those icons are crisp rather than downscaled.
        self.small_icons = IconResolver(size=T.POWER_ICON_SIZE)
        self.usage = UsageStore()
        # Canonical order: most-launched first, then alphabetical. This is the ONE true
        # order the list is always restored to.
        self.all_apps: list[AppEntry] = self.usage.sorted_apps(
            scan_applications()
        )
        # The scrollable list is a CanvasAppList (all apps drawn ONCE as canvas items,
        # filtered by show/hide -- never mapping/unmapping per-row X windows, which is
        # what made the old widget list flicker). Created in _build_app_list; rows are
        # populated lazily via populate().
        self.applist: CanvasAppList | None = None
        self._populated = False
        self.search_var = tk.StringVar()

        # --- TAB focus state ---------------------------------------------
        # Which zone currently has keyboard focus: FOCUS_APPS (search + list, the
        # default) or FOCUS_POWER (the power row). The power buttons + the currently
        # focused index are filled by _build_power_row.
        self.focus_zone = FOCUS_APPS
        self.power_buttons: list[PowerButton] = []
        self._power_index = 0

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
        # PhotoImage per app, which is by far the most expensive part of opening the
        # menu; doing it synchronously would keep the whole window off-screen until
        # every row existed (the visible delay the user hit). Instead the caller paints
        # the chrome first, then calls populate() -- see main().

    def _divider(self, parent: tk.Widget) -> None:
        tk.Frame(parent, bg=T.DIVIDER_COLOR, height=1).pack(fill="x")

    def _focus_search(self) -> None:
        try:
            self.search_entry.focus_set()
        except tk.TclError:
            pass

    # -- top: full-width search box ----------------------------------------
    def _build_search_row(self, parent: tk.Widget) -> None:
        # The search box now spans the FULL width of the top row: the old Settings
        # (gear) and pin buttons were removed, so nothing sits to its right and the box
        # stretches to fill the freed space (the user's "stretch the search input box
        # to fill the new space" request).
        row = tk.Frame(parent, bg=T.BG_COLOR)
        row.pack(fill="x", padx=12, pady=(12, 8))

        # A rounded surface frame with magnifier + entry, filling the whole row.
        box = tk.Frame(
            row, bg=T.SURFACE_COLOR, highlightthickness=1,
            highlightbackground=T.DIVIDER_COLOR, highlightcolor=T.BORDER_COLOR,
        )
        box.pack(side="left", fill="x", expand=True)

        search_img = self.small_icons.load("edit-find")
        mag = tk.Label(box, image=search_img, bg=T.SURFACE_COLOR)
        mag.image = search_img
        mag.pack(side="left", padx=(8, 4), pady=6)

        # The entry frame holds the entry plus an overlay placeholder label so the
        # placeholder NEVER lives inside the StringVar (keeping the query clean). The
        # label is lifted over the entry while it is empty.
        entry_wrap = tk.Frame(box, bg=T.SURFACE_COLOR)
        entry_wrap.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.search_entry = tk.Entry(
            entry_wrap, textvariable=self.search_var,
            bg=T.SURFACE_COLOR, fg=T.TEXT_COLOR, insertbackground=T.TEXT_COLOR,
            relief="flat", font=(T.FONT_FAMILY, T.FONT_SEARCH),
            highlightthickness=0, borderwidth=0,
        )
        self.search_entry.pack(fill="both", expand=True, ipady=6)
        # A click in the entry puts the caret there and returns focus to the "apps"
        # zone (in case the user had TAB'd to the power row). add="+" so it runs
        # ALONGSIDE Tk's own click handling (caret placement / selection).
        self.search_entry.bind(
            "<Button-1>", lambda _e: self.set_focus_zone(FOCUS_APPS), add="+"
        )
        # Standard desktop text-editing (select-all, cut/copy/paste, undo/redo, word
        # delete) so the search box behaves like any editor's input, not the emacs-ish
        # Tk default. Keep the returned undo stack referenced so its var-trace survives.
        self._search_undo = editing.enable_standard_editing(
            self.search_entry, self.search_var
        )

        self._placeholder_lbl = tk.Label(
            entry_wrap, text="Search...", bg=T.SURFACE_COLOR,
            fg=T.PLACEHOLDER_COLOR, font=(T.FONT_FAMILY, T.FONT_SEARCH),
            anchor="w",
        )
        self._placeholder_lbl.place(in_=self.search_entry, x=2, rely=0.5,
                                    anchor="w")
        self._placeholder_lbl.bind(
            "<Button-1>", lambda _e: (self.set_focus_zone(FOCUS_APPS),
                                      self._focus_search())
        )
        self._update_placeholder()

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
        # The list is a CanvasAppList: every app is a set of canvas ITEMS (image + two
        # text lines + a selection rectangle), drawn once and filtered by
        # showing/hiding/moving those items. There are NO per-row child windows, so
        # filtering never maps/unmaps X windows and thus never flickers. The items
        # themselves are filled lazily by populate() (icon loading is the expensive
        # part of opening the menu).
        self.applist = CanvasAppList(
            parent, [], self.icons.load, self._activate_entry
        )

    def populate(self) -> None:
        """Fill the list with every application in canonical order, then apply whatever
        is currently typed in the search box. Idempotent: a second call is a no-op, so
        main() and the tests can both invoke it without double-building.

        This is deliberately NOT run during _build(): it loads a PhotoImage per app
        (the bulk of the open cost). The window's chrome is painted first and THEN this
        fills the list, so the menu appears instantly (see main())."""
        if self._populated:
            return
        try:
            if not self.root.winfo_exists():
                return
        except tk.TclError:
            return
        self.applist.set_entries(self.all_apps)
        self._populated = True
        # Honour a query the user may have typed before the list was filled; falls back
        # to the empty (show-all) filter otherwise.
        self.applist.apply_filter(self.search_var.get())

    # -- search filtering --------------------------------------------------
    def _on_search(self) -> None:
        self._update_placeholder()
        # Typing in the search box implies the "apps" zone owns focus.
        if self.focus_zone != FOCUS_APPS:
            self.set_focus_zone(FOCUS_APPS)
        # The StringVar trace can fire during teardown; bail if the window is already
        # gone.
        try:
            if not self.root.winfo_exists():
                return
        except tk.TclError:
            return
        if self.applist is not None:
            self.applist.apply_filter(self.search_var.get())

    def resort(self) -> None:
        """Re-order the list by the CURRENT launch counts (most-used first, then A->Z).
        The daemon is a long-lived process, so a launch only bumps the in-memory usage
        counter -- without this the visible order would stay frozen until the process
        restarted. Called on each re-show so the just-launched app floats up next time.

        Re-sorts self.all_apps, hands the new order to the list, then re-applies the
        CURRENT filter so both order and visibility stay correct regardless of an
        active query. Safe to call standalone."""
        self.all_apps = self.usage.sorted_apps(self.all_apps)
        if not self._populated or self.applist is None:
            # List not filled yet -> just fix the model order; populate() will fill in
            # this order.
            return
        self.applist.set_entries(self.all_apps)
        self.applist.apply_filter(self.search_var.get())

    def reset_view(self) -> None:
        """Return the menu to its just-opened state: list filled, search cleared (which
        restores the canonical order and shows everything), scrolled to the top with
        the first row selected, and the focus zone back to the default (apps). Called
        by the daemon each time it re-shows the window so a stale query/scroll/focus
        from last time never lingers.

        Also re-sorts by the latest launch counts (resort) so the app the user just
        opened floats to the top on this open rather than only after a restart."""
        self.populate()  # no-op if already filled
        # Focus always starts on the search box + app list (the default), even if the
        # user left the menu on the power row last time.
        self.set_focus_zone(FOCUS_APPS)
        # Re-order by the latest usage so a launch since the last show is reflected now
        # (not only after a restart). This also re-applies the current filter.
        self.resort()
        if self.search_var.get():
            # A query is lingering: clear it -> the trace re-filters to the full
            # canonical list and resets selection + scroll.
            self.search_var.set("")
        else:
            # Already empty -> make sure the list shows everything from the top with the
            # first row selected (resort already re-applied "").
            if self.applist is not None:
                self.applist.apply_filter("")
        self._update_placeholder()

    # -- keyboard navigation (routed from the window's key bindings) -------
    def on_up(self) -> None:
        """Up arrow: move the app-list selection up (only in the apps zone)."""
        if self.focus_zone == FOCUS_APPS and self.applist is not None:
            self.applist.move_selection(-1)

    def on_down(self) -> None:
        """Down arrow: move the app-list selection down (only in the apps zone)."""
        if self.focus_zone == FOCUS_APPS and self.applist is not None:
            self.applist.move_selection(1)

    def on_left(self) -> None:
        """Left arrow: in the power zone, move the button focus left."""
        if self.focus_zone == FOCUS_POWER:
            self._move_power_focus(-1)

    def on_right(self) -> None:
        """Right arrow: in the power zone, move the button focus right."""
        if self.focus_zone == FOCUS_POWER:
            self._move_power_focus(1)

    def on_activate(self) -> None:
        """Enter/Return: launch the selected app (apps zone) or fire the focused power
        button (power zone)."""
        if self.focus_zone == FOCUS_POWER:
            self._activate_power()
        elif self.applist is not None:
            self.applist.activate_selected()

    def toggle_focus(self) -> None:
        """TAB: flip between the two focus zones. From the default (apps) it moves to
        the power row; from the power row it returns to the default. So pressing TAB
        always brings focus back to the search box + app list on the next press."""
        if self.focus_zone == FOCUS_APPS:
            self.set_focus_zone(FOCUS_POWER)
        else:
            self.set_focus_zone(FOCUS_APPS)

    def set_focus_zone(self, zone: str) -> None:
        """Move keyboard focus to `zone` (FOCUS_APPS or FOCUS_POWER), updating the
        visuals so the user can see which pane is active: in the apps zone the search
        box has the caret and the app-list selection outline is shown; in the power
        zone the app-list outline dims and one power button shows the focus outline."""
        if zone not in (FOCUS_APPS, FOCUS_POWER):
            return
        self.focus_zone = zone
        if zone == FOCUS_APPS:
            # App list shows its selection again; caret back in the search box.
            if self.applist is not None:
                self.applist.set_selection_enabled(True)
            self._clear_power_focus()
            self._focus_search()
        else:
            # Power row takes focus: dim the app-list selection so it is visibly not the
            # active pane, and light up a power button. Keep the search caret out of the
            # way is not required (Tk focus stays where it is; our key bindings route by
            # focus_zone, not by Tk focus), but the visual cue is the important part.
            if self.applist is not None:
                self.applist.set_selection_enabled(False)
            self._power_index = max(
                0, min(self._power_index, len(self.power_buttons) - 1)
            )
            self._apply_power_focus()

    def _activate_entry(self, entry: AppEntry) -> None:
        # Launch, then close. We do NOT bump the usage counter here: an "open" is
        # counted uniformly by the daemon's WindowWatcher when the app's WINDOW actually
        # appears -- so a launch from the taskbar, a desktop icon, a terminal or a file
        # association counts exactly like one from this menu, and a click that fails to
        # spawn anything is not miscounted. (When the menu runs without the
        # daemon/watcher -- e.g. the non-persistent test harness -- no auto-count
        # happens, which is why those tests record() directly.)
        actions.launch(entry.exec_argv)
        self.close_menu(force=True)

    # -- bottom: power row (Breeze icons, filling the bar) -----------------
    def _build_power_row(self, parent: tk.Widget) -> None:
        row = tk.Frame(parent, bg=T.BG_COLOR)
        row.pack(fill="x", pady=(4, 6))

        # (icon-name, label, callback). Lock is between Sleep and Restart. Icons are the
        # same Breeze session icons Kickoff's leave buttons used, rasterised via
        # IconResolver.
        items = (
            ("system-suspend", "Sleep", self._do(actions.suspend)),
            ("system-lock-screen", "Lock", self._do(actions.lock_session)),
            ("system-reboot", "Restart", self._do(actions.reboot)),
            ("system-shutdown", "Shut Down", self._do(actions.poweroff)),
        )
        # Grid the four buttons into four EQUAL columns (weight=1 + a shared uniform
        # group forces each cell to exactly row_width/4, regardless of how wide each
        # label is -- 'Shut Down' does not get a bigger cell than 'Lock'). Each
        # PowerButton fills its cell (sticky="nsew"); its inner icon+label content uses
        # the default center anchor, so every button sits centred WITHIN ITS OWN slice.
        self.power_buttons = []
        for col, (icon_name, label, cb) in enumerate(items):
            img = self.small_icons.load(icon_name)
            row.grid_columnconfigure(col, weight=1, uniform="power")
            btn = PowerButton(row, img, label, cb)
            btn.grid(row=0, column=col, sticky="nsew")
            self.power_buttons.append(btn)

    def _do(self, fn):
        """Wrap a power action so it closes the menu, then fires the action."""
        def run() -> None:
            self.close_menu(force=True)
            fn()
        return run

    # -- power-row keyboard focus ------------------------------------------
    def _apply_power_focus(self) -> None:
        """Paint the focus outline on the currently focused power button and clear it
        from the rest."""
        for i, btn in enumerate(self.power_buttons):
            btn.set_focused(i == self._power_index)

    def _clear_power_focus(self) -> None:
        """Remove the focus outline from every power button (leaving the apps zone)."""
        for btn in self.power_buttons:
            btn.set_focused(False)

    def _move_power_focus(self, delta: int) -> None:
        """Move the focused power button left/right, clamped to the row (no wrap)."""
        if not self.power_buttons:
            return
        self._power_index = max(
            0, min(len(self.power_buttons) - 1, self._power_index + delta)
        )
        self._apply_power_focus()

    def _activate_power(self) -> None:
        """Fire the currently focused power button (Enter in the power zone)."""
        if 0 <= self._power_index < len(self.power_buttons):
            self.power_buttons[self._power_index].activate()


# --- Window assembly ------------------------------------------------------
def build_window(persistent: bool = False) -> tk.Tk:
    """Create and lay out the menu window WITHOUT entering the event loop, so it is
    unit-testable: a caller can build it, assert on it, and destroy it without ever
    calling mainloop().

    The returned root carries the AppMenu content and the close wiring; a test can
    inspect ``root.az_menu`` and the bound events.

    persistent=True switches the window into DAEMON mode: closing (outside click,
    Escape, focus loss, launching an app) HIDES the window (withdraw) instead of
    destroying it, so the resident daemon can re-show it instantly. In that mode the
    caller drives visibility with root.az_show() / root.az_hide()."""
    root = tk.Tk()
    root.title("azarch-application-menu")

    # Remove ALL window-manager chrome: no titlebar, no min/max/close buttons.
    root.overrideredirect(True)

    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()

    # CENTERED on the screen (no panel to anchor to). Clamp the top-left to >= 0 so a
    # window larger than a tiny (headless-test) screen still maps on-screen.
    win_w, win_h = menu_size()
    x = max(0, (screen_w - win_w) // 2)
    y = max(0, (screen_h - win_h) // 2)
    root.geometry(f"{win_w}x{win_h}+{x}+{y}")
    root.configure(bg=T.BG_COLOR)

    # --- close-on-outside-click, Kickoff style (NO pin) -------------------
    # The menu is a transient launcher with no pin: while open it holds a global
    # pointer grab so a click anywhere reaches on_button, and it dismisses on an outside
    # click / Escape / focus loss / a second Super press. "closed" guards teardown;
    # "capturing" records whether we hold the keyboard (the search box is live).
    state = {"closed": False, "capturing": False}
    # Pending after() timer ids, cancelled on close so no deferred callback ever runs
    # against a destroyed interpreter (which Tk would report as a spurious "invalid
    # command name ...arm_focus_out" on stderr).
    timers: list[str] = []

    def _later(ms: int, fn) -> None:
        try:
            timers.append(root.after(ms, fn))
        except tk.TclError:
            pass

    def _cancel_timers() -> None:
        for tid in timers:
            try:
                root.after_cancel(tid)
            except tk.TclError:
                pass
        timers.clear()

    def close_menu(*_a, force: bool = False) -> None:
        # `force` is accepted for call-site symmetry (launching an app / a power action
        # passes force=True). With no pin there is nothing to override, so a normal
        # dismissal and a forced one behave the same -- but keeping the flag means the
        # activate paths and the dismiss paths read identically.
        if state["closed"]:
            return
        # In PERSISTENT (daemon) mode we never destroy the window -- we just hide it so
        # the next open is instant. hide_menu() is defined below; closures resolve names
        # at call time so it is available by the time this runs.
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
        try:
            root.destroy()
        except tk.TclError:
            pass

    def on_button(event: tk.Event) -> None:
        """Global button handler: close when the press is OUTSIDE the menu."""
        x0, y0 = root.winfo_rootx(), root.winfo_rooty()
        x1, y1 = x0 + root.winfo_width(), y0 + root.winfo_height()
        inside = (x0 <= event.x_root < x1 and y0 <= event.y_root < y1)
        if not inside:
            close_menu()

    def on_focus_out(_event: tk.Event) -> None:
        """Focus genuinely left our application (the user activated another window /
        alt-tabbed). NOT fired when focus merely moves between our own widgets. Dismiss,
        exactly like Kickoff. Deferred one tick so the internal focus churn on open
        cannot self-trigger."""
        if state["closed"]:
            return

        def check() -> None:
            if state["closed"]:
                return
            try:
                focused = root.focus_displayof()
            except (tk.TclError, KeyError):
                focused = None
            if focused is not None:
                return  # focus is still on one of our own widgets -> ignore
            close_menu()

        try:
            root.after(1, check)
        except tk.TclError:
            pass

    # Build the menu content (search + app list + power row).
    menu = AppMenu(root, close_menu)
    root.az_menu = menu

    # Escape closes; arrows + Enter route through the menu's focus-aware handlers; TAB
    # flips the focus zone.
    root.bind("<Escape>", close_menu)
    # Super/Meta ALSO closes -- "Super opened it, Super closes it". The bare Super key
    # toggles the menu via xcape + the OpenBox rc.xml keybind (-> our launcher -> the
    # daemon), which works while the menu is CLOSED. But while the menu is OPEN it holds
    # a global keyboard grab (see arm()), so the second Super press is delivered to THIS
    # window and never reaches OpenBox -- the global toggle can't fire, so the menu
    # would stay open. Binding Super here makes that grab-delivered press close it,
    # closing the loop. Both Super_* (typical) and Meta_* (some layouts report the key
    # as Meta) keysyms are bound so whichever X delivers triggers the close.
    for _keysym in ("<Super_L>", "<Super_R>", "<Meta_L>", "<Meta_R>"):
        root.bind(_keysym, close_menu)
    root.bind("<Down>", lambda _e: menu.on_down())
    root.bind("<Up>", lambda _e: menu.on_up())
    root.bind("<Left>", lambda _e: menu.on_left())
    root.bind("<Right>", lambda _e: menu.on_right())
    root.bind("<Return>", lambda _e: menu.on_activate())
    root.bind("<KP_Enter>", lambda _e: menu.on_activate())
    # TAB (and Shift-TAB) flip the focus zone. Return "break" so Tk's default
    # focus-traversal does not ALSO move focus among widgets underneath us.
    root.bind("<Tab>", lambda _e: (menu.toggle_focus(), "break")[1])
    root.bind("<Shift-Tab>", lambda _e: (menu.toggle_focus(), "break")[1])
    # Some X servers deliver Shift-Tab as the ISO_Left_Tab keysym.
    root.bind("<ISO_Left_Tab>", lambda _e: (menu.toggle_focus(), "break")[1])
    root.bind_all("<Button>", on_button)

    def arm() -> None:
        """Once mapped: take the global pointer grab so clicks anywhere reach
        on_button, pull keyboard focus into the search box, and only THEN arm the
        focus-out backup (so the focus churn during open cannot self-close the menu).

        arm() is scheduled on after_idle so it fires the INSTANT the window is mapped
        (no artificial delay -- the menu must open instantly). A global grab only works
        once the window is viewable; if after_idle beat the map, reschedule ourselves a
        beat later rather than silently dropping the grab (which would leave
        clicks-outside unable to dismiss the menu)."""
        if state["closed"]:
            return
        try:
            viewable = bool(root.winfo_viewable())
        except tk.TclError:
            viewable = False
        if not viewable:
            _later(10, arm)
            return
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
        # Focus starts on the search box + app list (the default zone).
        menu.set_focus_zone(FOCUS_APPS)
        # We now hold the keyboard (the global grab): the search box is live.
        # on_focus_out clears this when focus leaves.
        state["capturing"] = True

        def arm_focus_out() -> None:
            if state["closed"]:
                return
            try:
                root.bind("<FocusOut>", on_focus_out)
            except tk.TclError:
                pass

        _later(150, arm_focus_out)

    def hide_menu() -> None:
        """DAEMON mode: hide (withdraw) the window instead of destroying it, so the next
        show is instant. Releases the grab, unbinds the focus-out backup, cancels
        timers, and marks the menu closed so stray handlers no-op while hidden."""
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
        try:
            root.withdraw()
        except tk.TclError:
            pass

    def show_menu() -> None:
        """DAEMON mode: (re)show the pre-built window instantly. Resets the menu to a
        clean state -- search cleared, list scrolled to top with the first row selected,
        focus on the search box + app list -- then maps it, raises it and arms the
        grab/focus. Because the window and all rows already exist, this is essentially
        instant (no build, no icon loading)."""
        state["closed"] = False
        state["capturing"] = False  # arm() sets this True once the keyboard is ours
        # Clean slate: clear the query (repopulates the full list in order), reset focus
        # to the default zone, and scroll back to the top.
        try:
            menu.reset_view()
        except tk.TclError:
            pass
        try:
            # Apply the centered geometry BEFORE mapping. An overrideredirect window
            # sits at X's default 0,0 (top-left) origin until positioned, and on the
            # very FIRST show it has never been mapped, so a deiconify() (MapWindow)
            # issued before the move makes X map it VISIBLY at the top-left and only then
            # slide it to center -- the 'menu flashes at the top-left on the first click'
            # bug. Positioning first means the window is only ever mapped at the correct
            # spot. (Re-shows also need this: a withdrawn override-redirect window
            # forgets its position with no WM to remember it.)
            root.geometry(f"{win_w}x{win_h}+{x}+{y}")
            root.deiconify()
            root.lift()
        except tk.TclError:
            pass
        # Arm on the next idle so the grab/focus fire the instant the window is mapped
        # (arm() reschedules itself if it beats the map).
        try:
            timers.append(root.after_idle(arm))
        except tk.TclError:
            pass

    if persistent:
        # Daemon mode: do NOT arm now. The window is built, then withdrawn by the
        # daemon; arm()/grab happen on each show_menu().
        pass
    else:
        # Fire arm() the instant the window is mapped (after_idle), not on a fixed timer
        # -- part of making the menu open instantly. arm() reschedules itself if it
        # somehow beats the map (see its viewable guard).
        try:
            timers.append(root.after_idle(arm))
        except tk.TclError:
            pass

    # Exposed for tests: the deferred-timer list and a direct close hook, so a test can
    # tear the window down cleanly (cancelling timers) instead of a bare destroy() that
    # leaves after() callbacks dangling. az_populate lets a caller/test fill the
    # (deferred) application rows explicitly. az_show/az_hide drive daemon-mode
    # visibility.
    root.az_timers = timers
    root.az_close = close_menu
    root.az_populate = menu.populate
    root.az_show = show_menu
    root.az_hide = hide_menu
    # Introspection for tests: the close/capture state dict and the focus-out handler,
    # so a test can drive the "focus left -> close" flow deterministically without
    # relying on real (flaky, headless) X focus delivery.
    root.az_state = state
    root.az_on_focus_out = on_focus_out

    return root


def main() -> None:
    """Entry point: build the window, paint it INSTANTLY, then fill the list.

    The chrome (search box, empty list, power bar) is forced on screen first -- a
    cheap, fast paint -- and only then are the application rows built (loading an icon
    each, the expensive part). So the menu window pops up instantly and the rows fill
    in a beat later, instead of the whole thing hanging off-screen until every icon has
    loaded."""
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
