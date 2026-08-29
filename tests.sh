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
# to 80 -- long test ids then overflow and the [ NN%] column drifts. Resolve the
# REAL width once and export it so pytest formats to the actual screen exactly as
# it would on a bare tty. Try the cheapest source that works: an already-set
# COLUMNS, else the tty via stty, else tput, else 80. Each guarded so a headless
# run (no tty) never errors under `set -o nounset`.
WIDTH="${COLUMNS:-}"
if [ -z "$WIDTH" ]; then WIDTH="$(stty size 2>/dev/null | cut -d' ' -f2)"; fi
if [ -z "$WIDTH" ]; then WIDTH="$(tput cols 2>/dev/null || true)"; fi
[ -n "$WIDTH" ] || WIDTH=80
export COLUMNS="$WIDTH"

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
    mixed)  MODE_OPTS=(-o addopts= -rN --color=yes -p no:cacheprovider) ;;  # dots per file
    quiet)  MODE_OPTS=(-o addopts= -q -rN --color=yes -p no:cacheprovider) ;;  # green dots
    loud)   MODE_OPTS=(-o addopts= -vv -rA --tb=long --color=yes -p no:cacheprovider) ;;  # eyesore
esac

# Fresh log every run: truncate logs/tests.log so it holds exactly THIS run's
# transcript (color-stripped), mirroring compile.sh which truncates logs/*.log
# per launch. mkdir -p because logs/ is gitignored and may not exist yet.
mkdir -p "$LOGDIR"
: > "$LOG"

# ALL terminal formatting in ONE awk pass. Three awk stages chained by pipes
# re-buffer between each other (libc block-buffers an awk->awk pipe even with
# fflush on the last one), which reintroduced the "frozen until the end" feel.
# A single process with one fflush() per line stays live end to end AND spawns
# fewer processes, so it is snappier too. Per line it does, in order:
#
#   1. GRAY HEADER -- pytest's environment lines are context, not result, so they
#      recede to gray (\033[90m): platform/Python/pluggy, rootdir, configfile,
#      testpaths, cachedir, plugins, and `collecting ... collected N items`.
#      Matched on the DE-COLORED text (pytest paints "collecting" bold, so the raw
#      line starts with an escape, not a letter) and anchored at line-start so a
#      test id that merely contains "rootdir" is never caught.
#
#   2. FIT TO WIDTH -- keep every line within the terminal width WITHOUT counting
#      color escapes and WITHOUT leaving a severed stub. LOUD (-vv) prints each
#      test's full node id, and a few parametrized ids here are pathological (one
#      carries a 300+ digit number): a single token far wider than the screen. A
#      blind left-clip would chop it mid-number, dropping the trailing
#      " PASSED [ NN%]" and leaving unreadable garbage. So when a line is too wide
#      we MIDDLE-truncate -- head + one ellipsis + tail on the VISIBLE text --
#      keeping a bit more tail so the PASSED/percentage always survives. Lines
#      already within width keep their bytes (and their color) untouched.
#
#   3. BLANK BEFORE SUMMARY -- put exactly one blank line above pytest's final
#      "N passed[, M skipped] in Xs" line. mixed/loud render that as a ==== rule
#      pytest already pads, so we must not double it; quiet glues the bare count to
#      the last row of dots. Rule: emit a blank first only when this IS the summary
#      and the previous emitted line was not already blank.
format_stream() {
    awk -v W="$COLUMNS" '
    function strip(s) { gsub(/\033\[[0-9;]*[a-zA-Z]/, "", s); return s }
    {
        bare = strip($0)

        # (3) one blank line before the summary, never doubled.
        if (bare ~ /(^| )[0-9]+ (passed|failed|error|errors|skipped|deselected|xfailed|xpassed).* in [0-9]/ \
            && prev_nonblank) {
            print ""
        }
        prev_nonblank = (bare != "")

        # (1) recede the environment header to gray (repaint the clean text).
        if (bare ~ /^(platform |rootdir:|configfile:|testpaths:|plugins:|cachedir:|collecting |collected )/) {
            line = "\033[90m" bare "\033[0m"; visible = bare
        } else {
            line = $0; visible = bare
        }

        # (2) fit to width: pass thru if it fits, else middle-truncate the visible
        # text (a middled line cannot keep balanced SGR, so it goes plain + reset).
        if (length(visible) <= W) {
            print line
        } else {
            keep = W - 1; head = int(keep * 0.55); tail = keep - head
            print "\033[90m" substr(visible,1,head) "\342\200\246" substr(visible, length(visible)-tail+1) "\033[0m"
        }
        fflush()
    }'
}

# The default run includes EVERYTHING, network-marked live tests included. The
# `network`-marked tests ping real external hosts and skip themselves when
# offline, so a plain `bash tests.sh` still passes without connectivity.
#
# Real-time output. pytest writes to a PIPE below (we filter + tee it), and off a
# tty it lets its stream sit in a big block buffer -- so with plain piping nothing
# appears until the run is nearly over and it FEELS frozen for the whole suite.
# Two things fix that: `python -u` unbuffers the interpreter, and `stdbuf -oL`
# forces pytest's stdout to flush per LINE, so each row of dots / each test line
# reaches the screen the instant pytest emits it. Every downstream awk/sed fflushes
# per line too, so the whole pipeline is live end to end. stdbuf is coreutils and
# effectively always present; if it is somehow missing, fall back to plain (still
# correct, just block-buffered) rather than fail.
STDBUF=(stdbuf -oL)
command -v stdbuf >/dev/null 2>&1 || STDBUF=()

# The pipeline (three stages, all line-buffered -> live end to end):
#   pytest (line-buffered stdout + unbuffered interp)  ->  format_stream (the one
#   awk that grays the header, fits each line, and spaces the summary)  ->  tee to
#   the terminal AND, via process substitution, to a sed that strips color into
#   logs/tests.log.
# `set -o errexit` is disabled around it so a test failure does not abort before
# cleanup; pytest's TRUE exit code is read from ${PIPESTATUS[0]} (the FIRST stage
# -- stdbuf execs pytest and propagates its status, so this stays pytest's own
# code, not awk's / tee's) and re-raised, so `bash tests.sh` reports it.
set +o errexit
"${STDBUF[@]}" "$PY" -u -m pytest "${MODE_OPTS[@]}" "${PYTEST_ARGS[@]}" 2>&1 \
    | format_stream \
    | tee >(sed -u -E 's/\x1b\[[0-9;]*[a-zA-Z]//g' >> "$LOG")
status="${PIPESTATUS[0]}"
set -o errexit

exit "$status"
