#!/bin/sh
# azarch-application-menu -- TOGGLE the Az'arch menu (INSTANT, via a daemon).
#
# Installed to /usr/local/bin/azarch-application-menu. Run by the dedicated panel
# ICON applet (see install.sh) -- clicking the icon runs this.
#
# The menu runs as a resident DAEMON (menu built once, kept hidden) so opening it
# is instant -- no per-click Python/Tk startup. This launcher just signals the
# daemon:
#   * daemon already running  -> SIGUSR1 = toggle (show if hidden, hide if shown)
#   * daemon not running yet   -> start it, wait for it to be ready, SIGUSR2 = show
#
# State is the daemon's PID file under XDG_RUNTIME_DIR.
#
# POSIX sh. Deps: python3 + system `tk` (Tkinter) -- both on the live session.
# No pip packages, no venv.

set -eu

export LC_ALL="${LC_ALL:-C.UTF-8}"

# Installed daemon/menu modules. Overridable via AZARCH_MENU_DIR for local
# testing (both daemon.py and menu.py live in the same dir).
MENU_DIR="${AZARCH_MENU_DIR:-/usr/local/lib/azarch-application-menu}"
DAEMON_PY="${AZARCH_DAEMON_PY:-${MENU_DIR}/daemon.py}"

RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp}"
PID_FILE="${RUNTIME_DIR}/azarch-application-menu.pid"

if [ ! -f "$DAEMON_PY" ]; then
    printf 'azarch-application-menu: daemon module not found at %s\n' "$DAEMON_PY" >&2
    exit 1
fi

# --- Is the daemon already running? ---------------------------------------
if [ -f "$PID_FILE" ]; then
    PID="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [ -n "${PID:-}" ] && kill -0 "$PID" 2>/dev/null; then
        # Alive -> toggle it and we're done (instant show/hide inside the daemon).
        kill -USR1 "$PID" 2>/dev/null || true
        exit 0
    fi
    # Stale PID file (daemon gone) -> clean up and start a fresh one below.
    rm -f "$PID_FILE"
fi

# --- Start the daemon, then show ------------------------------------------
# Detach so the panel icon does not block. The daemon writes its own PID file
# once its window is built and ready.
setsid python3 "$DAEMON_PY" >/dev/null 2>&1 < /dev/null &

# Wait (briefly) for the daemon to come up and publish its PID file, then tell
# it to show. Poll up to ~5s in 50ms steps so a slow first start still works.
i=0
while [ "$i" -lt 100 ]; do
    if [ -f "$PID_FILE" ]; then
        PID="$(cat "$PID_FILE" 2>/dev/null || true)"
        if [ -n "${PID:-}" ] && kill -0 "$PID" 2>/dev/null; then
            kill -USR2 "$PID" 2>/dev/null || true
            exit 0
        fi
    fi
    sleep 0.05
    i=$((i + 1))
done

printf 'azarch-application-menu: daemon did not come up in time\n' >&2
exit 1
