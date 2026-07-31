#!/usr/bin/env bash
#
# pull_specifications.sh -- generate the Az'arch DISTRIBUTION specification.
#
# This produces four artifacts:
#   documentations/SPECIFICATIONS_GENERAL.md  the general / developer view:
#                                     at-a-glance facts, what Az'arch changes on
#                                     top of Arch, and the subsystem breakdown.
#                                     No dependency-graph tables (those are below).
#   documentations/SPECIFICATIONS_COMPONENTS_OVERVIEW.svg  a navigable layered
#                                     image of the dependency graph, kernel at the
#                                     bottom up to leaf apps at the top, boxes
#                                     coloured by category and marked by edition.
#   documentations/SPECIFICATIONS_COMPONENTS_NAVIGATE_FULL.html  the interactive
#                                     twin of the SVG: the same layered map, but
#                                     open it in a browser and click any component
#                                     to inspect it and highlight its dependencies.
#   documentations/SPECIFICATIONS_COMPONENTS_FULL.txt  the exhaustive listing:
#                                     EVERY component, nothing collapsed, each with
#                                     a plain-language purpose (the official Arch
#                                     package description), its layer, and its full
#                                     requires / required-by edges.
# All are computed from the real package set, with real versions.
#
# The dependency data is resolved from the official Arch Linux core/extra/multilib
# package databases (the repos the ISO is actually built against), NOT from the
# host's pacman databases -- on a non-Arch host those carry different packages and
# versions and would produce a wrong specification. The databases are fetched once and
# cached under cache/specification-db/; pass --offline to reuse them without network.
#
# This is a thin shim: it locates the repo, checks for python3, and hands off to
# scripts/libraries/pull_specifications.py, which orchestrates the work across
# scripts/libraries/specification_{db,resolve,classify,content,render,svg}.py. All flags
# are passed straight through.
#
# Usage:
#   scripts/pull_specifications.sh [options]
#
# Options (forwarded to the Python orchestrator):
#   -o, --output FILE   write the general Markdown here (default: documentations/SPECIFICATIONS_GENERAL.md)
#       --svg FILE      write the components graph SVG here (default: documentations/SPECIFICATIONS_COMPONENTS_OVERVIEW.svg)
#       --html FILE     write the interactive HTML map here (default: documentations/SPECIFICATIONS_COMPONENTS_NAVIGATE_FULL.html)
#       --fulltext FILE write the full component listing here (default: documentations/SPECIFICATIONS_COMPONENTS_FULL.txt)
#   -m, --manifest FILE package manifest (default: libraries/data/packages.x86_64)
#       --db-cache DIR  where to cache the Arch .db files (default: cache/specification-db)
#       --mirror URL    Arch mirror base URL to fetch databases from
#       --offline       reuse cached .db files; do not download
#       --stdout        print the Markdown to stdout (skips writing both files)
#   -h, --help          show this help and exit
#
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_ENTRY="$SELF_DIR/libraries/pull_specifications.py"

case "${1:-}" in
    -h|--help)
        sed -n '3,49p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
        exit 0
        ;;
esac

if ! command -v python3 >/dev/null 2>&1; then
    echo "pull_specifications: python3 is required but was not found" >&2
    exit 1
fi

if [ ! -f "$PY_ENTRY" ]; then
    echo "pull_specifications: missing $PY_ENTRY" >&2
    exit 1
fi

exec python3 "$PY_ENTRY" "$@"
