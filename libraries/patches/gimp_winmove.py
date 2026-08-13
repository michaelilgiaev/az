#!/usr/bin/env python3
"""Az'arch GIMP window mover -- find GIMP's main window and hide/show it (X11, no external
tools). Uses only libX11 via ctypes (python is in base; libX11 ships with X), so it needs
no xdotool/wmctrl. Two commands:

    azarch-gimp-winmove hide   HIDE GIMP's main window: nudge it off-screen (to cut the
                               on-screen flash to a clamped corner while it is still
                               painting) and then ICONIFY it, which sets
                               _NET_WM_STATE_HIDDEN and makes it vanish entirely. Because the
                               window has already painted, the later `show` is clean/instant.
                               ALSO CLOSE GIMP's "Welcome to GIMP" dialog if present (below).
    azarch-gimp-winmove show   de-iconify (map) GIMP's main window, move it on-screen, raise.

WHY ICONIFY, NOT JUST OFF-SCREEN. An off-screen move ALONE does not hide the window: OpenBox
CLAMPS a mostly-off-screen window so a corner stays on the viewport (verified -- a move to
5000,5000 lands at 1841,1055, leaving a ~79x25px GIMP corner, mascot + "File Edit", visible
on the desktop). Iconifying is the real hide. The old design relied on off-screen alone and
left that visible peek; this one iconifies AFTER the window has painted (so the un-iconify is
still clean -- the transparent-middle bug came from starting the window ICONIC/unpainted, not
from iconifying an already-drawn one).

GIMP's main image window is matched by WM_CLASS "gimp" AND a client size >= 600px wide
(GIMP also creates a tiny 10x10 GApplication helper window and dialog windows; we want the
big one; XGetGeometry still reports its size when iconified, so `show` can still find it).
Prints what it did; exit 0 even if no window is found yet (the caller polls).

THE WELCOME DIALOG. GIMP 3.2 shows a "Welcome to GIMP <ver>" dialog once after a version
update; it is a version-gated "what's new" window that (verified on the guest) `(show-
welcome-dialog no)` in gimprc does NOT suppress, and it is a SEPARATE top-level window from
the main image window, so hiding the main window leaves this dialog sitting centered on the
desktop. So `hide` also asks the WM to close any window whose _NET_WM_NAME starts with
"Welcome to GIMP" (a polite _NET_CLOSE_WINDOW client message -- verified to leave the main
GIMP process alive and healthy). Because the preload calls `hide` in a poll loop, a welcome
dialog that maps slightly after the main window is still caught and closed.
"""

import ctypes
import ctypes.util
import sys

# Off-screen anchor used ONLY to cut the on-screen flash to a small corner while GIMP is
# still painting -- it is NOT the hide mechanism (iconify is). OpenBox clamps this: a request
# to 5000,5000 lands at ~1841,1055 on a 1920x1080 screen, leaving a ~79x25px corner visible,
# which is why we ALSO iconify. Big enough to be off toward the bottom-right of any monitor.
OFFSCREEN_X = 5000
OFFSCREEN_Y = 5000
# On-screen anchor when showing (a sensible top-left-ish spot; the WM/GIMP keep it visible).
ONSCREEN_X = 120
ONSCREEN_Y = 80
# Minimum width (px) that distinguishes GIMP's real main window from its tiny helper window.
MIN_MAIN_WIDTH = 600
# GIMP's version-update "what's new" dialog titles itself "Welcome to GIMP <version>". We
# match on this prefix (case-insensitive) to close it during hide, since gimprc cannot
# suppress it. Kept broad (prefix, any version) so a GIMP point-release does not slip past.
WELCOME_TITLE_PREFIX = "welcome to gimp"


# Minimal XEvent union carrying just the XClientMessageEvent we send (_NET_CLOSE_WINDOW).
# The real XEvent is a large union; we only need the client-message view plus enough padding
# that the struct is at least as big as the real one so XSendEvent reads valid memory.
class _XClientMessageEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int), ("serial", ctypes.c_ulong), ("send_event", ctypes.c_int),
        ("display", ctypes.c_void_p), ("window", ctypes.c_ulong),
        ("message_type", ctypes.c_ulong), ("format", ctypes.c_int),
        ("data", ctypes.c_long * 5),
    ]


class _XEvent(ctypes.Union):
    _fields_ = [
        ("type", ctypes.c_int),
        ("xclient", _XClientMessageEvent),
        ("pad", ctypes.c_long * 24),   # >= sizeof(XEvent) so XSendEvent reads safely
    ]


_CLIENT_MESSAGE = 33            # X ClientMessage event type
_SUBSTRUCTURE_NOTIFY = 0x00080000
_SUBSTRUCTURE_REDIRECT = 0x00100000


class XConn:
    def __init__(self):
        name = ctypes.util.find_library("X11") or "libX11.so.6"
        self.x = ctypes.CDLL(name)
        self.x.XOpenDisplay.restype = ctypes.c_void_p
        self.x.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self.x.XInternAtom.restype = ctypes.c_ulong
        self.x.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        self.x.XGetClassHint.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p]
        self.x.XFree.argtypes = [ctypes.c_void_p]
        self.x.XFlush.argtypes = [ctypes.c_void_p]
        self.x.XMoveWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                                       ctypes.c_int, ctypes.c_int]
        self.x.XRaiseWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        # XIconifyWindow (minimize) + XMapWindow (de-minimize) -- the real hide/show. Off-
        # screen moves alone do NOT hide: OpenBox CLAMPS a mostly-off-screen window back so a
        # corner stays on-screen (verified: a move to 5000,5000 lands at 1841,1055, leaving a
        # visible GIMP corner). Iconifying sets _NET_WM_STATE_HIDDEN -- the window vanishes
        # entirely -- and mapping restores it; because we iconify only AFTER it has painted
        # fully, the restore is instant and clean (no transparent middle).
        self.x.XDefaultScreen.restype = ctypes.c_int
        self.x.XDefaultScreen.argtypes = [ctypes.c_void_p]
        self.x.XIconifyWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int]
        self.x.XMapWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self.x.XGetWindowProperty.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_long, ctypes.c_long,
            ctypes.c_int, ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.POINTER(ctypes.c_ubyte)),
        ]
        self.x.XGetGeometry.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_uint),
            ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint),
            ctypes.POINTER(ctypes.c_uint),
        ]
        # XSendEvent, used to ask the WM to close the welcome dialog (_NET_CLOSE_WINDOW).
        self.x.XSendEvent.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_long,
            ctypes.POINTER(_XEvent),
        ]
        self.dpy = self.x.XOpenDisplay(None)
        if not self.dpy:
            print("NO_DISPLAY", file=sys.stderr)
            raise SystemExit(0)
        self.root = self._default_root()
        self.screen = self.x.XDefaultScreen(self.dpy)   # for XIconifyWindow

    def _default_root(self):
        self.x.XDefaultRootWindow.restype = ctypes.c_ulong
        self.x.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        return self.x.XDefaultRootWindow(self.dpy)

    def _atom(self, name):
        return self.x.XInternAtom(self.dpy, name.encode(), False)

    def _client_list(self):
        """All managed top-level windows (_NET_CLIENT_LIST)."""
        prop = self._atom("_NET_CLIENT_LIST")
        actual_type = ctypes.c_ulong()
        actual_format = ctypes.c_int()
        nitems = ctypes.c_ulong()
        bytes_after = ctypes.c_ulong()
        data = ctypes.POINTER(ctypes.c_ubyte)()
        AnyPropertyType = 0
        status = self.x.XGetWindowProperty(
            self.dpy, self.root, prop, 0, 4096, False, AnyPropertyType,
            ctypes.byref(actual_type), ctypes.byref(actual_format),
            ctypes.byref(nitems), ctypes.byref(bytes_after), ctypes.byref(data))
        if status != 0 or not data:
            return []
        n = nitems.value
        # _NET_CLIENT_LIST is a format-32 property. Xlib returns format-32 data as an array
        # of C `long` (8 bytes each on LP64, NOT 4) -- the classic gotcha. Cast the buffer
        # to an array of c_ulong of length n rather than struct-unpacking 4-byte ints.
        arr = ctypes.cast(data, ctypes.POINTER(ctypes.c_ulong * n)).contents
        wins = [arr[i] for i in range(n)]
        self.x.XFree(ctypes.cast(data, ctypes.c_void_p))
        return wins

    def _wm_class(self, win):
        # Use void-pointer fields so we can BOTH read the C string and free the exact
        # pointer Xlib allocated (reading a c_char_p field copies+loses the pointer).
        class _ClassHint(ctypes.Structure):
            _fields_ = [("res_name", ctypes.c_void_p), ("res_class", ctypes.c_void_p)]
        hint = _ClassHint()
        if self.x.XGetClassHint(self.dpy, win, ctypes.byref(hint)) == 0:
            return ("", "")

        def _read(ptr):
            return ctypes.string_at(ptr).decode(errors="replace") if ptr else ""

        name = _read(hint.res_name)
        cls = _read(hint.res_class)
        if hint.res_name:
            self.x.XFree(hint.res_name)
        if hint.res_class:
            self.x.XFree(hint.res_class)
        return (name, cls)

    def _wm_name(self, win):
        """The window's title. Prefer _NET_WM_NAME (UTF8_STRING); the welcome dialog sets it.
        Returns "" if unset. Read via XGetWindowProperty so we get the modern EWMH title
        (WM_NAME/XFetchName is legacy Latin-1 and GTK apps may not set it)."""
        prop = self._atom("_NET_WM_NAME")
        utf8 = self._atom("UTF8_STRING")
        actual_type = ctypes.c_ulong()
        actual_format = ctypes.c_int()
        nitems = ctypes.c_ulong()
        bytes_after = ctypes.c_ulong()
        data = ctypes.POINTER(ctypes.c_ubyte)()
        status = self.x.XGetWindowProperty(
            self.dpy, win, prop, 0, 1024, False, utf8,
            ctypes.byref(actual_type), ctypes.byref(actual_format),
            ctypes.byref(nitems), ctypes.byref(bytes_after), ctypes.byref(data))
        if status != 0 or not data:
            return ""
        text = ctypes.string_at(data, nitems.value).decode("utf-8", errors="replace")
        self.x.XFree(ctypes.cast(data, ctypes.c_void_p))
        return text

    def find_welcome(self):
        """GIMP's "Welcome to GIMP <ver>" dialog window, or None. Matched by _NET_WM_NAME
        prefix (case-insensitive) AND a gimp WM_CLASS, so we never close an unrelated window."""
        for win in self._client_list():
            name, cls = self._wm_class(win)
            if "gimp" not in name.lower() and "gimp" not in cls.lower():
                continue
            if self._wm_name(win).lower().startswith(WELCOME_TITLE_PREFIX):
                return win
        return None

    def close_window(self, win):
        """Ask the WM to close `win` via a _NET_CLOSE_WINDOW client message (the same polite
        close the titlebar X button sends). Used for the welcome dialog; verified to leave the
        main GIMP process alive."""
        ev = _XEvent()
        ev.xclient.type = _CLIENT_MESSAGE
        ev.xclient.window = win
        ev.xclient.message_type = self._atom("_NET_CLOSE_WINDOW")
        ev.xclient.format = 32
        ev.xclient.data[0] = 0          # timestamp (0 = CurrentTime is fine here)
        ev.xclient.data[1] = 1          # source indication: 1 = normal application
        self.x.XSendEvent(self.dpy, self.root, False,
                          _SUBSTRUCTURE_REDIRECT | _SUBSTRUCTURE_NOTIFY, ctypes.byref(ev))

    def _width(self, win):
        root_ret = ctypes.c_ulong()
        x = ctypes.c_int(); y = ctypes.c_int()
        w = ctypes.c_uint(); h = ctypes.c_uint()
        bw = ctypes.c_uint(); depth = ctypes.c_uint()
        if self.x.XGetGeometry(self.dpy, win, ctypes.byref(root_ret),
                               ctypes.byref(x), ctypes.byref(y), ctypes.byref(w),
                               ctypes.byref(h), ctypes.byref(bw), ctypes.byref(depth)) == 0:
            return 0
        return w.value

    def find_gimp_main(self):
        """The GIMP main window: WM_CLASS name/class 'gimp'/'Gimp' AND width >= MIN_MAIN_WIDTH."""
        best = None
        best_w = 0
        for win in self._client_list():
            name, cls = self._wm_class(win)
            if "gimp" in name.lower() or "gimp" in cls.lower():
                wdt = self._width(win)
                if wdt >= MIN_MAIN_WIDTH and wdt > best_w:
                    best, best_w = win, wdt
        return best

    def move(self, win, x, y):
        self.x.XMoveWindow(self.dpy, win, x, y)

    def raise_(self, win):
        self.x.XRaiseWindow(self.dpy, win)

    def iconify(self, win):
        """Minimize the window (sets _NET_WM_STATE_HIDDEN so it vanishes entirely). We call
        this only AFTER the window has painted, so the later map()/de-iconify is clean."""
        self.x.XIconifyWindow(self.dpy, win, self.screen)

    def map_(self, win):
        """De-iconify (restore) the window. Mapping an iconified GTK window that already
        painted brings it back instantly and fully-drawn -- no transparent middle."""
        self.x.XMapWindow(self.dpy, win)

    def flush(self):
        self.x.XFlush(self.dpy)


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("hide", "show", "hide-welcome"):
        print("usage: azarch-gimp-winmove hide|show|hide-welcome", file=sys.stderr)
        raise SystemExit(2)
    cmd = sys.argv[1]
    conn = XConn()

    if cmd == "hide-welcome":
        # Close ONLY the "Welcome to GIMP" dialog (leave the main window where it is). Used by
        # the open wrapper's cold-start sweeper, where the main window is meant to stay
        # on-screen. Reports CLOSED_WELCOME if it acted so the caller's poll loop can stop.
        welcome = conn.find_welcome()
        if welcome is not None:
            conn.close_window(welcome)
            conn.flush()
            print("CLOSED_WELCOME 0x%x" % welcome)
        else:
            print("NO_WELCOME")
        raise SystemExit(0)

    if cmd == "hide":
        # Always try to close the version-update welcome dialog (gimprc can't suppress it),
        # and HIDE the main window. The welcome may map BEFORE the main window, so do not gate
        # the welcome-close on the main window existing. Report HID if we acted on EITHER, so
        # the preload's poll loop stops once the warm instance is invisible.
        #
        # Hiding = move off-screen (cuts the on-screen flash to a clamped corner while GIMP is
        # still painting) THEN iconify (the real hide: OpenBox clamps off-screen moves so a
        # corner would otherwise stay visible; iconifying sets _NET_WM_STATE_HIDDEN and the
        # window vanishes). By the time the preload calls hide the window has painted, so the
        # eventual show (de-iconify) is instant and clean.
        acted = False
        welcome = conn.find_welcome()
        if welcome is not None:
            conn.close_window(welcome)
            acted = True
            print("CLOSED_WELCOME 0x%x" % welcome)
        win = conn.find_gimp_main()
        if win is not None:
            conn.move(win, OFFSCREEN_X, OFFSCREEN_Y)
            conn.iconify(win)
            acted = True
            print("HID 0x%x" % win)
        conn.flush()
        if not acted:
            print("NO_GIMP_WINDOW")
        raise SystemExit(0)

    # show: de-iconify (map) the warm window, move it on-screen and raise it. The welcome
    # dialog (if any) was already closed during hide. Mapping an already-painted iconified
    # window restores it fully-drawn -> instant and clean.
    win = conn.find_gimp_main()
    if win is None:
        print("NO_GIMP_WINDOW")
        raise SystemExit(0)
    conn.map_(win)
    conn.move(win, ONSCREEN_X, ONSCREEN_Y)
    conn.raise_(win)
    conn.flush()
    print("SHOWED 0x%x" % win)


if __name__ == "__main__":
    main()
