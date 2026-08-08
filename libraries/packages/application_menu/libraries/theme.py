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
DEFAULT_WIDTH = 582        # menu window width (was 647; -10% -> pulled in from the right)
DEFAULT_HEIGHT = 497

APPLETSRC = os.path.expanduser(
    "~/.config/plasma-org.kde.plasma.desktop-appletsrc"
)


# --- Panel-icon highlight bar geometry ------------------------------------
# Our panel icon (org.kde.plasma.icon launching this menu) is now the LEFTMOST
# applet on the bottom panel: [Az'arch menu][task launchers...] -- Kickoff was
# removed and our icon took its slot (see configuration/desktop.py). The panel is
# bottom, full screen width, PANEL_HEIGHT px tall, so its top edge is at
# screen_h - PANEL_HEIGHT and our cell starts at the very left edge (x = 0).
ICON_CELL_X = 0                      # left edge of our (1st/leftmost) icon cell
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

# Disabled (greyed-out) control. Used by IconButton's disabled mode for the
# not-yet-working Settings (gear) button: the button shows a dimmed glyph, does
# not react to hover, and ignores clicks, so the user reads it as inactive rather
# than wondering why nothing happens. The glyph is composited toward this colour
# (a muted grey near the window bg) at DISABLED_ICON_MIX so it visibly fades.
DISABLED_ICON_COLOR = "#5c6166"  # Breeze disabled-foreground grey
DISABLED_ICON_MIX = 0.62         # 0=untouched .. 1=fully the disabled colour

# The active-applet accent colour, RGB(61,174,233) == #3daee9.
HIGHLIGHT_COLOR = "#3daee9"
BORDER_COLOR = "#3daee9"    # Breeze highlight blue
# Selection/hover: a rounded blue OUTLINE with a faint tinted fill (matches the
# Kickoff/rough-design look) rather than a full-bleed solid block.
SELECT_BORDER = "#3daee9"   # outline of the selected row
SELECT_FILL = "#31383e"     # subtle fill inside a selected/hovered row
SELECT_TEXT = "#ffffff"     # text on a selected row

# --- Scrollbar (EXACT Plasma Kickoff match) -------------------------------
# Kickoff's scrollbar (org.kde.plasma.components.ScrollBar over the Breeze
# desktop theme, verified against the theme's scrollbar.svgz + ScrollBar.qml) is:
#   * ARROW-LESS -- no up/down buttons (the QML checks for an "arrow-up" element
#     that the Breeze theme does not ship).
#   * a single ROUNDED (pill) slider thumb, ~6px wide, translucent light grey.
#   * NO visible track at rest; on hover the thumb brightens AND a faint groove
#     fades in behind it.
#   * NO separator line (Breeze lacks the private-hint-show-separator element).
# We reproduce it with a custom canvas widget (widgets.KickoffScrollBar). The
# colours below are Breeze foreground (#fcfcfc) composited over the menu bg
# (#2a2e32) at the alphas Breeze uses for the handle, so the result matches what
# Kickoff paints.
SCROLL_THUMB_WIDTH = 6            # px, pill thumb thickness (theme size hint)
SCROLL_TRACK_WIDTH = 12          # px, total column the scrollbar occupies
SCROLL_THUMB_COLOR = "#5c6166"   # rest thumb: #fcfcfc @ ~24% over #2a2e32
SCROLL_THUMB_HOVER = "#93989c"   # hover/drag thumb: #fcfcfc @ ~50% over #2a2e32
SCROLL_GROOVE_COLOR = "#33383d"  # faint groove behind thumb, hover-only
SCROLL_THUMB_MIN = 32            # px, minimum thumb length so it stays grabbable

# --- Tooltip (small hover hint) -------------------------------------------
# A tiny Breeze-ish popup shown the instant the mouse enters a control that needs
# a word of explanation -- currently the greyed-out Settings (gear) button, whose
# tooltip says the settings screen is not available yet. Dark surface with a
# subtle blue border, matching the menu.
TOOLTIP_BG = "#31363b"       # tooltip background (Breeze surface)
TOOLTIP_FG = "#eff0f1"       # tooltip text
TOOLTIP_BORDER = "#3daee9"   # thin Breeze-blue border
# Retained for compatibility; the tooltip is now INSTANT (appears on <Enter>,
# disappears on <Leave>) with no dwell delay, so nothing gates on this value.
TOOLTIP_DELAY_MS = 0         # no hover dwell -- tooltip shows immediately


# --- Fonts ----------------------------------------------------------------
# ONE home for the menu's text sizes so they scale together. These are 10%
# bigger than the original Kickoff-match sizes (12/9/12/11 pt) -- a small bump so
# the text and icons read a touch larger while the window still fits alongside
# everything else on the panel. Rounded to the nearest whole point because Tk
# font sizes are integers. The widget modules (widgets.py app rows + power label,
# applist.py canvas rows, menu.py search box) all read these instead of baking in
# their own literals, so a future resize is a one-line change here.
FONT_FAMILY = "Noto Sans"  # the menu's UI font throughout
FONT_APP_NAME = 13         # app-row NAME (big line)                -- was 12
FONT_APP_TYPE = 10         # app-row TYPE subtitle (muted line)     -- was 9
FONT_SEARCH = 13           # search box entry + placeholder         -- was 12
FONT_POWER = 12            # bottom power-row button labels         -- was 11

# Icon sizes. Bumped 10% (rounded) in step with the fonts above so the glyphs
# grow with the text rather than looking small beside the larger labels.
ICON_SIZE = 44             # px, app-row icon edge                  -- was 40
POWER_ICON_SIZE = 24       # px, bottom power-button icon edge      -- was 22
TOP_ICON_SIZE = 24         # px, top settings/pin button icon edge  -- was 22
