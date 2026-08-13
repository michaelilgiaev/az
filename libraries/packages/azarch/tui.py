#!/usr/bin/env python3
"""azarch guest CLI -- the bare-`azarch` TERMINAL UI (Theme / Wallpaper / Network).

WHY THIS EXISTS. `azarch <subcommand>` is the scriptable surface, but a developer who has
never touched Linux should not have to KNOW the subcommands. Running `azarch` with no
arguments opens this full-screen text UI so the three things a fresh machine needs tuned --
the colour Theme, the desktop Wallpaper, and the Network -- are all reachable by arrow keys,
with the current status shown right there. It is meant to "get out of the way": no Az'arch
art, no branding, just a list you move through and a status you can read at a glance.

THE SHAPE (identical on every screen, so it is learned once):

    +--------------------------------------------------+
    | Search: ______                                   |  <- search box, top
    |                                                  |
    |   > Theme        dark                            |  <- rows: label + live status
    |     Wallpaper    years                           |
    |     Network      wifi on, firewall active        |
    |                                                  |
    | up/down move  enter select  esc back  / search   |  <- nav hints, bottom
    +--------------------------------------------------+

  * The Search box at the top filters the rows on the current screen (press `/` to focus it,
    type, Enter/Esc to leave it). Everything is searchable -- top-level entries and the
    actions inside each screen.
  * The rows carry LIVE STATUS pulled from the same functions the subcommands use
    (current_theme(), _current_id(), _nm_radio(), _bt_state(), the firewall status...), so
    the screen always reflects reality.
  * The bottom line always lists the keys: arrows, enter, esc, and `/`.

HOW IT APPLIES CHANGES. Selecting an action calls the SAME functions the CLI subcommands
call -- apply_theme(), apply_wallpaper(), and the network helpers. Because some of those
shell out (and may prompt for a sudo password), the UI SUSPENDS curses around every action
(_suspend_curses), runs it on the real terminal so any prompt/output is visible, then shows
a one-line result and resumes. So the TUI is a thin front-end over the existing, tested
command functions -- it adds navigation, not new system behaviour.

TESTABILITY. The whole model -- what rows a screen shows, how search filters them, and what
each action does -- lives in plain functions/data (build_menu, filter_items, the Action
list) with NO curses in them, so tests drive the menu without a tty. Only _Screen.loop and
the draw helpers touch curses, and run_tui() degrades to a clear message when there is no
terminal (so `azarch </dev/null` or a pipe does not throw).
"""

from __future__ import annotations

# BUNDLE_START


# ---------------------------------------------------------------------------
# model: an Item is one selectable row (label + live status + what it does)
# ---------------------------------------------------------------------------
class _Item:
    """One row on a screen: a label, a callable giving its live status string, and an
    action. `action` is either a screen id to descend into (str) or a zero-arg callable
    returning a human result line (an apply). `status` is a zero-arg callable (evaluated at
    draw time so it is always current) or None for rows with no status (e.g. plain actions).
    Kept as a tiny class rather than a dict purely so the attribute access reads cleanly in
    the draw loop."""

    __slots__ = ("label", "status", "action", "hint")

    def __init__(self, label, action, status=None, hint=""):
        self.label = label
        self.action = action          # str screen-id  OR  callable() -> str result
        self.status = status          # callable() -> str   OR  None
        self.hint = hint              # optional extra help shown under the row list

    def status_text(self) -> str:
        try:
            return self.status() if self.status else ""
        except Exception as exc:                     # never let a status probe crash the UI
            return f"(unavailable: {exc.__class__.__name__})"


def filter_items(items, query: str):
    """Rows whose label or status contains `query` (case-insensitive). Empty query -> all.
    This is the search box: pure function over the row list so it is unit-testable and the
    same for every screen."""
    q = query.strip().lower()
    if not q:
        return list(items)
    out = []
    for it in items:
        hay = (it.label + " " + it.status_text()).lower()
        if q in hay:
            out.append(it)
    return out


# ---------------------------------------------------------------------------
# status probes (thin wrappers over the functions the subcommands already use)
# ---------------------------------------------------------------------------
def _theme_status_line() -> str:
    return current_theme()                            # 'dark' | 'white'


def _wallpaper_status_line() -> str:
    return _current_id()                              # 'years' | 'decades' | 'custom'


def _wifi_status_line() -> str:
    if not _have("nmcli"):
        return "nmcli not found"
    radio = _nm_radio("wifi") or "unknown"
    ssid = ""
    for name, typ, _dev in _nm_field("NAME,TYPE,DEVICE", "connection", "show", "--active"):
        if "wireless" in typ:
            ssid = name
            break
    return f"radio {radio}" + (f", on {ssid}" if ssid else "")


def _wired_status_line() -> str:
    if not _have("nmcli"):
        return "nmcli not found"
    for d, t, state, _conn in _nm_field("DEVICE,TYPE,STATE,CONNECTION", "device"):
        if t == "ethernet":
            return f"{d}: {state}"
    return "no ethernet device"


def _firewall_status_line() -> str:
    """A one-word firewall state ('active'/'inactive'/...) for the row status. Reads ufw the
    same way _firewall_print_status does but returns just the state word."""
    if not _have("ufw"):
        return "ufw not found"
    rc, out = _run("sudo", "-n", "ufw", "status")
    if rc != 0:
        return "needs sudo"
    for line in out.splitlines():
        if line.lower().startswith("status:"):
            return line.split(":", 1)[1].strip() or "unknown"
    return "unknown"


def _airplane_status_line() -> str:
    return "on" if _airplane_is_on() else "off"


def _bluetooth_status_line() -> str:
    return _bt_state()


# ---------------------------------------------------------------------------
# actions (each returns a one-line human result; run with curses suspended)
# ---------------------------------------------------------------------------
def _act_theme(dark: bool):
    def run():
        apply_theme(dark)
        return f"Theme set to {'dark' if dark else 'white'}."
    return run


def _act_wallpaper(wp_id: str):
    def run():
        rc = apply_wallpaper(wp_id)
        return (f"Wallpaper set to {wp_id}." if rc == 0
                else f"Could not set wallpaper {wp_id} (see message above).")
    return run


def _act_call(fn_name, *args, ok=""):
    """Wrap a network helper (one that returns an int rc) as an action returning a result
    line. The helper is named by STRING and resolved from the module namespace AT CALL TIME
    (globals()[fn_name]) rather than captured now -- so the TUI always dispatches to the
    live command function (and a test can stub it) instead of an early-bound reference."""
    def run():
        rc = globals()[fn_name](*args)
        return ok or ("Done." if rc == 0 else "That reported an error (see above).")
    return run


# ---------------------------------------------------------------------------
# screens: the menu tree (all data -- no curses -- so it is testable)
# ---------------------------------------------------------------------------
# The wallpaper directory the spec asks to be shown on the Wallpaper screen. It is the
# same standard dir the `azarch wallpaper` command ships to (WALLPAPERS_SYSTEM_DIR from
# wallpaper.py, bundled ahead of this module).
def _wallpaper_dir() -> str:
    return WALLPAPERS_SYSTEM_DIR


def build_menu() -> dict:
    """The whole navigable tree as {screen_id: (title, [items], subtitle)}. Built fresh so
    the closures capture the live functions. 'main' is the entry screen; every other screen
    is reached by an item whose action is that screen's id."""
    screens: dict = {}

    # -- top level: the three things (Theme / Wallpaper / Network) -----------
    screens["main"] = (
        "Az'arch",
        [
            _Item("Theme", "theme", _theme_status_line),
            _Item("Wallpaper", "wallpaper", _wallpaper_status_line),
            _Item("Network", "network", _network_summary_line),
        ],
        "Configure your system. Move with the arrow keys, Enter to open.",
    )

    # -- Theme --------------------------------------------------------------
    screens["theme"] = (
        "Theme",
        [
            _Item("Dark", _act_theme(True), _theme_status_line,
                  hint="The default. Everything follows it."),
            _Item("White", _act_theme(False), _theme_status_line),
        ],
        "Current theme shown beside each choice.",
    )

    # -- Wallpaper (shows the directory path, per the spec) -----------------
    screens["wallpaper"] = (
        "Wallpaper",
        [
            _Item("Years", _act_wallpaper("years"), _wallpaper_status_line),
            _Item("Decades", _act_wallpaper("decades"), _wallpaper_status_line),
        ],
        f"Saved in: {_wallpaper_dir()}",
    )

    # -- Network (the busiest screen; each row descends or toggles) ---------
    screens["network"] = (
        "Network",
        [
            _Item("Wifi", "network.wifi", _wifi_status_line),
            _Item("Wired", "network.wired", _wired_status_line),
            _Item("Bluetooth", "network.bluetooth", _bluetooth_status_line),
            _Item("Airplane mode", "network.airplane", _airplane_status_line),
            _Item("Firewall", "network.firewall", _firewall_status_line),
        ],
        "Everything network related.",
    )

    screens["network.wifi"] = (
        "Wifi",
        [
            _Item("Turn wifi on", _act_call("_wifi_radio", True), _wifi_status_line),
            _Item("Turn wifi off", _act_call("_wifi_radio", False), _wifi_status_line),
            _Item("Scan / list networks", _act_call("_wifi_list"), _wifi_status_line),
            _Item("Disconnect", _act_call("_wifi_disconnect"), _wifi_status_line),
        ],
        "To connect to a network: azarch network wifi connect <name> <password>",
    )

    screens["network.wired"] = (
        "Wired",
        [
            _Item("Turn wired on", _act_call("_wired_toggle", True), _wired_status_line),
            _Item("Turn wired off", _act_call("_wired_toggle", False), _wired_status_line),
        ],
        "Ethernet.",
    )

    screens["network.bluetooth"] = (
        "Bluetooth",
        [
            _Item("Turn bluetooth on", _act_call("_bt_toggle", True), _bluetooth_status_line),
            _Item("Turn bluetooth off", _act_call("_bt_toggle", False), _bluetooth_status_line),
            _Item("Scan / list devices", _act_call("_bt_scan"), _bluetooth_status_line),
        ],
        "Off by default. Pair a device with: azarch network bluetooth pair <mac>",
    )

    screens["network.airplane"] = (
        "Airplane mode",
        [
            _Item("Turn airplane mode on", _act_call("_airplane_set", True),
                  _airplane_status_line, hint="Kills every radio at once."),
            _Item("Turn airplane mode off", _act_call("_airplane_set", False),
                  _airplane_status_line),
        ],
        "One switch for all radios.",
    )

    screens["network.firewall"] = (
        "Firewall",
        [
            _Item("Enable firewall", _act_call("_firewall_enable", True), _firewall_status_line),
            _Item("Disable firewall", _act_call("_firewall_enable", False), _firewall_status_line),
            _Item("List ports (with titles)", _act_call("_firewall_port", ["list"]),
                  _firewall_status_line),
        ],
        "Open/close/delete a port with: azarch network firewall port ...",
    )

    return screens


def _network_summary_line() -> str:
    """A compact one-liner for the top-level Network row: wifi + firewall at a glance."""
    bits = []
    if _have("nmcli"):
        bits.append(f"wifi {_nm_radio('wifi') or '?'}")
    bits.append(f"firewall {_firewall_status_line()}")
    if _airplane_is_on():
        bits.append("airplane on")
    return ", ".join(bits)


# ---------------------------------------------------------------------------
# curses driver (the only part that needs a terminal)
# ---------------------------------------------------------------------------
def _suspend_curses(fn):
    """Run `fn` with curses torn down so it can use the real terminal (sudo prompts, ufw
    output), then return its result. The caller re-inits the screen afterwards. Kept separate
    so actions never have to know about curses."""
    import curses
    curses.endwin()
    try:
        return fn()
    finally:
        pass


class _Screen:
    """The interactive loop over the menu tree. Holds the curses window, the current screen
    id, a per-screen selection index, and the search query. All drawing is here; the data it
    draws comes from build_menu()."""

    def __init__(self, stdscr, screens: dict):
        self.stdscr = stdscr
        self.screens = screens
        self.stack = ["main"]                 # screen-id breadcrumb (back = pop)
        self.sel = 0                          # selected visible-row index
        self.query = ""                       # search box contents
        self.searching = False                # is the search box focused
        self.message = ""                     # last action result (shown briefly)

    # -- helpers ---------------------------------------------------------
    def _cur(self):
        title, items, subtitle = self.screens[self.stack[-1]]
        return title, items, subtitle

    def _visible(self):
        _t, items, _s = self._cur()
        return filter_items(items, self.query)

    # -- drawing ---------------------------------------------------------
    def draw(self):
        import curses
        scr = self.stdscr
        scr.erase()
        h, w = scr.getmaxyx()
        title, _items, subtitle = self._cur()
        vis = self._visible()
        if self.sel >= len(vis):
            self.sel = max(0, len(vis) - 1)

        def put(y, x, text, attr=0):
            if 0 <= y < h and x < w:
                scr.addnstr(y, x, text, max(0, w - x - 1), attr)

        # breadcrumb / title (top, left) + search box (top, right)
        crumb = " / ".join(self.screens[s][0] for s in self.stack)
        put(0, 0, crumb, curses.A_BOLD)
        search_label = "Search: "
        box = self.query + ("_" if self.searching else "")
        sx = max(len(crumb) + 2, w - (len(search_label) + 24))
        put(0, sx, search_label, curses.A_DIM)
        put(0, sx + len(search_label), box,
            curses.A_REVERSE if self.searching else curses.A_UNDERLINE)
        put(1, 0, "-" * (w - 1), curses.A_DIM)

        # subtitle (context line, e.g. the wallpaper directory path)
        if subtitle:
            put(2, 0, subtitle, curses.A_DIM)

        # rows: label (left column) + live status (second column)
        top = 4
        label_w = max((len(it.label) for it in vis), default=6) + 2
        if not vis:
            put(top, 2, "(nothing matches your search)", curses.A_DIM)
        for i, it in enumerate(vis):
            y = top + i
            if y >= h - 2:
                break
            selected = (i == self.sel)
            marker = "> " if selected else "  "
            attr = curses.A_REVERSE if selected else 0
            put(y, 0, marker + it.label.ljust(label_w), attr)
            st = it.status_text()
            if st:
                put(y, 2 + label_w + 1, st,
                    (curses.A_REVERSE if selected else curses.A_DIM))

        # selected row's extra hint (just above the footer)
        if vis and 0 <= self.sel < len(vis) and vis[self.sel].hint:
            put(h - 3, 0, vis[self.sel].hint, curses.A_DIM)

        # message line (last action result) or the nav hints
        if self.message:
            put(h - 2, 0, self.message, curses.A_BOLD)
        put(h - 1, 0, self._footer(), curses.A_DIM)
        scr.refresh()

    def _footer(self) -> str:
        if self.searching:
            return "type to filter   enter/esc leave search"
        back = "esc quit" if len(self.stack) == 1 else "esc back"
        return f"up/down move   enter select   {back}   / search"

    # -- input -----------------------------------------------------------
    def loop(self):
        import curses
        while True:
            self.draw()
            ch = self.stdscr.getch()
            if self.searching:
                if not self._handle_search_key(ch):
                    return
                continue
            if ch in (curses.KEY_UP, ord("k")):
                self.sel = max(0, self.sel - 1)
                self.message = ""
            elif ch in (curses.KEY_DOWN, ord("j")):
                self.sel = min(max(0, len(self._visible()) - 1), self.sel + 1)
                self.message = ""
            elif ch == ord("/"):
                self.searching = True
            elif ch in (curses.KEY_ENTER, 10, 13, ord(" ")):
                self._activate()
            elif ch in (27,):                      # ESC
                if not self._back():
                    return
            elif ch in (ord("q"),):
                if len(self.stack) == 1:
                    return
                self._back()

    def _handle_search_key(self, ch) -> bool:
        """Handle a key while the search box is focused. Returns False only if the app
        should quit (it never does from here). Enter/Esc leave the box; Backspace edits;
        printable chars append."""
        import curses
        if ch in (curses.KEY_ENTER, 10, 13, 27):
            self.searching = False
        elif ch in (curses.KEY_BACKSPACE, 127, 8):
            self.query = self.query[:-1]
            self.sel = 0
        elif 32 <= ch < 127:
            self.query += chr(ch)
            self.sel = 0
        return True

    def _back(self) -> bool:
        """Pop one screen. Returns False when already at the top (caller then quits). A
        non-empty search is cleared first (so Esc gets you out of a filter before it leaves
        the screen)."""
        if self.query:
            self.query = ""
            self.sel = 0
            return True
        if len(self.stack) > 1:
            self.stack.pop()
            self.sel = 0
            self.query = ""
            self.message = ""
            return True
        return False

    def _activate(self):
        """Enter on the selected row: descend into a sub-screen (str action) or run an
        apply (callable action) with curses suspended, then show the result."""
        vis = self._visible()
        if not vis or not (0 <= self.sel < len(vis)):
            return
        item = vis[self.sel]
        action = item.action
        if isinstance(action, str):               # descend into a sub-screen
            if action in self.screens:
                self.stack.append(action)
                self.sel = 0
                self.query = ""
                self.message = ""
            return
        # An apply: suspend curses, run it on the real terminal, capture a result line.
        result = _suspend_curses(action)
        self._resume()
        self.message = result if isinstance(result, str) else ""

    def _resume(self):
        """Re-initialise the curses screen after an action ran with it suspended."""
        import curses
        self.stdscr.refresh()
        curses.doupdate()


def run_tui(argv=None) -> int:
    """Entry point for the bare `azarch` command: launch the full-screen TUI. Returns 0 on a
    clean exit. If there is no usable terminal (piped stdin/stdout, no TERM), it does NOT try
    to start curses -- it prints a short pointer to the subcommands and returns 0, so
    `azarch </dev/null`, a cron job, or a dumb pipe never crashes."""
    import curses
    if not _tty_ok():
        print("azarch: no interactive terminal. Use the subcommands instead, e.g.:\n"
              "  azarch theme --dark        set the theme\n"
              "  azarch wallpaper           show / set the wallpaper\n"
              "  azarch network             network status and controls\n"
              "Run `azarch --help` for the full list.")
        return 0

    def _main(stdscr):
        curses.curs_set(0)
        stdscr.keypad(True)
        screens = build_menu()
        _Screen(stdscr, screens).loop()

    try:
        curses.wrapper(_main)
    except KeyboardInterrupt:
        pass
    return 0


def _tty_ok() -> bool:
    """True when stdin AND stdout are real terminals and TERM is set -- the precondition for
    curses. Guards run_tui so a non-interactive invocation degrades gracefully."""
    return bool(sys.stdin.isatty() and sys.stdout.isatty() and os.environ.get("TERM"))
