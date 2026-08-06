#!/usr/bin/env python3
"""Az'arch application menu -- a minimal Tkinter window.

This is OUR application menu (right side of the screen), a companion to KDE's
Kickoff. For now its only content is the label "Hello World"; it exists to be
grown into a real menu later. It is opened by a dedicated panel icon (see the
install script), NOT by hijacking the Super key.

Kept dependency-free on purpose: Tkinter ships in the Python standard library
(backed by the system `tk` package), so nothing is pip-installed and there is
no venv to break. Runs on the live X11 Plasma session.
"""

from __future__ import annotations

import tkinter as tk


# Window geometry: a small panel pinned to the RIGHT edge of the screen, above
# the bottom panel. x/y are computed from the live screen size so it hugs the
# right edge at any resolution.
WINDOW_WIDTH = 320
WINDOW_HEIGHT = 480
EDGE_MARGIN = 12          # gap from the screen edges
PANEL_HEIGHT = 60         # Az'arch bottom panel height (configuration/desktop.py)


def build_window() -> tk.Tk:
    """Create and lay out the menu window WITHOUT entering the event loop, so it
    is unit-testable: a caller can build it, assert on it, and destroy it without
    ever calling mainloop()."""
    root = tk.Tk()
    root.title("Az'arch Menu")

    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    x = screen_w - WINDOW_WIDTH - EDGE_MARGIN
    y = screen_h - WINDOW_HEIGHT - PANEL_HEIGHT - EDGE_MARGIN
    root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+{x}+{y}")

    label = tk.Label(root, text="Hello World", font=("sans-serif", 16))
    label.pack(expand=True)

    # Escape closes the menu, matching how Kickoff dismisses on Escape.
    root.bind("<Escape>", lambda _event: root.destroy())

    return root


def main() -> None:
    """Entry point: build the window and run the Tk event loop."""
    root = build_window()
    root.mainloop()


if __name__ == "__main__":
    main()
