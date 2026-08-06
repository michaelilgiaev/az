#!/bin/sh
# azarch-application-menu -- TOGGLE the Az'arch menu.
#
# Installed to /usr/local/bin/azarch-application-menu. Run by the dedicated panel
# ICON applet (see install.sh) -- clicking the icon runs this.
#
# TOGGLE behaviour: the menu is a single instance. If it is NOT open, this opens
# it. If it IS already open, this CLOSES it (so a second left-click on the panel
# icon dismisses the menu instead of stacking another copy -- opening it multiple
# times makes no sense). State is tracked with a PID file under XDG_RUNTIME_DIR.
#
# POSIX sh. Deps: python3 + system `tk` (Tkinter) -- both on the live session.
# No pip packages, no venv.

set -eu

export LC_ALL="${LC_ALL:-C.UTF-8}"

# Installed menu module (install.sh copies libraries/menu.py here). Overridable
# via AZARCH_MENU_PY for local testing.
MENU_PY="${AZARCH_MENU_PY:-/usr/local/lib/azarch-application-menu/menu.py}"

# PID file: prefer the per-user runtime dir (already per-uid and cleared on
# logout); fall back to /tmp only if XDG_RUNTIME_DIR is unset.
RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp}"
PID_FILE="${RUNTIME_DIR}/azarch-application-menu.pid"

if [ ! -f "$MENU_PY" ]; then
    printf 'azarch-application-menu: menu module not found at %s\n' "$MENU_PY" >&2
    exit 1
fi

# --- Toggle: is a menu already open? --------------------------------------
if [ -f "$PID_FILE" ]; then
    OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [ -n "${OLD_PID:-}" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        # It's alive -> this click is the "close" click. Kill it and stop.
        kill "$OLD_PID" 2>/dev/null || true
        rm -f "$PID_FILE"
        exit 0
    fi
    # Stale PID file (process gone) -> clean up and fall through to open.
    rm -f "$PID_FILE"
fi

# --- Open a fresh instance ------------------------------------------------
# Detach so the launcher returns immediately (the panel icon does not block).
setsid python3 "$MENU_PY" >/dev/null 2>&1 < /dev/null &
MENU_PID=$!
echo "$MENU_PID" > "$PID_FILE"
