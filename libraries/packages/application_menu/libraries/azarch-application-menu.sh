#!/bin/sh
# azarch-application-menu -- launch the Az'arch menu.
#
# Installed to /usr/local/bin/azarch-application-menu. Run by the dedicated panel
# ICON applet (see install.sh) -- clicking the icon runs this, which opens our
# Tkinter menu (libraries/menu.py, installed to /usr/local/lib/...).
#
# This first version simply OPENS the menu on each run. (Press-again-to-close
# toggle is a later, menu.py-only enhancement; it does not change this script or
# the panel wiring.)
#
# POSIX sh. Deps: python3 + system `tk` (Tkinter) -- both on the live session.
# No pip packages, no venv.

set -eu

export LC_ALL="${LC_ALL:-C.UTF-8}"

# Installed menu module (install.sh copies libraries/menu.py here). Overridable
# via AZARCH_MENU_PY for local testing.
MENU_PY="${AZARCH_MENU_PY:-/usr/local/lib/azarch-application-menu/menu.py}"

if [ ! -f "$MENU_PY" ]; then
    printf 'azarch-application-menu: menu module not found at %s\n' "$MENU_PY" >&2
    exit 1
fi

# Detach so the launcher returns immediately (the panel icon does not block).
setsid python3 "$MENU_PY" >/dev/null 2>&1 < /dev/null &
