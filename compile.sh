#!/bin/bash
#
# azarch -- ISO build entrypoint (thin shim).
#
# The build itself is Python: everything (steps, staging, the package cache, the
# progress bar, the ownership handback) lives in libraries/azarch/. This shim
# only does the two things that genuinely must be bash BEFORE Python starts:
#
#   1. Prime sudo ONCE on the real controlling terminal. After the PTY re-exec
#      below there is no interactive channel, so this is the only point a password
#      prompt can reach the user. The primed credential lets the Python sudo
#      keepalive + ownership handback run `sudo -n` for the rest of the build.
#
#   2. Re-exec on a PTY via util-linux `script`. The PTY is the point: pacman/
#      mkarchiso detect a terminal and keep their live, \r-redrawn progress bars
#      (piping through plain tee makes them buffer and appear frozen for minutes
#      during big downloads), and the process being a real tty is what lets the
#      progress bar paint. `script` here writes its capture to /dev/null -- it is
#      kept ONLY for the PTY. Python (azarch.logstream) owns logs/full.log itself,
#      so the progress bar (painted to the raw terminal) never pollutes the log.
#
# Then it hands off to `python3 -m azarch.build`, which does the rest.
#
# ARGS: any args are passed straight through to the Python build driver.
#   --full-compile           build Az'arch's own packages ENTIRELY from source
#                            (incl. a multi-hour LibreWolf/Firefox compile) instead
#                            of the default, which repackages LibreWolf's verified
#                            upstream binary tarball (sha256 + PGP checked).
#   --estimate*              don't build anything -- estimate how long a build would
#                            take on THIS machine and exit. Six variants pick the
#                            tier (default vs --full-compile) and what to estimate:
#                              --estimate                            default: compute + network
#                              --estimate-only-compute               default: compute only
#                              --estimate-only-network               default: network only
#                              --estimate-full-compile               full:    compute + network
#                              --estimate-full-compile-only-compute  full:    compute only
#                              --estimate-full-compile-only-network  full:    network only
#                            The network variants run a short, timeout-bounded
#                            bandwidth probe against an Arch mirror; still no sudo.
# See azarch.build.

set -o pipefail

REPODIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGDIR="$REPODIR/logs"
FULL_LOG="$LOGDIR/full.log"
STEPS_LOG="$LOGDIR/steps.log"
mkdir -p "$LOGDIR"

# Any --estimate* variant is a pure, read-only query (no build, no privileged
# steps, no live progress bar): hand straight to Python WITHOUT priming sudo or
# re-execing on a PTY, so it runs instantly and never prompts for a password. The
# network-including variants DO open a client socket for a short bandwidth probe,
# but still need no sudo and no PTY. The `--estimate*` glob matches all six flags
# (and any future --estimate...).
for _arg in "$@"; do
    case "$_arg" in
        --estimate*)
            export PYTHONPATH="$REPODIR/libraries${PYTHONPATH:+:$PYTHONPATH}"
            exec python3 -u -m azarch.build "$@"
            ;;
    esac
done

if [ -z "$_COMPILE_LOGGING" ]; then
    export _COMPILE_LOGGING=1
    # Prime sudo once, interactively, on the real terminal (see note 1 above).
    if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
        sudo -n -v 2>/dev/null || sudo -n true 2>/dev/null || sudo -v || {
            echo "[!] sudo is required for the privileged build steps." >&2; exit 1; }
    fi
    # Truncate both logs so each launch overwrites the previous run's logs. Python
    # (azarch.logstream / azarch.progress) reopens them in append mode afterwards.
    : > "$FULL_LOG"
    : > "$STEPS_LOG"
    # Re-exec on a PTY. `script` flags: -q quiet, -e propagate child exit status,
    # -f flush after each write, -c run our command. Output goes to /dev/null:
    # `script` is kept ONLY to provide the PTY (see note 2); Python owns full.log,
    # so the progress bar's escapes/glyphs never get captured into the log.
    if command -v script >/dev/null 2>&1; then
        exec script -qefc "_COMPILE_LOGGING=1 _COMPILE_ONPTY=1 bash '${BASH_SOURCE[0]}' $*" /dev/null
    else
        # No `script` available: run without a PTY. Python still writes full.log
        # itself; child \r-progress bars degrade to plain lines but the build works.
        :
    fi
fi

# --- Under the PTY now: hand off to the Python build driver. ----------------
# PYTHONPATH points at libraries/ so `import azarch` resolves. -u = unbuffered,
# so the bar and build output interleave correctly on the PTY and in full.log.
export PYTHONPATH="$REPODIR/libraries${PYTHONPATH:+:$PYTHONPATH}"
export _COMPILE_ONPTY
exec python3 -u -m azarch.build "$@"
