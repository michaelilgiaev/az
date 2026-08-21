#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

usage() {
  cat <<'EOF'
Usage: clear.sh [-o] [-l] [-c] [-h]

Clears the build tree. With NO flags it clears everything (the default):
output/, logs/, cache/, and every __pycache__ in the project.

Pass flags to clear only PART of the tree (flags combine):
  -o, --output   clear only output/
  -l, --logs     clear only logs/
  -c, --cache    clear only cache/  (also sweeps every __pycache__)
  -h, --help     show this help and exit

Examples:
  clear.sh            clear output/, logs/, cache/ and __pycache__ (everything)
  clear.sh -o -l      clear output/ and logs/ only (leaves cache/ and __pycache__)
  clear.sh -c         clear cache/ and __pycache__ only
EOF
}

# Selective flags: without any, clear EVERYTHING (unchanged original behaviour). With one or
# more, clear only the selected targets. __pycache__ is swept WITH cache -- so -c (or the no-flag
# default) sweeps it, while -o/-l alone leave it. Unknown flags are rejected non-zero with usage.
do_output=0
do_logs=0
do_cache=0
any_flag=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o|--output) do_output=1; any_flag=1 ;;
    -l|--logs)   do_logs=1;   any_flag=1 ;;
    -c|--cache)  do_cache=1;  any_flag=1 ;;
    -h|--help)   usage; exit 0 ;;
    *)
      echo "clear.sh: unknown option '$1'" >&2
      echo >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done
if [ "$any_flag" -eq 0 ]; then       # no flags -> the original everything-clear
  do_output=1
  do_logs=1
  do_cache=1
fi
# __pycache__ rides with cache (or the no-flag default that selects cache anyway).
sweep_pyc="$do_cache"

if [ "$(id -u)" -eq 0 ]; then
  echo "Running as root: this deletes root-owned leftovers too."
  echo "Use sudo when a compile was stopped mid-process: the ownership"
  echo "handback may not have run, leaving some files in cache/ root-owned,"
  echo "which git clean can't remove. Running as root wipes them anyway."
else
  echo "Running as your user. If some files in cache/ are root-owned"
  echo "(a compile stopped mid-process before ownership was handed back),"
  echo "they won't delete. Re-run with: sudo ./clear.sh"
fi
echo

# Delete each build dir and SAY what happened to it. Without this the script was
# silent, so you could not tell an already-clean tree from a failed delete.
#   - dir missing            -> nothing to do
#   - dir present, rm works  -> report it was removed (with its prior size)
#   - dir present, rm fails  -> report it survived (root-owned leftovers: re-run
#                               with sudo). rm's own stderr says which paths.
# Only the selected build dirs (order preserved: logs, cache, output). With no flags all three
# are selected, so this is the original list.
targets=()
[ "$do_logs" -eq 1 ]   && targets+=(logs)
[ "$do_cache" -eq 1 ]  && targets+=(cache)
[ "$do_output" -eq 1 ] && targets+=(output)
deleted=0
for d in "${targets[@]}"; do
  if [ ! -e "$d" ]; then
    echo "  [ skip    ] $d/ -- not present, nothing to delete"
    continue
  fi
  size="$(du -sh "$d" 2>/dev/null | cut -f1)"
  # Do not let a single failed rm abort the loop (set -e): capture its status so
  # the remaining dirs are still attempted and reported.
  if rm -rf "$d"; then
    echo "  [ deleted ] $d/ (was ${size:-?})"
    deleted=$((deleted + 1))
  else
    echo "  [ FAILED  ] $d/ still present -- likely root-owned; re-run: sudo ./clear.sh"
  fi
done

# Sweep every __pycache__ directory in the project (pytest/imports scatter them under
# tests/, libraries/, scripts/, ...). They are build junk, never tracked, and a stale one
# can shadow a just-edited module -- so wipe them all on a clear. Reported like the dirs
# above. Prune venv/ so we don't churn its thousands of cached stdlib entries.
# __pycache__ rides with cache: swept on the no-flag default or -c, left alone by -o/-l.
pyc_deleted=0
if [ "$sweep_pyc" -eq 1 ]; then
  echo
  pyc_found=0
  while IFS= read -r -d '' pc; do
    pyc_found=$((pyc_found + 1))
    if rm -rf "$pc"; then
      pyc_deleted=$((pyc_deleted + 1))
    else
      echo "  [ FAILED  ] $pc -- could not remove (permissions?); re-run: sudo ./clear.sh"
    fi
  done < <(find . -type d -name venv -prune -o -type d -name __pycache__ -print0)

  if [ "$pyc_found" -eq 0 ]; then
    echo "  [ skip    ] __pycache__ -- none found in the tree"
  else
    echo "  [ deleted ] $pyc_deleted __pycache__ director$( [ "$pyc_deleted" -eq 1 ] && echo y || echo ies )"
  fi
fi

echo
total=$((deleted + pyc_deleted))
if [ "$total" -eq 0 ]; then
  echo "Nothing was deleted -- the tree was already clean."
elif [ "$sweep_pyc" -eq 1 ]; then
  echo "Removed $deleted build director$( [ "$deleted" -eq 1 ] && echo y || echo ies )" \
       "and $pyc_deleted __pycache__ director$( [ "$pyc_deleted" -eq 1 ] && echo y || echo ies )."
else
  # __pycache__ was not in scope (-o/-l without -c), so don't mention it.
  echo "Removed $deleted build director$( [ "$deleted" -eq 1 ] && echo y || echo ies )."
fi
