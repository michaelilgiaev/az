#!/usr/bin/env python3
"""Az'arch GIMP window mover -- find GIMP's main window and hide/show it (X11, no external
tools). Uses only libX11 via ctypes (python is in base; libX11 ships with X), so it needs
no xdotool/wmctrl. Two commands:

    azarch-gimp-winmove hide   move GIMP's main window OFF-SCREEN (bottom-right, past the
                               viewport) -- it stays mapped so it renders fully (a clean,
                               instant reveal later), but is invisible to the user.
    azarch-gimp-winmove show   move GIMP's main window back ON-SCREEN and raise it.

GIMP's main image window is matched by WM_CLASS "gimp" AND a client size >= 600px wide
(GIMP also creates a tiny 10x10 GApplication helper window and dialog windows; we want the
big one). Prints what it did; exit 0 even if no window is found yet (the caller polls).
"""

import ctypes
import ctypes.util
import sys

# Off-screen anchor: far past a typical viewport. The WM may clamp, but to just-off-screen
# (verified on openbox: a request to 5000,5000 lands ~2228,1862 on a 1920x1080 screen --
# fully off the viewport, no peek). Big enough to be off any single monitor.
OFFSCREEN_X = 5000
OFFSCREEN_Y = 5000
# On-screen anchor when showing (a sensible top-left-ish spot; the WM/GIMP keep it visible).
ONSCREEN_X = 120
ONSCREEN_Y = 80
# Minimum width (px) that distinguishes GIMP's real main window from its tiny helper window.
MIN_MAIN_WIDTH = 600


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
        self.dpy = self.x.XOpenDisplay(None)
        if not self.dpy:
            print("NO_DISPLAY", file=sys.stderr)
            raise SystemExit(0)
        self.root = self._default_root()

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

    def flush(self):
        self.x.XFlush(self.dpy)


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("hide", "show"):
        print("usage: azarch-gimp-winmove hide|show", file=sys.stderr)
        raise SystemExit(2)
    cmd = sys.argv[1]
    conn = XConn()
    win = conn.find_gimp_main()
    if win is None:
        print("NO_GIMP_WINDOW")
        raise SystemExit(0)
    if cmd == "hide":
        conn.move(win, OFFSCREEN_X, OFFSCREEN_Y)
        conn.flush()
        print("HID 0x%x" % win)
    else:
        conn.move(win, ONSCREEN_X, ONSCREEN_Y)
        conn.raise_(win)
        conn.flush()
        print("SHOWED 0x%x" % win)


if __name__ == "__main__":
    main()
