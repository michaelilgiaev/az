#!/usr/bin/env python3
"""Az'arch application menu -- minimal X11 input-focus helpers (ctypes/libX11).

A single, self-contained purpose: let the PINNED menu hand the keyboard back to
whatever application the user switches to, and read which window that is.

Why this exists
---------------
Our menu window is ``overrideredirect(True)`` -- unmanaged by the window manager.
When it is pinned we keep the search box live with ``focus_force()``. But an
unmanaged window that has force-grabbed the X keyboard does NOT give it up when
the user activates another application: on kwin, neither ``<FocusOut>``, a local
``grab_set()``, ``lower()``/``withdraw()``, nor even a real Alt+Tab moves the X
input focus off it (verified on the live hypervisor). The one primitive that DOES
work is the low-level call every window manager uses to assign focus,
``XSetInputFocus`` -- reachable from pure Python via ctypes with no third-party
dependency (python-xlib is NOT required, and is not installed on the target).

So this module wraps exactly two X operations:
  * :func:`active_window` -- read ``_NET_ACTIVE_WINDOW`` off the root, i.e. which
    window the WM currently considers active. A change in this value is our
    reliable "the user switched away" signal while pinned.
  * :func:`set_input_focus` -- push the X keyboard focus onto a given window id,
    so keystrokes start going THERE (used to hand focus to the newly-active app
    when the pinned menu should stop capturing).

Everything is best-effort and crash-proof, exactly like the rest of the menu: if
libX11 is missing, the display cannot be opened, or any call fails, the functions
quietly no-op (returning 0 / doing nothing) and the menu simply keeps its old
behaviour. Standard library only.
"""

from __future__ import annotations

import ctypes
import os

# RevertTo modes / special windows from X.h.
_REVERT_TO_PARENT = 2
_ANY_PROPERTY_TYPE = 0


class _X:
    """Lazily-opened libX11 connection + the handful of bound symbols we need.

    Built once on first use and cached. If anything about loading libX11 or
    opening the display fails, ``ok`` stays False and every public helper becomes
    a no-op -- the menu must never crash because focus plumbing was unavailable."""

    _instance: "_X | None" = None

    def __init__(self) -> None:
        self.ok = False
        self.dpy = None
        try:
            xlib = ctypes.CDLL("libX11.so.6")
        except OSError:
            try:
                xlib = ctypes.CDLL("libX11.so")
            except OSError:
                return
        display = os.environ.get("DISPLAY")
        if not display:
            return

        # Signatures (only what we call).
        xlib.XOpenDisplay.restype = ctypes.c_void_p
        xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        xlib.XDefaultRootWindow.restype = ctypes.c_ulong
        xlib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        xlib.XInternAtom.restype = ctypes.c_ulong
        xlib.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        xlib.XSetInputFocus.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong
        ]
        xlib.XFlush.argtypes = [ctypes.c_void_p]
        xlib.XFree.argtypes = [ctypes.c_void_p]
        xlib.XGetWindowProperty.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong,
            ctypes.c_long, ctypes.c_long, ctypes.c_int, ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.POINTER(ctypes.c_ubyte)),
        ]

        dpy = xlib.XOpenDisplay(display.encode("ascii", "replace"))
        if not dpy:
            return
        self.xlib = xlib
        self.dpy = dpy
        self.root = xlib.XDefaultRootWindow(dpy)
        self.net_active = xlib.XInternAtom(dpy, b"_NET_ACTIVE_WINDOW", False)
        self.ok = True

    @classmethod
    def get(cls) -> "_X":
        if cls._instance is None:
            cls._instance = _X()
        return cls._instance


def active_window() -> int:
    """Return the id of the window the WM currently marks active
    (``_NET_ACTIVE_WINDOW`` on the root), or 0 if unknown/unavailable.

    A CHANGE in this value while the pinned menu holds the keyboard is our signal
    that the user switched to another application."""
    x = _X.get()
    if not x.ok:
        return 0
    actual_type = ctypes.c_ulong()
    actual_format = ctypes.c_int()
    nitems = ctypes.c_ulong()
    bytes_after = ctypes.c_ulong()
    data = ctypes.POINTER(ctypes.c_ubyte)()
    try:
        status = x.xlib.XGetWindowProperty(
            x.dpy, x.root, x.net_active, 0, 1, False, _ANY_PROPERTY_TYPE,
            ctypes.byref(actual_type), ctypes.byref(actual_format),
            ctypes.byref(nitems), ctypes.byref(bytes_after), ctypes.byref(data),
        )
    except Exception:
        return 0
    if status != 0 or not data:
        return 0
    try:
        if nitems.value < 1:
            return 0
        win = ctypes.cast(data, ctypes.POINTER(ctypes.c_ulong))[0]
    finally:
        try:
            x.xlib.XFree(data)
        except Exception:
            pass
    return int(win)


def set_input_focus(win: int) -> bool:
    """Push the X keyboard focus onto window ``win`` (so keystrokes go there),
    returning True if the call was issued. Best-effort: no-op / False if X is
    unavailable or ``win`` is falsy.

    Used to hand the keyboard to the newly-active application when a pinned menu
    should stop capturing -- the override-redirect menu will not relinquish focus
    any other way (see the module docstring)."""
    if not win:
        return False
    x = _X.get()
    if not x.ok:
        return False
    try:
        x.xlib.XSetInputFocus(x.dpy, ctypes.c_ulong(win), _REVERT_TO_PARENT, 0)
        x.xlib.XFlush(x.dpy)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    # Tiny smoke check: print the active window id (or 0 if X is unavailable).
    print("active _NET_ACTIVE_WINDOW = 0x%x" % active_window())
