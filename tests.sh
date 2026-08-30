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
# Exactly one of three verbosity modes selects what the TERMINAL shows, chosen by
# a flag CONSUMED here (never forwarded to pytest). All three are COLORED and all
# three fit the terminal width (nothing ever overflows, even a 300-digit param id).
#
#   (no flag)   MIXED  -- dots grouped per file. Each line is a general
#                         category (the test file's path) followed by one dot
#                         per test in it: `tests/test_paths.py ..........`.
#                         Colored (green dot pass, red F/E fail). The default.
#   -q, --quiet QUIET  -- green dots. Just the dots, nothing else to read.
#   -l, --loud  LOUD   -- an eyesore. Loudest pytest has: -vv, one bright
#                         colored line per test, full long tracebacks (failures
#                         reported; a clean run has no trailing PASSED wall).
#
# -q and -l are mutually exclusive; passing both is a hard error.
#
# LOGS: independent of the mode on screen, EVERY run writes all three renders to
# logs/ (color-stripped): tests.log (mixed), tests-loud.log (loud), tests-quiet.log
# (quiet). Pytest runs ONCE at -vv and every render -- terminal and all three logs
# -- is reconstructed from that single capture (keeps startup snappy: no 3x collect).
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
# Every run writes ALL THREE renders to logs/, no matter which mode the terminal
# shows: tests.log (mixed / default), tests-loud.log (loud), tests-quiet.log
# (quiet). The terminal shows only the selected mode; logs/ always gets all three.
LOG_MIXED="$LOGDIR/tests.log"
LOG_LOUD="$LOGDIR/tests-loud.log"
LOG_QUIET="$LOGDIR/tests-quiet.log"

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
# FIFODIR (set just before the run) holds the three named pipes feeding the log
# renderers; remove it too. Empty until then, so the guard is safe under nounset.
FIFODIR=""
cleanup() {
    rm -rf "$REPODIR/.pytest_cache"
    [ -n "$FIFODIR" ] && rm -rf "$FIFODIR"
    find "$REPODIR" -type d -name venv -prune -o -type d -name __pycache__ -exec rm -rf {} +
}
trap cleanup EXIT

# ONE fixed pytest invocation feeds EVERY render. pytest cannot natively produce
# all three layouts (mixed/quiet/loud need different verbosity) in a single run,
# so we run it ONCE at the RICHEST view -- `-vv`, one line per test -- and
# reconstruct the leaner mixed/quiet layouts from that stream in awk (render()
# below). One pytest process keeps startup snappy (no 3x collect) and lets every
# log + the terminal derive from the same authoritative capture.
#   -o addopts= wipes the -v pyproject bakes in (so OUR -vv is the only verbosity).
#   -vv         one bright line per test -- the source detail every render needs.
#   -rfE        trailing reason report lists ONLY failures/errors: a green run has
#               NO trailing wall of PASSED lines (that "changes when done" report,
#               and its middled huge-number ids, are gone). Failures still report.
#   --tb=long   full tracebacks (loud is an eyesore; leaner renders drop them).
#   --color=yes forces color through the pipes (stdout is not a tty below).
#   -p no:cacheprovider keeps .pytest_cache from ever being written.
# These lead so a user's own -k/path in PYTEST_ARGS still applies and can override.
PYTEST_OPTS=(-o addopts= -vv -rfE --tb=long --color=yes -p no:cacheprovider)

# Fresh logs every run: truncate all three so each holds exactly THIS run's
# transcript (color-stripped), mirroring compile.sh which truncates logs/*.log
# per launch. mkdir -p because logs/ is gitignored and may not exist yet.
mkdir -p "$LOGDIR"
: > "$LOG_MIXED"; : > "$LOG_LOUD"; : > "$LOG_QUIET"

# render <mode> -- reformat a pytest -vv stream into one of the three layouts,
# in ONE awk pass (fflush per line -> live end to end; chained awks re-buffer and
# freeze, so everything stays in this single process). -vv gives, per test, a line
#   <file>::<node> <VERDICT> [ NN%]   (VERDICT colored)
# plus a gray-able header block and a final "N passed ... in Xs" summary. Per mode:
#
#   loud  -- the -vv line VERBATIM (its color kept), just width-fitted. The eyesore.
#   mixed -- per FILE a row  "<file> ....."  : the file path (the general category)
#            in gray, then one colored glyph per test in it. Rows wrap to width.
#   quiet -- bare colored glyphs only, no labels, wrapped to width.
#
# Cross-cutting, all modes:
#   * HEADER to gray (\033[90m): platform/rootdir/configfile/testpaths/plugins/
#     cachedir/collecting/collected -- context, not result. Matched on de-colored
#     text, anchored at line start (a node id containing "rootdir" is never caught).
#   * FIT TO WIDTH by MIDDLE-truncation with an ellipsis. A -vv node id can be a
#     single unbreakable token far wider than the screen (one param id here carries
#     a 300+ digit number). A left-clip would sever the trailing " PASSED [ NN%]"
#     into garbage; middling keeps head + `…` + tail so the verdict/percentage
#     always survives. Lines that already fit keep their exact bytes and color.
#   * ONE blank line above the final "N passed ... in Xs", never doubled.
# Glyph+color mirror pytest's own dot view: PASSED/XPASS -> "." green;
# FAILED/ERROR -> "F"/"E" red; SKIPPED -> "s" yellow; XFAIL -> "x" yellow.
render() {
    awk -v W="$COLUMNS" -v MODE="$1" '
    BEGIN { GRN="\033[32m"; RED="\033[31m"; YEL="\033[33m"; GRY="\033[90m"; RST="\033[0m" }
    function strip(s) { gsub(/\033\[[0-9;]*[a-zA-Z]/, "", s); return s }
    # middle-truncate a plain string to width W (head + ellipsis + tail). Balanced
    # head/tail -- for generic lines where both ends may matter.
    function fit(v,   keep,head,tail) {
        if (length(v) <= W) return v
        keep = W - 1; head = int(keep*0.55); tail = keep - head
        return substr(v,1,head) "\342\200\246" substr(v, length(v)-tail+1)
    }
    # fit a -vv RESULT line (loud). Here the head -- "file::test_name" -- is the
    # readable part and the tail is often a pathological digit wall; keep only a
    # SHORT tail, just enough for the trailing " VERDICT [ NN%]", so the ellipsis
    # eats the garbage middle instead of showing a screenful of 9s.
    function fit_result(v,   tail,head) {
        if (length(v) <= W) return v
        tail = 14                                   # "] PASSED [ 99%]" ~ 14 visible chars
        if (tail > W - 2) tail = int(W/2)
        head = W - 1 - tail
        return substr(v,1,head) "\342\200\246" substr(v, length(v)-tail+1)
    }
    # fit a possibly-colored line: keep bytes+color if it fits, else strip+middle (gray).
    function fit_line(raw, bare) { return (length(bare) <= W) ? raw : GRY fit(bare) RST }
    # normalize a -vv header line into what the leaner (non -vv) views show:
    #   drop the " -- /path/to/python" suffix -vv tacks onto the platform line,
    #   and turn "collecting ... collected N items" into plain "collected N items".
    function norm_header(b) {
        sub(/ -- \/.*/, "", b)                      # strip the -vv python-path suffix
        sub(/^collecting \.\.\. /, "", b)           # "collecting ... collected N" -> "collected N"
        return b
    }
    # close an open dot row (mixed/quiet) with a newline before any non-dot output.
    function close_row() { if (col_open) { printf "\n"; col_open=0; cur_file=""; rowlen=0 } }
    # append one colored glyph to the wrapped dot stream.
    #   mixed -- one labeled row per file: "<file> ....."; if a file has more dots
    #            than fit the width, wrap and HANG-INDENT the continuation under the
    #            first dot (aligned to the label width) so it plainly reads as the
    #            SAME file, not an orphaned fragment.
    #   quiet -- bare glyphs, wrapped at the width, no labels.
    function put_glyph(file, glyph, color,   label) {
        if (MODE == "mixed") {
            if (file != cur_file) {                 # new category: end old row, start labeled row
                close_row()
                label = file " "
                if (length(label) >= W) label = fit(label) " "   # even the label overflows -> middle it
                printf "%s%s%s", GRY, label, RST
                rowlen = length(label); cur_file=file; col_open=1
                # hang-indent for wrapped rows = label width, but bounded so a very
                # narrow terminal still leaves room for several dots per row (never
                # an indent so wide the continuation can not fit even one dot).
                indent = length(label); if (indent > W-4) indent = (W>8) ? W-4 : 0
            }
            if (rowlen + 1 > W) { printf "\n%*s", indent, ""; rowlen=indent }  # wrap, hang-indent
            printf "%s%s%s", color, glyph, RST; rowlen++
        } else {                                    # quiet: bare glyphs, wrap at width
            if (rowlen + 1 > W) { printf "\n"; rowlen=0 }
            printf "%s%s%s", color, glyph, RST; rowlen++; col_open=1
        }
    }
    {
        bare = strip($0)

        # header block -> normalize away -vv-only noise, then gray + width-fit.
        if (bare ~ /^(platform |rootdir:|configfile:|testpaths:|plugins:|cachedir:|collecting |collected )/) {
            close_row(); print GRY fit(norm_header(bare)) RST; prev_nonblank=1

        # the "=== test session starts ===" banner: keep as-is (fit only).
        } else if (bare ~ /test session starts/) {
            close_row(); print fit_line($0,bare); prev_nonblank=1

        # a -vv per-test result line?  file::node VERDICT [ NN%]
        } else if (bare ~ /::/ && bare ~ / (PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)([ ]|$)/) {
            file = bare; sub(/::.*/, "", file)          # category = path before ::
            if      (bare ~ / PASSED/)  { g="."; c=GRN }
            else if (bare ~ / XPASS/)   { g="."; c=GRN }
            else if (bare ~ / FAILED/)  { g="F"; c=RED }
            else if (bare ~ / ERROR/)   { g="E"; c=RED }
            else if (bare ~ / SKIPPED/) { g="s"; c=YEL }
            else                        { g="x"; c=YEL }   # XFAIL
            if (MODE == "loud") {
                # loud: verbatim -vv line, but width-fit a pathological id so the
                # tail keeps the VERDICT/percentage (not a wall of digits).
                print (length(bare) <= W) ? $0 : GRY fit_result(bare) RST
            } else put_glyph(file, g, c)
            prev_nonblank=1

        # summary line -> close any open dot row, one blank above, never doubled.
        } else if (bare ~ /(^| )[0-9]+ (passed|failed|error|errors|skipped|deselected|xfailed|xpassed).* in [0-9]/) {
            close_row()
            if (prev_nonblank) print ""
            print fit_line($0, bare); prev_nonblank=(bare!="")

        # everything else (loud tracebacks, blank lines, the failure reason report).
        } else if (bare == "") {
            close_row(); print ""; prev_nonblank=0
        } else {
            close_row(); print fit_line($0, bare); prev_nonblank=1
        }
        fflush()
    }
    END { close_row() }'
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

# The pipeline. ONE pytest process, its -vv stream FANNED OUT to three log
# renderers AND the terminal (all stages line-buffered -> live end to end):
#
#   pytest (-vv) | tee <3 FIFOs> | render "$MODE"   (terminal, colored)
#        the 3 FIFOs each feed:  render <mode> | strip-color >> logs/<file>
#
# Why FIFOs + real background jobs instead of `tee >(...)` process substitutions:
# `tee` does NOT wait for its process-substitution sinks, and neither does the
# shell -- so when the terminal side of the pipe drains and the script hits
# `exit`, the log renderers can be KILLED mid-write, TRUNCATING the logs (a real,
# reproducible race, worse the larger the log). Feeding named pipes from explicit
# background jobs gives each sink a PID we can `wait` on, so every log is complete
# before we exit. The FIFO dir is wiped by the EXIT trap (FIFODIR above).
#
# pytest's TRUE exit code is ${PIPESTATUS[0]} (stdbuf execs pytest and propagates
# its status, so this is pytest's own code, not tee's / render's); errexit is off
# around the run so a failure does not abort before we read it and wait on sinks.
STRIP='s/\x1b\[[0-9;]*[a-zA-Z]//g'
FIFODIR="$(mktemp -d "${TMPDIR:-/tmp}/azarch-tests.XXXXXX")"
mkfifo "$FIFODIR/mixed" "$FIFODIR/loud" "$FIFODIR/quiet"

# Log renderers: real background jobs reading each FIFO, reformatting to their
# layout, stripping color, into the log. Capture PIDs so we can wait on them.
render mixed < "$FIFODIR/mixed" | sed -u -E "$STRIP" >> "$LOG_MIXED" & P_MIXED=$!
render loud  < "$FIFODIR/loud"  | sed -u -E "$STRIP" >> "$LOG_LOUD"  & P_LOUD=$!
render quiet < "$FIFODIR/quiet" | sed -u -E "$STRIP" >> "$LOG_QUIET" & P_QUIET=$!

set +o errexit
"${STDBUF[@]}" "$PY" -u -m pytest "${PYTEST_OPTS[@]}" "${PYTEST_ARGS[@]}" 2>&1 \
    | tee "$FIFODIR/mixed" "$FIFODIR/loud" "$FIFODIR/quiet" \
    | render "$MODE"
status="${PIPESTATUS[0]}"
wait "$P_MIXED" "$P_LOUD" "$P_QUIET"    # ensure all three logs are fully written
set -o errexit

exit "$status"
