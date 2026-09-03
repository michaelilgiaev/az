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
# LOGS: independent of the mode on screen, EVERY run writes all three views to
# logs/ (color-stripped): tests.log (mixed), tests-loud.log (loud), tests-quiet.log
# (quiet). Each view is produced by its OWN native pytest run: the TERMINAL run (the
# selected mode) writes its own log as it prints, and the OTHER TWO modes each run
# in a throwaway COPY of the repo, concurrently, feeding their logs. Native-per-mode
# means pytest emits exactly the right layout for each view, so no `-vv` artifact
# (wrapped skip reasons, digit walls) ever leaks into the leaner mixed/quiet views.
# A small awk only fits lines to the terminal WIDTH; it never reconstructs dots.
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
# Every run writes ALL THREE views to logs/, no matter which mode the terminal
# shows: tests.log (mixed / default), tests-loud.log (loud), tests-quiet.log
# (quiet). The terminal shows only the selected mode; logs/ always gets all three
# (the shown mode from the terminal run, the other two from isolated copies).
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
    # pip runs quiet so a clean install stays silent, but a FAILING install must
    # not vanish: capture its output and dump it before exiting non-zero. A bare
    # `--quiet` swallows the real error (a yanked wheel, a version that dropped
    # support for this Python), leaving CI with just "exit code 1" and nothing to
    # diagnose. `pip_install` prints the captured log only on failure.
    pip_install() {
        local log
        log="$("$PY" -m pip install --quiet "$@" 2>&1)"
        local rc=$?
        if [ "$rc" -ne 0 ]; then
            echo "[tests] pip install failed (exit $rc):" >&2
            printf '%s\n' "$log" >&2
        fi
        return "$rc"
    }
    pip_install --upgrade pip
    if [ -f "$REQ" ]; then
        pip_install -r "$REQ"
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
# COLUMNS, else the tty via stty, else tput, else 80. Each source is guarded so a
# headless run (no tty) never aborts the script: `nounset` is satisfied by the
# `${COLUMNS:-}` default, and -- because `set -o pipefail` propagates a pipe's
# failure and `errexit` would then kill us -- the stty/tput calls (which fail off
# a tty) each swallow their own non-zero status (`|| true`) so the pipeline stays
# zero and we simply fall through to the next source, ending at 80.
WIDTH="${COLUMNS:-}"
if [ -z "$WIDTH" ]; then WIDTH="$( { stty size 2>/dev/null || true; } | cut -d' ' -f2)"; fi
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
# The two off-screen log runs are children of this shell, each working inside a
# throwaway repo COPY under /tmp. On any exit (pass, fail, Ctrl-C) the trap kills
# any still-running child and removes every copy so nothing lingers after we go.
cleanup() {
    rm -rf "$REPODIR/.pytest_cache"
    kill "$P_LOG1" "$P_LOG2" 2>/dev/null || true
    for d in "${LOGCOPIES[@]}"; do [ -n "$d" ] && rm -rf "$d"; done
    find "$REPODIR" -type d -name venv -prune -o -type d -name __pycache__ -exec rm -rf {} +
}
# P_* are the off-screen log PIDs and LOGCOPIES the temp copy dirs, all set just
# before the run. Default them empty/empty-array so the trap is safe under nounset
# if we exit before they are populated.
P_LOG1=""; P_LOG2=""
LOGCOPIES=()
trap cleanup EXIT

# --- Per-mode pytest options -------------------------------------------------
# Each output mode runs pytest in its OWN native verbosity, so pytest emits the
# right layout directly -- no reconstruction, so no `-vv` artifact (wrapped skip
# reasons, digit walls) can leak into the leaner views.
#   -o addopts= wipes the -v pyproject bakes in, so OUR verbosity is the only one.
#   --color=yes forces color through the pipe (stdout is not a tty below).
#   -p no:cacheprovider keeps .pytest_cache from ever being written.
# Mode-specific:
#   mixed -> -ra              : pytest's own per-file grouped dots
#            (`tests/test_x.py .....`), gray-able header, short summary. The file
#            label prints in the terminal's default fg (white); dots green. Default.
#   quiet -> -q              : bare dots only, `s`/`F` inline. `-q` never prints an
#            inline skip REASON, so long reasons cannot wrap into junk lines.
#   loud  -> -vv -rfE --tb=long : one bright line per test, failures reported, full
#            tracebacks. The eyesore.
# These lead so a user's own -k/path in PYTEST_ARGS still applies and can override.
opts_for_mode() {                          # opts_for_mode <mode> -> echoes flags
    case "$1" in
        quiet) echo "-o addopts= -q --color=yes -p no:cacheprovider" ;;
        loud)  echo "-o addopts= -vv -rfE --tb=long --color=yes -p no:cacheprovider" ;;
        *)     echo "-o addopts= -ra --color=yes -p no:cacheprovider" ;;   # mixed
    esac
}

# Fresh logs every run: truncate all three so each holds exactly THIS run's
# transcript (color-stripped), mirroring compile.sh which truncates logs/*.log
# per launch. mkdir -p because logs/ is gitignored and may not exist yet.
mkdir -p "$LOGDIR"
: > "$LOG_MIXED"; : > "$LOG_LOUD"; : > "$LOG_QUIET"

# fit <mode> -- reformat a NATIVE pytest stream to the terminal WIDTH, in ONE awk
# pass (fflush per line -> live end to end). This is the ONLY reformatting: pytest
# already produced the correct layout for the mode, so awk never reconstructs dots.
# It does exactly three things, all width/color cosmetics:
#   * HEADER block (platform/rootdir:/configfile:/testpaths:/plugins:/collected ...)
#     -> gray. Context, not result. Anchored at line start on de-colored text so a
#     node id that merely CONTAINS "rootdir" is never caught. (The mixed per-file
#     LABEL is NOT a header line, so it keeps pytest's default white fg.)
#   * A per-test `::...VERDICT [ NN%]` line wider than the screen (loud, where a
#     param id can be a 500-char digit wall pytest does not truncate): cut at the
#     `[` that opens the param id, insert an ellipsis, keep the trailing
#     ` VERDICT [ NN%]`. The unreadable digits are DROPPED, not sampled. If the id
#     has no `[` (a long plain node name), fall back to a generic middle-truncate
#     that still preserves the tail verdict.
#   * Any OTHER over-wide line (a long traceback line, a wide summary) -> generic
#     middle-truncate (head + ellipsis + tail) so both ends survive.
# Lines that already fit keep their exact bytes and color. Blank lines and pytest's
# own spacing pass through untouched -- no synthesized or collapsed blanks.
fit() {
    awk -v W="$COLUMNS" '
    BEGIN { GRY="\033[90m"; RST="\033[0m" }
    function strip(s) { gsub(/\033\[[0-9;]*[a-zA-Z]/, "", s); return s }
    # generic middle-truncate of a PLAIN string to width W (head + ellipsis + tail).
    function mid(v,   keep,head,tail) {
        if (length(v) <= W) return v
        keep = W - 1; head = int(keep*0.55); tail = keep - head
        return substr(v,1,head) "\342\200\246" substr(v, length(v)-tail+1)
    }
    # a possibly-colored line: keep bytes+color if it fits, else strip+middle (gray).
    function fit_line(raw, bare) { return (length(bare) <= W) ? raw : GRY mid(bare) RST }
    # fit an over-wide per-test RESULT line by cutting at the param-id `[`. bare is
    # the de-colored text, shaped "file::name[HUGE_ID] VERDICT [ NN%]". Keep
    # everything up to and including "name[", an ellipsis, then the trailing
    # " VERDICT [ NN%]" -- anchored on the VERDICT WORD (from the space just before
    # it), so both the verdict and the percentage survive and the whole unreadable
    # id is DROPPED, not sampled. No `[` (a long plain node name) -> generic
    # middle-truncate. Colors are dropped on a truncated line (partial escapes would
    # corrupt); a fitting line never reaches here.
    function fit_result(bare,   lb, vpos, tail_start, headstr, tailstr, rest, off) {
        lb = index(bare, "[")                       # first "[" opens the param id
        if (lb == 0) return GRY mid(bare) RST       # no param id: generic middle
        # Find the LAST VERDICT word (the id itself can contain letters, so scan
        # from where the id opens and keep the rightmost match).
        vpos = 0; off = lb
        while (match(substr(bare, off), /(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)/)) {
            vpos = off + RSTART - 1                  # absolute index of this verdict
            off  = vpos + RLENGTH                    # continue past it for a later one
        }
        if (vpos == 0) return GRY mid(bare) RST      # no verdict found: generic middle
        tail_start = (vpos > 1 && substr(bare, vpos-1, 1) == " ") ? vpos-1 : vpos
        headstr = substr(bare, 1, lb)               # readable "file::name[" up to "["
        tailstr = substr(bare, tail_start)          # " VERDICT [ NN%]"
        # The verdict tail is non-negotiable; the head gets the rest. If the head
        # (a long path + long function name) itself overruns that budget, clip its
        # END -- keep the START, which is the readable name -- so we never spill the
        # digit wall back in via a balanced middle-truncate. Budget = W-1 for the
        # ellipsis. If even the tail alone will not fit (pathologically narrow
        # terminal), fall back to a generic middle so at least the percentage shows.
        if (length(tailstr) + 1 >= W) return GRY mid(bare) RST
        if (length(headstr) + 1 + length(tailstr) > W)
            headstr = substr(headstr, 1, W - 1 - length(tailstr))
        return GRY headstr "\342\200\246" tailstr RST
    }
    {
        bare = strip($0)
        # header block -> gray + width-fit.
        if (bare ~ /^(platform |rootdir:|configfile:|testpaths:|plugins:|cachedir:|collecting |collected )/) {
            print GRY mid(bare) RST
        # an over-wide per-test result line -> cut the param-id digit wall at "[".
        } else if (length(bare) > W && bare ~ /::/ && bare ~ / (PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)([ ]|\[|$)/) {
            print fit_result(bare)
        # everything else: keep verbatim if it fits, else generic middle-truncate.
        } else {
            print fit_line($0, bare)
        }
        fflush()
    }'
}

# The default run includes EVERYTHING, network-marked live tests included. The
# `network`-marked tests ping real external hosts and skip themselves when
# offline, so a plain `bash tests.sh` still passes without connectivity.
#
# Real-time output. pytest writes to a PIPE below (we filter it), and off a tty it
# lets its stream sit in a big block buffer -- so with plain piping nothing appears
# until the run is nearly over and it FEELS frozen. Two things fix that: `python -u`
# unbuffers the interpreter, and `stdbuf -oL` forces pytest's stdout to flush per
# LINE, so each row of dots / each test line reaches the screen the instant pytest
# emits it. The downstream awk fflushes per line too, so the pipeline is live end
# to end. stdbuf is coreutils and effectively always present; if it is somehow
# missing, fall back to plain (still correct, just block-buffered) rather than fail.
STDBUF=(stdbuf -oL)
command -v stdbuf >/dev/null 2>&1 || STDBUF=()

STRIP='s/\x1b\[[0-9;]*[a-zA-Z]//g'   # ANSI-color scrubber for the plain-text logs

# The mode shown on the terminal writes its OWN log directly from the terminal run
# (no extra pytest process). The OTHER TWO modes each need their own pytest run for
# a faithful log -- and those runs must NOT share this working directory with the
# terminal run: a few tests build C binaries INTO the source tree and rmtree them
# in teardown (test_*_does_not_pollute_the_repo_tree), so two runs of the suite in
# the same dir race on those paths (a real FileNotFoundError mid-copy, reproduced).
# So each background log run executes in its OWN throwaway COPY of the repo (12M,
# copied in well under a second), cwd + PYTHONPATH pointed at the copy, leaving the
# real tree untouched and the runs fully independent -- they run CONCURRENTLY with
# the terminal (wall time ~= one run) yet cannot collide. errexit is off around the
# whole block so a test failure never aborts before we read status + wait on sinks.
#
# other_modes <shown> -- echo the two modes that are NOT the one on screen.
other_modes() {
    case "$1" in
        quiet) echo "mixed loud" ;;
        loud)  echo "mixed quiet" ;;
        *)     echo "loud quiet" ;;   # mixed shown
    esac
}
log_path_for() {                           # log_path_for <mode> -> its logfile
    case "$1" in quiet) echo "$LOG_QUIET" ;; loud) echo "$LOG_LOUD" ;; *) echo "$LOG_MIXED" ;; esac
}

# run_log_isolated <mode> <logfile> <dir> -- mirror the repo into <dir> and run
# pytest there in <mode>, writing the fitted, color-stripped transcript to
# <logfile>. <dir> is created and recorded by the PARENT (below) so the EXIT trap
# can remove it -- a `LOGCOPIES+=` here would be lost, since this runs backgrounded
# in a subshell whose variable writes never reach the parent. Its pytest exit code
# is irrelevant (the terminal run is authoritative), so it is not propagated.
run_log_isolated() {                       # run_log_isolated <mode> <logfile> <dir>
    local mode="$1" logfile="$2" dir="$3" o
    # Mirror the repo minus the bits a run does not need (venv is reused via $PY;
    # .git and logs are irrelevant to a test run) -- keeps the copy tiny and fast.
    if command -v rsync >/dev/null 2>&1; then
        rsync -a --exclude venv --exclude .git --exclude logs "$REPODIR"/ "$dir"/ 2>/dev/null || return 0
    else
        cp -a "$REPODIR"/. "$dir"/ 2>/dev/null || return 0
        rm -rf "$dir/venv" "$dir/.git" "$dir/logs"
    fi
    read -r -a o <<< "$(opts_for_mode "$mode")"
    # cwd = copy so repo-relative test paths resolve inside it; PYTHONPATH -> the
    # COPY's import roots so imported modules also write into the copy, never the
    # real tree. Reuse the real venv interpreter ($PY) -- the venv is not copied.
    ( cd "$dir" \
        && PYTHONPATH="$dir/libraries:$dir/scripts/libraries" \
           "${STDBUF[@]}" "$PY" -u -m pytest "${o[@]}" "${PYTEST_ARGS[@]}" 2>&1 ) \
        | fit "$mode" | sed -u -E "$STRIP" >> "$logfile"
}

set +o errexit
# Launch the two OFF-SCREEN log runs (isolated copies), concurrently. Create + record
# each copy dir HERE in the parent so the EXIT trap (via LOGCOPIES) always removes it,
# even though the run itself is backgrounded.
read -r -a OTHER <<< "$(other_modes "$MODE")"
DIR1="$(mktemp -d "${TMPDIR:-/tmp}/azarch-testlog.XXXXXX")"; LOGCOPIES+=("$DIR1")
DIR2="$(mktemp -d "${TMPDIR:-/tmp}/azarch-testlog.XXXXXX")"; LOGCOPIES+=("$DIR2")
run_log_isolated "${OTHER[0]}" "$(log_path_for "${OTHER[0]}")" "$DIR1" & P_LOG1=$!
run_log_isolated "${OTHER[1]}" "$(log_path_for "${OTHER[1]}")" "$DIR2" & P_LOG2=$!

# The TERMINAL run: pytest natively in the SELECTED mode, IN PLACE. Its fitted,
# colored stream goes to the screen AND (color-stripped) to that mode's own log --
# one process serves both. This is the authoritative run: its TRUE exit code is
# ${PIPESTATUS[0]} (stdbuf execs pytest and propagates its status, so this is
# pytest's own code, not tee's / awk's / sed's).
read -r -a TERM_OPTS <<< "$(opts_for_mode "$MODE")"
"${STDBUF[@]}" "$PY" -u -m pytest "${TERM_OPTS[@]}" "${PYTEST_ARGS[@]}" 2>&1 \
    | fit "$MODE" \
    | tee >(sed -u -E "$STRIP" >> "$(log_path_for "$MODE")")
status="${PIPESTATUS[0]}"
wait "$P_LOG1" "$P_LOG2"               # ensure both off-screen logs are fully written
set -o errexit

exit "$status"
