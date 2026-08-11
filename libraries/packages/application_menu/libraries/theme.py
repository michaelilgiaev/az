#!/usr/bin/env python3
"""Az'arch application menu -- shared palette + geometry constants.

Pulled out of ``menu.py`` so the widget classes (``widgets.py``) and the menu
orchestrator (``menu.py``) share ONE definition of the Breeze-ish colours and
the geometry numbers. No behaviour here -- just constants.

The colours approximate the Breeze Dark colour roles so the menu reads as a
polished dark launcher rather than a raw Tk window. (KDE Plasma has been removed
from Az'arch; the desktop is now OpenBox and the menu is the whole shell -- a
borderless launcher CENTERED on the screen, opened by the Super key.)
"""

from __future__ import annotations


# --- Geometry -------------------------------------------------------------
# The menu is a fixed-size borderless window CENTERED on the screen (there is no
# panel anymore -- the old bottom-left/panel-relative placement is gone). These are
# the window's width/height; menu.py centers it via (screen - size) / 2.
DEFAULT_WIDTH = 582        # menu window width
DEFAULT_HEIGHT = 497       # menu window height


# --- Breeze-ish palette ---------------------------------------------------
BG_COLOR = "#2a2e32"       # window background
SURFACE_COLOR = "#31363b"  # slightly lighter surface (search box, buttons)
HOVER_COLOR = "#3b4045"    # row hover background
DIVIDER_COLOR = "#3a3f44"  # subtle separators between top/list/bottom
TEXT_COLOR = "#eff0f1"     # Breeze foreground (near-white) -- big app names
SUBTEXT_COLOR = "#9aa0a6"  # muted foreground -- the type subtitle
PLACEHOLDER_COLOR = "#7f858a"  # search placeholder text

# The Breeze accent blue, RGB(61,174,233) == #3daee9. Used for the selection /
# keyboard-focus outline on the app rows AND the power buttons, and the search box
# focus border.
BORDER_COLOR = "#3daee9"    # Breeze highlight blue
# Selection/hover/keyboard-focus: a rounded blue OUTLINE with a faint tinted fill
# rather than a full-bleed solid block.
SELECT_BORDER = "#3daee9"   # outline of the selected row / focused power button
SELECT_FILL = "#31383e"     # subtle fill inside a selected/hovered/focused control
SELECT_TEXT = "#ffffff"     # text on a selected row

# --- Scrollbar (arrow-less rounded pill, Plasma-Kickoff style) ------------
# A single ROUNDED (pill) slider thumb, ~6px wide, translucent light grey; NO visible
# track at rest; on hover the thumb brightens AND a faint groove fades in behind it; no
# up/down arrow buttons. Reproduced with a custom canvas widget
# (widgets.KickoffScrollBar). The colours are a light foreground (#fcfcfc) composited
# over the menu bg (#2a2e32) at the alphas the handle uses.
SCROLL_THUMB_WIDTH = 6            # px, pill thumb thickness (size hint)
SCROLL_TRACK_WIDTH = 12          # px, total column the scrollbar occupies
SCROLL_THUMB_COLOR = "#5c6166"   # rest thumb: #fcfcfc @ ~24% over #2a2e32
SCROLL_THUMB_HOVER = "#93989c"   # hover/drag thumb: #fcfcfc @ ~50% over #2a2e32
SCROLL_GROOVE_COLOR = "#33383d"  # faint groove behind thumb, hover-only
SCROLL_THUMB_MIN = 32            # px, minimum thumb length so it stays grabbable


# --- Fonts ----------------------------------------------------------------
# ONE home for the menu's text sizes so they scale together. Rounded to the nearest
# whole point because Tk font sizes are integers. The widget modules (widgets.py app
# rows + power label, applist.py canvas rows, menu.py search box) all read these
# instead of baking in their own literals, so a future resize is a one-line change
# here.
FONT_FAMILY = "Noto Sans"  # the menu's UI font throughout
FONT_APP_NAME = 13         # app-row NAME (big line)
FONT_APP_TYPE = 10         # app-row TYPE subtitle (muted line)
FONT_SEARCH = 13           # search box entry + placeholder
FONT_POWER = 12            # bottom power-row button labels

# Icon sizes.
ICON_SIZE = 44             # px, app-row icon edge
POWER_ICON_SIZE = 24       # px, bottom power-button icon edge
