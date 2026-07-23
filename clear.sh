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

rm -rf logs/ cache/ output/
