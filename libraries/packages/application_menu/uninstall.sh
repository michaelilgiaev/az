#!/bin/sh
# uninstall.sh -- remove the Az'arch application menu and its PANEL ICON.
#
# Fully reverses install.sh:
#   1. Stop the resident daemon and remove its autostart entry.
#   2. Remove our icon applet from the panel config (and from AppletOrder).
#   3. Remove the .desktop, the launcher, the menu module + panel_icon helper.
#
# The panel returns to Kickoff / LibreWolf / Kitty / Dolphin as before. Like
# install, this does NOT bounce plasmashell: LOG OUT and back in (or reboot) for
# the icon to disappear from the running panel.
#
# Safe to run repeatedly / even if some pieces are already gone.

set -eu

export LC_ALL="${LC_ALL:-C.UTF-8}"

BIN_DEST="/usr/local/bin/azarch-application-menu"
LIB_DEST_DIR="/usr/local/lib/azarch-application-menu"
PANEL_ICON="$LIB_DEST_DIR/panel_icon.py"
DESKTOP_DEST="/usr/local/share/applications/azarch-application-menu.desktop"

AUTOSTART_DEST="$HOME/.config/autostart/azarch-application-menu-daemon.desktop"
PID_FILE="${XDG_RUNTIME_DIR:-/tmp}/azarch-application-menu.pid"

APPLETSRC="$HOME/.config/plasma-org.kde.plasma.desktop-appletsrc"
PANEL_ID="2"
# The org.kde.plasma.icon backing .desktop install.sh created (its localPath).
ICON_LOCAL_PATH="$HOME/.local/share/plasma_icons/azarch-application-menu.desktop"

echo "Uninstalling Az'arch application menu ..."

# --- 0. Stop the resident daemon + remove its autostart ---------------------
if [ -f "$PID_FILE" ]; then
    PID="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [ -n "${PID:-}" ] && kill -0 "$PID" 2>/dev/null; then
        kill -TERM "$PID" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
fi
rm -f "$AUTOSTART_DEST"
echo "  stopped daemon + removed autostart entry"

# --- 1. Remove the panel icon -----------------------------------------------
# Use the installed helper if present; otherwise fall back to the project copy.
HELPER="$PANEL_ICON"
[ -f "$HELPER" ] || HELPER="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)/libraries/panel_icon.py"
if [ -f "$APPLETSRC" ] && [ -f "$HELPER" ]; then
    cp -a "$APPLETSRC" "$APPLETSRC.azarch-menu-uninstall.bak"
    python3 "$HELPER" remove "$APPLETSRC" "$PANEL_ID"
    echo "  removed panel icon (backup: $APPLETSRC.azarch-menu-uninstall.bak)"
fi

# --- 3. Remove installed files ----------------------------------------------
sudo rm -f "$BIN_DEST" "$DESKTOP_DEST"
sudo rm -rf "$LIB_DEST_DIR"
# The per-user backing .desktop the icon applet read (not root-owned).
rm -f "$ICON_LOCAL_PATH"
echo "  removed launcher + menu module + .desktop + panel-icon backing file"

echo ""
echo "Done. LOG OUT and back in (or reboot) so the icon leaves the panel."
