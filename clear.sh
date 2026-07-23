#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

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
targets=(logs cache output)
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

echo
if [ "$deleted" -eq 0 ]; then
  echo "Nothing was deleted -- the tree was already clean."
else
  echo "Removed $deleted director$( [ "$deleted" -eq 1 ] && echo y || echo ies )."
fi
