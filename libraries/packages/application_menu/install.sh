#!/bin/sh
# install.sh -- install the Az'arch application menu and add its PANEL ICON.
#
# Adds a dedicated icon to the bottom panel, positioned to the RIGHT of KDE's
# Application Launcher (Kickoff) and to the LEFT of LibreWolf. Clicking it opens
# our Tkinter menu ("Hello World" for now). No Super-key hijack, no Kickoff
# changes -- just our own icon.
#
# Steps:
#   1. Install menu module   -> /usr/local/lib/azarch-application-menu/menu.py
#      + panel_icon helper    -> /usr/local/lib/azarch-application-menu/panel_icon.py
#   2. Install launcher       -> /usr/local/bin/azarch-application-menu   (0755)
#   3. Install .desktop       -> /usr/local/share/applications/azarch-application-menu.desktop
#   4. Insert an org.kde.plasma.icon applet in the panel (right of Kickoff),
#      pointing at the .desktop, via panel_icon.py (backs the config up first).
#
# APPLYING THE PANEL CHANGE: Plasma reads the panel layout at shell start, so the
# new icon appears after plasmashell reloads. This script does NOT bounce
# plasmashell (doing so detached over SSH has been unreliable); LOG OUT AND BACK
# IN (or reboot) to see the icon. The config edit itself is verified before exit.
#
# Idempotent. /usr/local installs use sudo (passwordless here); the panel-config
# edit is on the per-user appletsrc.

set -eu

export LC_ALL="${LC_ALL:-C.UTF-8}"

# shellcheck disable=SC1007  # `CDPATH= cd` is an env-prefixed command, not a bad assignment
SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
LIB_SRC="$SCRIPT_DIR/libraries"

# Install destinations.
BIN_DEST="/usr/local/bin/azarch-application-menu"
LIB_DEST_DIR="/usr/local/lib/azarch-application-menu"
MENU_PY_DEST="$LIB_DEST_DIR/menu.py"
PANEL_ICON_DEST="$LIB_DEST_DIR/panel_icon.py"
DESKTOP_DEST_DIR="/usr/local/share/applications"
DESKTOP_DEST="$DESKTOP_DEST_DIR/azarch-application-menu.desktop"

# Panel config (per-user) + the panel containment id (2 = bottom panel).
APPLETSRC="$HOME/.config/plasma-org.kde.plasma.desktop-appletsrc"
PANEL_ID="2"
ICON_NAME="application-menu"
# The org.kde.plasma.icon backing .desktop (its localPath). We create this real
# Type=Application launcher ourselves so the applet does NOT bake a Type=Link/
# Icon=unknown wrapper (the "paper icon that launches nothing" bug). Per-user file.
ICON_LOCAL_PATH="$HOME/.local/share/plasma_icons/azarch-application-menu.desktop"

echo "Installing Az'arch application menu ..."

# --- 1 + 2. Program files ---------------------------------------------------
sudo install -d -m 755 "$LIB_DEST_DIR"
sudo install -m 644 "$LIB_SRC/menu.py" "$MENU_PY_DEST"
sudo install -m 644 "$LIB_SRC/panel_icon.py" "$PANEL_ICON_DEST"
sudo install -m 755 "$LIB_SRC/azarch-application-menu.sh" "$BIN_DEST"
echo "  menu module -> $MENU_PY_DEST"
echo "  launcher    -> $BIN_DEST"

# --- 3. .desktop the icon applet points at ----------------------------------
sudo install -d -m 755 "$DESKTOP_DEST_DIR"
sudo install -m 644 "$LIB_SRC/azarch-application-menu.desktop" "$DESKTOP_DEST"
echo "  .desktop    -> $DESKTOP_DEST"

# --- 4. Insert the panel icon (right of Kickoff, left of LibreWolf) ----------
if [ ! -f "$APPLETSRC" ]; then
    echo "  WARNING: panel config not found at $APPLETSRC -- skipping panel icon."
    echo "  (Run this from within the Plasma session so the panel config exists.)"
else
    cp -a "$APPLETSRC" "$APPLETSRC.azarch-menu.bak"
    python3 "$PANEL_ICON_DEST" add "$APPLETSRC" "$PANEL_ID" "$DESKTOP_DEST" \
        "$ICON_NAME" "$ICON_LOCAL_PATH" "$BIN_DEST"
    # Verify the edit landed (icon applet present + in AppletOrder). url= is written
    # as a file:// URI (bypasses the Type=Link paper-icon bug), so match that form.
    if grep -q "url=file://$DESKTOP_DEST" "$APPLETSRC"; then
        echo "  panel icon  -> inserted right of Kickoff (backup: $APPLETSRC.azarch-menu.bak)"
    else
        echo "  ERROR: panel icon insert did not take; restoring backup." >&2
        cp -a "$APPLETSRC.azarch-menu.bak" "$APPLETSRC"
        exit 1
    fi
fi

echo ""
echo "Done. LOG OUT and back in (or reboot) to see the icon on the panel."
echo "Direct test (no panel needed): AZARCH_MENU_PY=$MENU_PY_DEST $BIN_DEST"
