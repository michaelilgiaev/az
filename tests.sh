#!/usr/bin/env bash
#
# azarch -- test entry point.
#
# `bash tests.sh` is the ONE command. It is self-bootstrapping: it creates the
# venv if it is missing, installs requirements.txt into it, and runs pytest.
# No global Python packages are touched -- everything lives in ./venv (which is
# gitignored). Re-running is cheap: the venv and its installed packages persist,
# and pip is skipped entirely when requirements.txt has not changed.
#
# The tests here are PURE unit tests. They never build an ISO, never call
# pacman/makepkg/mkarchiso, never touch the network, never use sudo or Docker.
# They exercise the deterministic Python logic (the configuration-file emitters, the
# package list handling, path building, the specification pipeline's transforms) -- the
# exact code where a silent regression turns into whack-a-mole. If a test needs
# a real build tool, it does not belong here.
#
# --- OUTPUT MODES ------------------------------------------------------------
# Exactly one of three verbosity modes, chosen by a flag CONSUMED here (never
# forwarded to pytest). All three are COLORED on the terminal, all three fit an
# 80-column screen, and all three write a full color-stripped transcript to
# logs/tests.log.
#
#   (no flag)   MIXED  -- dots grouped per file. Each line is a general
#                         category (the test file's path) followed by one dot
#                         per test in it: `tests/test_paths.py ..........`.
#                         Colored (green dot pass, red F/E fail). The default.
#   -q, --quiet QUIET  -- green dots. Just the dots, nothing else to read.
#   -l, --loud  LOUD   -- an eyesore. Loudest pytest has: -vv, one bright
#                         colored line per test, full long tracebacks and the
#                         full reason report.
#
# -q and -l are mutually exclusive; passing both is a hard error.
#
# --- PASS-THROUGH ------------------------------------------------------------
# Any OTHER arguments are passed straight through to pytest (only the mode flags
# above are stripped), e.g.:
#   bash tests.sh -k pacman                # run only tests matching "pacman"
#   bash tests.sh tests/test_paths.py      # run one file
#   bash tests.sh -q -k pacman             # green dots, only "pacman" tests
#   bash tests.sh -l tests/test_emit.py    # eyesore, one file

set -o errexit
set -o nounset
set -o pipefail

REPODIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPODIR"

VENV="$REPODIR/venv"
PY="$VENV/bin/python"
REQ="$REPODIR/requirements.txt"
STAMP="$VENV/.requirements.installed"
LOGDIR="$REPODIR/logs"
LOG="$LOGDIR/tests.log"

# --- 0. Pick the output mode. -----------------------------------------------
# Walk the args ONCE: pull out the (at most one) mode flag and keep everything
# else in PYTEST_ARGS to forward. `--` ends flag parsing -- anything after it is
# forwarded verbatim. Two mode flags (e.g. `-q -l`) is a hard error, not a
# silent last-one-wins.
MODE="mixed"
MODE_FLAG_SEEN=""
PYTEST_ARGS=()
seen_ddash=0
set_mode() {                            # set_mode <name> <flag-as-typed>
    if [ -n "$MODE_FLAG_SEEN" ] && [ "$MODE" != "$1" ]; then
        echo "[tests] error: '$MODE_FLAG_SEEN' and '$2' are mutually exclusive -- pick one output mode" >&2
        exit 2
    fi
    MODE="$1"
    MODE_FLAG_SEEN="$2"
}
for arg in "$@"; do
    if [ "$seen_ddash" -eq 1 ]; then
        PYTEST_ARGS+=("$arg"); continue
    fi
    case "$arg" in
        --)              seen_ddash=1 ;;
        -q|--quiet)      set_mode quiet "$arg" ;;
        -l|--loud)       set_mode loud  "$arg" ;;
        *)               PYTEST_ARGS+=("$arg") ;;
    esac
done

# --- 1. Ensure the venv exists. ---------------------------------------------
if [ ! -x "$PY" ]; then
    echo "[tests] creating venv at $VENV"
    python3 -m venv "$VENV"
fi

# --- 2. Install requirements only when they change. -------------------------
# Stamp the venv with a hash of requirements.txt. If the file is byte-identical
# to the last successful install, skip pip entirely (pip is slow even on a
# no-op). Edit requirements.txt and the next run reinstalls automatically.
REQ_HASH=""
if [ -f "$REQ" ]; then
    REQ_HASH="$(sha256sum "$REQ" | cut -d' ' -f1)"
fi
if [ ! -f "$STAMP" ] || [ "$(cat "$STAMP" 2>/dev/null)" != "$REQ_HASH" ]; then
    echo "[tests] installing requirements"
    "$PY" -m pip install --quiet --upgrade pip
    if [ -f "$REQ" ]; then
        "$PY" -m pip install --quiet -r "$REQ"
    fi
    echo "$REQ_HASH" > "$STAMP"
fi

# --- 3. Run pytest. ----------------------------------------------------------
# PYTHONPATH exposes both Python roots so tests can import the flat compiler
# modules (compiler, paths, ...), the packages.* / modifications.* packages (the ISO
# build driver, rooted at libraries/) and the flat specification_* modules (the
# specifications pipeline, rooted at scripts/libraries/). pytest options and
# the test path live in pyproject.toml.
export PYTHONPATH="$REPODIR/libraries:$REPODIR/scripts/libraries${PYTHONPATH:+:$PYTHONPATH}"

# Do not write .pyc files. The tests import the source modules directly; a stale
# cached .pyc from an interrupted run can otherwise shadow a just-edited .py
# (same mtime) and make a test read old bytes. Compiling fresh every run costs a
# few ms on this tiny codebase and removes that whole class of confusion.
export PYTHONDONTWRITEBYTECODE=1

# Right-align the percentage and keep lines from wrapping. Below, pytest's stdout
# is a PIPE (we tee it), so pytest cannot query the terminal width and falls back
# to 80 -- long test ids then overflow and the [ NN%] column drifts. Export the
# REAL width (tput, else COLUMNS, else 80) so pytest formats to the actual screen
# exactly as it would on a bare tty.
COLS="$(tput cols 2>/dev/null || true)"
[ -n "${COLS:-}" ] || COLS="${COLUMNS:-80}"
export COLUMNS="$COLS"

# Leave a spotless tree on EXIT, however we exit (pass, fail, or Ctrl-C). Two
# kinds of scratch get wiped, both gitignored and both treated as pollution here:
#   - .pytest_cache in the rootdir (pytest's scratch). We ALSO run pytest with
#     -p no:cacheprovider (below) so it is never written in the first place; this
#     rm is the belt to that suspenders.
#   - every __pycache__ in the tree. PYTHONDONTWRITEBYTECODE=1 above stops this
#     run from writing any, but a stray one from some other tool must not survive
#     a test run either -- so sweep them all. venv/ is pruned so we don't churn
#     its thousands of cached stdlib entries (matches clear.sh).
# logs/ is NOT swept here: it is this script's own output (logs/tests.log below);
# clearing it is clear.sh's job (clear.sh -l).
cleanup() {
    rm -rf "$REPODIR/.pytest_cache"
    find "$REPODIR" -type d -name venv -prune -o -type d -name __pycache__ -exec rm -rf {} +
}
trap cleanup EXIT

# Per-mode pytest options.
#   -o addopts="" wipes the -v that pyproject bakes into addopts, so EACH mode
#      owns its own verbosity (without it every mode is stuck at -v -- one line
#      per test -- and mixed/quiet could not show grouped dots).
#   --color=yes FORCES color even though stdout is the tee pipe below.
#   -p no:cacheprovider keeps .pytest_cache from ever being written.
#   -rN (quiet/mixed) silences the trailing reason report; -rA (loud) shows all.
# These lead so a user's own -k/path in PYTEST_ARGS still applies and can override.
case "$MODE" in
    mixed)  MODE_OPTS=(-o addopts= --no-header -rN --color=yes -p no:cacheprovider) ;;  # dots per file
    quiet)  MODE_OPTS=(-o addopts= -q --no-header -rN --color=yes -p no:cacheprovider) ;;  # green dots
    loud)   MODE_OPTS=(-o addopts= -vv -rA --tb=long --color=yes -p no:cacheprovider) ;;  # eyesore
esac

# Fresh log every run: truncate logs/tests.log so it holds exactly THIS run's
# transcript (color-stripped), mirroring compile.sh which truncates logs/*.log
# per launch. mkdir -p because logs/ is gitignored and may not exist yet.
mkdir -p "$LOGDIR"
: > "$LOG"

# Hard-clip every output line to the terminal width, WITHOUT counting the color
# escapes. LOUD (-vv) prints each test's full node id, and a few parametrized
# ids here are pathological (one carries a 300+ digit number) -- a single
# unbreakable token far wider than the screen that NO pytest verbosity truncates.
# So we clip ourselves: walk each line, copy ANSI escapes verbatim (zero width)
# and keep only the first $COLUMNS VISIBLE characters, then re-emit a reset so a
# clipped color never bleeds into the next line. mixed/quiet lines are already
# within width, so this is a no-op for them -- one uniform filter guarantees ALL
# three modes fit the screen. awk is used (not `cut`, which would slice through
# an escape sequence and corrupt the color).
clip_to_width() {
    awk -v W="$COLUMNS" '
    {
        line=$0; vis=0; out=""; i=1; n=length(line)
        while (i<=n) {
            c=substr(line,i,1)
            if (c=="\033") {                       # copy a CSI escape verbatim, no width
                j=i+1
                while (j<=n && index("mGKHFABCDsu", substr(line,j,1))==0) j++
                out=out substr(line,i,j-i+1); i=j+1; continue
            }
            if (vis<W) { out=out c; vis++ }        # keep visible chars up to the width
            i++
        }
        # Re-emit a reset ONLY if we clipped mid-color (dropped visible chars past
        # the width); when nothing was dropped, pytest already closed its own SGR,
        # so adding another would just double it.
        if (vis>=W && n>0) out=out "\033[0m"
        print out
    }'
}

# The default run includes EVERYTHING, network-marked live tests included. The
# `network`-marked tests ping real external hosts and skip themselves when
# offline, so a plain `bash tests.sh` still passes without connectivity.
#
# One capture, clipped, two sinks: pytest's colored output is clipped to the
# screen width, then `tee`d to the terminal (colored) AND, via process
# substitution, into a sed that strips ANSI and appends the plain text to
# logs/tests.log. `set -o errexit` is disabled around this so a test failure does
# not abort the script before cleanup; we read pytest's TRUE exit code from
# ${PIPESTATUS[0]} (the FIRST stage -- NOT clip's / tee's / sed's) and re-raise
# it, so `bash tests.sh` still reports the real code.
set +o errexit
"$PY" -m pytest "${MODE_OPTS[@]}" "${PYTEST_ARGS[@]}" 2>&1 \
    | clip_to_width \
    | tee >(sed -E 's/\x1b\[[0-9;]*[a-zA-Z]//g' >> "$LOG")
status="${PIPESTATUS[0]}"
set -o errexit

exit "$status"
