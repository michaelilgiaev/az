#!/usr/bin/env python3
"""Az'arch application menu -- shared palette + geometry constants.

Pulled out of ``menu.py`` so the widget classes (``widgets.py``) and the menu
orchestrator (``menu.py``) share ONE definition of the Breeze-ish colours and
the panel/geometry numbers. No behaviour here -- just constants.

The colours approximate the Breeze Dark colour roles so the menu blends into the
Plasma desktop rather than reading as a raw Tk window.
"""

from __future__ import annotations

import os


# --- Geometry -------------------------------------------------------------
# Match the live Plasma Kickoff popup size and sit in the bottom-RIGHT corner
# just above the panel, mirroring where Kickoff pops up from its icon.
PANEL_HEIGHT = 60          # Az'arch bottom panel height (configuration/desktop.py)

# Fallbacks if Kickoff's size can't be read (defaults observed on this desktop:
# popupWidth=647, popupHeight=497 in plasma-org.kde.plasma.desktop-appletsrc).
DEFAULT_WIDTH = 647
DEFAULT_HEIGHT = 497

APPLETSRC = os.path.expanduser(
    "~/.config/plasma-org.kde.plasma.desktop-appletsrc"
)


# --- Panel-icon highlight bar geometry ------------------------------------
# Our panel icon (org.kde.plasma.icon launching this menu) sits SECOND from the
# left on the bottom panel: [Kickoff][Az'arch menu][task launchers...]. The
# panel is bottom, full screen width, PANEL_HEIGHT px tall, so its top edge is
# at screen_h - PANEL_HEIGHT.
ICON_CELL_X = PANEL_HEIGHT           # left edge of our (2nd) icon cell
ICON_CELL_W = PANEL_HEIGHT           # square cell, == panel thickness
HIGHLIGHT_BAR_HEIGHT = 3             # px thick when fully grown
HIGHLIGHT_BAR_INSET = 6              # px inset on each side of the cell


# --- Breeze-ish palette ---------------------------------------------------
BG_COLOR = "#2a2e32"       # window background
SURFACE_COLOR = "#31363b"  # slightly lighter surface (search box, buttons)
HOVER_COLOR = "#3b4045"    # row hover background
DIVIDER_COLOR = "#3a3f44"  # subtle separators between top/list/bottom
TEXT_COLOR = "#eff0f1"     # Breeze foreground (near-white) -- big app names
SUBTEXT_COLOR = "#9aa0a6"  # muted foreground -- the type subtitle
PLACEHOLDER_COLOR = "#7f858a"  # search placeholder text

# The active-applet accent colour, RGB(61,174,233) == #3daee9.
HIGHLIGHT_COLOR = "#3daee9"
BORDER_COLOR = "#3daee9"    # Breeze highlight blue
# Selection/hover: a rounded blue OUTLINE with a faint tinted fill (matches the
# Kickoff/rough-design look) rather than a full-bleed solid block.
SELECT_BORDER = "#3daee9"   # outline of the selected row
SELECT_FILL = "#31383e"     # subtle fill inside a selected/hovered row
SELECT_TEXT = "#ffffff"     # text on a selected row

# Icon sizes.
ICON_SIZE = 40             # px, app-row icon edge
POWER_ICON_SIZE = 22       # px, bottom power-button icon edge
TOP_ICON_SIZE = 22         # px, top settings/pin button icon edge
