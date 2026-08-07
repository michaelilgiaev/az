#!/usr/bin/env python3
"""Az'arch application menu -- a borderless Tkinter panel styled like Plasma's
Kickoff (the "hamburger") menu, pinned flush to the RIGHT edge of the screen.

This is OUR application menu, a companion to KDE's Kickoff. For now its only
content is the label "Hello World"; it exists to be grown into a real menu
later. It is opened by a dedicated panel icon (see the install script).

Behaviour (matched to Plasma's Kickoff popup):
  * NO window chrome -- overrideredirect(True) removes the titlebar/toolbar and
    its minimize/maximize/close buttons entirely (KDE cannot decorate it).
  * Same SIZE as the live Plasma Kickoff popup (read from its popupWidth/
    popupHeight, with a sensible fallback), pinned to the bottom-RIGHT corner
    just above the bottom panel -- exactly where Kickoff itself pops up.
  * Breeze-like flat styling (dark panel background, subtle left border, light
    text) so it reads as part of the Plasma desktop rather than a raw Tk window.
  * CLOSES ON ANY CLICK OUTSIDE ITSELF, exactly like Plasma's Kickoff: pressing
    a mouse button anywhere off the menu (desktop, another window, the panel)
    dismisses it. This is done with a GLOBAL pointer grab (grab_set_global) plus
    a hit-test against the window bounds, backed up by <FocusOut> and Escape --
    the standard, session-safe way an X11 override-redirect popup dismisses. The
    grab is always released on close, so it can never wedge the session (probed
    live on the Plasma 6.7 VM: grab_set_global returns OK and plasmashell keeps
    running).
  * HIGHLIGHT BAR over the panel icon, like Plasma's Kickoff: when the menu
    opens, a thin Breeze-blue (#3daee9) accent bar POPS IN at full size across
    the TOP edge of our panel-icon cell (no animation), and vanishes when the
    menu closes. Plasma draws this "active applet" indicator for its
    own expandable applets; our launcher icon is the generic (compiled) plasma
    icon applet, which has no such state, so the menu paints the bar itself.

Kept dependency-free on purpose: Tkinter ships in the Python standard library
(backed by the system `tk` package). Runs on the live X11 Plasma session.
"""

from __future__ import annotations

import os
import re
import tkinter as tk


# --- Geometry -------------------------------------------------------------
# Match the live Plasma Kickoff popup size and sit in the bottom-RIGHT corner
# just above the panel, mirroring where Kickoff pops up from its icon.
PANEL_HEIGHT = 60         # Az'arch bottom panel height (configuration/desktop.py)

# Fallbacks if Kickoff's size can't be read (defaults observed on this desktop:
# popupWidth=647, popupHeight=497 in plasma-org.kde.plasma.desktop-appletsrc).
DEFAULT_WIDTH = 647
DEFAULT_HEIGHT = 497

_APPLETSRC = os.path.expanduser(
    "~/.config/plasma-org.kde.plasma.desktop-appletsrc"
)


def kickoff_popup_size() -> tuple[int, int]:
    """Return (width, height) of the live Kickoff popup, read from Plasma's
    appletsrc (popupWidth / popupHeight). Falls back to DEFAULT_* if the file or
    keys are absent, so the menu still matches Kickoff's default footprint."""
    w = h = None
    try:
        with open(_APPLETSRC, encoding="utf-8") as fh:
            for ln in fh:
                m = re.match(r"popupWidth=(\d+)", ln)
                if m:
                    w = int(m.group(1))
                m = re.match(r"popupHeight=(\d+)", ln)
                if m:
                    h = int(m.group(1))
    except OSError:
        pass
    return (w or DEFAULT_WIDTH, h or DEFAULT_HEIGHT)


# --- Panel-icon highlight bar geometry ------------------------------------
# Our panel icon (org.kde.plasma.icon launching this menu) sits SECOND from the
# left on the bottom panel: [Kickoff][Az'arch menu][task launchers...]. The
# panel is `location=4` (bottom), full screen width, PANEL_HEIGHT px tall, so
# its top edge is at screen_h - PANEL_HEIGHT.
#
# The icon CELL is a PANEL_HEIGHT-square (Plasma sizes panel icon cells to the
# panel thickness). Measured live (ffmpeg x11grab of the panel, glyph-column
# analysis): Kickoff glyph centered at x=33, our glyph at x=89 -- one cell
# (~PANEL_HEIGHT) to the right. So our cell starts at ICON_CELL_X and spans
# ICON_CELL_W. These are only used to POSITION the cosmetic highlight bar; being
# a few px off just nudges the accent stripe, it does not affect the menu.
ICON_CELL_X = PANEL_HEIGHT          # left edge of our (2nd) icon cell
ICON_CELL_W = PANEL_HEIGHT          # square cell, == panel thickness

# The accent bar itself: a thin horizontal Breeze-blue stripe hugging the TOP
# edge of the icon cell (the edge facing the desktop), like Plasma's active
# indicator. Height and a small horizontal inset so it reads as a centered bar.
HIGHLIGHT_BAR_HEIGHT = 3            # px thick when fully grown
HIGHLIGHT_BAR_INSET = 6            # px inset on each side of the cell


# --- Breeze-ish palette ---------------------------------------------------
# Approximates the Breeze Dark "Window" role so the menu blends with Plasma.
BG_COLOR = "#2a2e32"      # window background
BORDER_COLOR = "#3daee9"  # Breeze highlight blue -- thin accent on the left edge
TEXT_COLOR = "#eff0f1"    # Breeze foreground (near-white)
BORDER_WIDTH = 2          # px of the left accent border

# The active-applet accent color, RGB(61,174,233) == #3daee9. Read live from the
# Breeze Dark scheme (Colors:Selection BackgroundNormal / DecorationFocus /
# DecorationHover are all 61,174,233) -- the exact "cyan-ish" bar Plasma paints.
HIGHLIGHT_COLOR = "#3daee9"


# --- Highlight bar over the panel icon ------------------------------------
class HighlightBar:
    """A borderless Breeze-blue accent stripe that POPS IN at full size over the
    panel icon while the menu is open (mirroring Plasma's "active applet"
    indicator), and is torn down when the menu closes.

    No animation on purpose: the bar appears instantly at its full width when
    show() is called and disappears on close(). It is a child Toplevel of the
    menu's root so it shares the Tk event loop and dies with the root
    automatically; close() is idempotent."""

    def __init__(self, root: tk.Tk, screen_w: int, screen_h: int) -> None:
        self._root = root

        # Full bar geometry, clamped to the screen so it is always visible.
        full_w = max(1, ICON_CELL_W - 2 * HIGHLIGHT_BAR_INSET)
        cell_left = ICON_CELL_X + HIGHLIGHT_BAR_INSET
        self._w = min(full_w, screen_w)
        self._x = cell_left
        # Top edge of the panel; the bar hugs the panel's desktop-facing edge.
        self._y = screen_h - PANEL_HEIGHT

        win = tk.Toplevel(root)
        win.overrideredirect(True)
        win.configure(bg=HIGHLIGHT_COLOR)
        # Sit above normal windows so the accent is not hidden by the panel.
        try:
            win.attributes("-topmost", True)
        except tk.TclError:
            pass
        # Withdraw until show() so it never flashes at the wrong spot on build.
        win.withdraw()
        self._win = win

    def show(self) -> None:
        """Pop the bar in at full size, instantly (no animation)."""
        if not self._alive():
            return
        self._win.geometry(
            f"{self._w}x{HIGHLIGHT_BAR_HEIGHT}+{self._x}+{self._y}"
        )
        self._win.deiconify()

    def _alive(self) -> bool:
        try:
            return bool(self._win.winfo_exists())
        except tk.TclError:
            return False

    def close(self) -> None:
        """Destroy the bar. Idempotent -- safe to call from the menu's close path
        more than once."""
        try:
            self._win.destroy()
        except tk.TclError:
            pass


def build_window() -> tk.Tk:
    """Create and lay out the menu window WITHOUT entering the event loop, so it
    is unit-testable: a caller can build it, assert on it, and destroy it without
    ever calling mainloop().

    The returned root carries the highlight bar and the close wiring already
    attached; a test can inspect `root.az_highlight` and the bound events."""
    root = tk.Tk()
    root.title("Az'arch Menu")

    # Remove ALL window-manager chrome: no titlebar, no min/max/close buttons.
    # This is what makes it look like a menu panel instead of an app window.
    root.overrideredirect(True)

    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()

    # Same footprint as the live Kickoff popup, pinned to the bottom-RIGHT
    # corner sitting just above the bottom panel (flush to the right edge).
    win_w, win_h = kickoff_popup_size()
    x = screen_w - win_w                      # flush right, no margin
    y = screen_h - PANEL_HEIGHT - win_h       # bottom, resting on the panel
    root.geometry(f"{win_w}x{win_h}+{x}+{y}")

    root.configure(bg=BORDER_COLOR)

    # Inner frame inset by BORDER_WIDTH on the LEFT only -> a thin accent stripe
    # down the left edge (the side facing the desktop), Breeze-panel style.
    inner = tk.Frame(root, bg=BG_COLOR)
    inner.pack(fill="both", expand=True, padx=(BORDER_WIDTH, 0), pady=0)

    label = tk.Label(
        inner, text="Hello World", font=("Noto Sans", 16),
        bg=BG_COLOR, fg=TEXT_COLOR,
    )
    label.pack(expand=True)

    # --- Close-on-outside-click, Plasma-Kickoff style ---------------------
    # Close exactly once (destroying the root also destroys the highlight bar via
    # its parent link; guard so the grab release / bar close run a single time).
    state = {"closed": False}

    def close_menu(*_a) -> None:
        if state["closed"]:
            return
        state["closed"] = True
        # Release the global pointer grab BEFORE tearing down, so input returns
        # to the desktop cleanly (never leave the session grabbed).
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
        """Global button handler: close when the press is OUTSIDE the menu,
        otherwise let it through (so clicks on the menu still work)."""
        x0, y0 = root.winfo_rootx(), root.winfo_rooty()
        x1, y1 = x0 + root.winfo_width(), y0 + root.winfo_height()
        inside = (x0 <= event.x_root < x1 and y0 <= event.y_root < y1)
        if not inside:
            close_menu()

    # Escape closes the menu, matching how Kickoff dismisses on Escape.
    root.bind("<Escape>", close_menu)
    # Any mouse press anywhere (global grab feeds every press here) -> hit-test.
    root.bind_all("<Button>", on_button)
    # Focus leaving the menu (user activated another window) -> close, like a
    # real popup. Backs up the grab for focus-stealing surfaces.
    root.bind("<FocusOut>", close_menu)

    def arm() -> None:
        """Once mapped: take the global pointer grab so clicks anywhere reach
        on_button, pull keyboard focus for Escape, and pop in the icon
        highlight bar. Deferred via `after` so the window exists first (a grab
        before map is a no-op / race)."""
        if state["closed"]:
            return
        try:
            root.grab_set_global()
        except tk.TclError:
            # If the global grab is refused, <FocusOut> + Escape still dismiss.
            pass
        try:
            root.focus_force()
        except tk.TclError:
            pass
        bar = getattr(root, "az_highlight", None)
        if bar is not None:
            bar.show()

    # Build the animated highlight bar and stash it on the root so main()/tests
    # can reach it and the close path can tear it down.
    root.az_highlight = HighlightBar(root, screen_w, screen_h)
    # Arm the grab + animation shortly after the loop starts (window is mapped).
    root.after(30, arm)

    return root


def main() -> None:
    """Entry point: build the window and run the Tk event loop."""
    root = build_window()
    root.mainloop()


if __name__ == "__main__":
    main()
