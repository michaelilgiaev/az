#!/usr/bin/env python3
"""Az'arch application menu -- a borderless Tkinter panel styled like Plasma's
Kickoff (the "hamburger") menu, pinned flush to the RIGHT edge of the screen.

This is OUR application menu, a companion to KDE's Kickoff. For now its only
content is the label "Hello World"; it exists to be grown into a real menu
later. It is opened by a dedicated panel icon (see the install script).

Changes from the first version:
  * NO window chrome -- overrideredirect(True) removes the titlebar/toolbar and
    its minimize/maximize/close buttons entirely (KDE cannot decorate it).
  * Same SIZE as the live Plasma Kickoff popup (read from its popupWidth/
    popupHeight, with a sensible fallback), pinned to the bottom-RIGHT corner
    just above the bottom panel -- exactly where Kickoff itself pops up.
  * Breeze-like flat styling (dark panel background, subtle left border, light
    text) so it reads as part of the Plasma desktop rather than a raw Tk window.

It deliberately does NOT grab global input focus or force itself topmost: a
borderless override-redirect window that seizes focus fights the rest of the
desktop. Dismissal is by the panel-icon toggle (second click) or Escape.

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

# --- Breeze-ish palette ---------------------------------------------------
# Approximates the Breeze Dark "Window" role so the menu blends with Plasma.
BG_COLOR = "#2a2e32"      # window background
BORDER_COLOR = "#3daee9"  # Breeze highlight blue -- thin accent on the left edge
TEXT_COLOR = "#eff0f1"    # Breeze foreground (near-white)
BORDER_WIDTH = 2          # px of the left accent border


def build_window() -> tk.Tk:
    """Create and lay out the menu window WITHOUT entering the event loop, so it
    is unit-testable: a caller can build it, assert on it, and destroy it without
    ever calling mainloop()."""
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

    # Escape closes the menu, matching how Kickoff dismisses on Escape.
    # NOTE: deliberately NO focus_force()/global grab and NO -topmost here -- a
    # borderless override-redirect window that seizes the X input focus fights
    # the rest of the desktop (and can wedge the session). The panel-icon TOGGLE
    # in the launcher is what dismisses the menu on a second click; Escape is the
    # keyboard fallback. Closing on click-away is left to the toggle, not a
    # <FocusOut> self-destruct (which races window creation).
    root.bind("<Escape>", lambda _event: root.destroy())

    return root


def main() -> None:
    """Entry point: build the window and run the Tk event loop."""
    root = build_window()
    root.mainloop()


if __name__ == "__main__":
    main()
