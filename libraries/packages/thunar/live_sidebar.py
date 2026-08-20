"""Live Thunar sidebar -- keep ~/.config/gtk-3.0/bookmarks in sync with the ACTUAL home
directory contents at runtime (PROMPT: "whatever the user ADDS to the home directory later ...
must AUTOMATICALLY appear on the sidebar").

THE PROBLEM. GTK bookmarks are a STATIC file. packages/thunar/sidebar builds it once at
BUILD time from home_directory's curated set, so a folder/file/symlink the user creates in
$HOME AFTER install never shows up in the shortcuts pane on its own. Making "anything added to
home shows up" needs a RUNTIME mechanism.

THE MECHANISM. A tiny POSIX-sh helper (azarch-sidebar-sync) that regenerates the bookmarks file
from the CURRENT top-level home contents, in the SAME required order as the static seed
(PROMPT: directories -> files -> symbolic links -> "Trash" LAST), pointing symlink bookmarks at
their RESOLVED targets (consistent with the resolved-path behaviour everywhere else). It runs in
two modes:
  * `azarch-sidebar-sync` (once)   -- regenerate the bookmarks now.
  * `azarch-sidebar-sync --watch`  -- regenerate now, then loop: every ~2s recompute a cheap
                                      SIGNATURE of the top-level home listing (each entry's name
                                      + type + symlink target) and regenerate only when it
                                      changed. A signature (not the dir mtime) catches an
                                      add/remove/retarget even within the same clock second
                                      (mtime is 1s-granular) and avoids a needless rewrite when
                                      nothing changed. Dependency-free (no inotify-tools in the
                                      manifest; the PROMPT explicitly allows "a lightweight
                                      periodic" watcher) and matches the repo's other
                                      autostart-launched helpers.

WIRING. The OpenBox session autostart (packages/openbox) launches
`azarch-sidebar-sync --watch &` -- both the LIVE and the INSTALLED autostart (via the shared
_openbox_autostart_common block), so additions are tracked on both. The script is a root-owned
system helper (like the other /usr/local/lib/azarch tools); it operates on the invoking user's
own $HOME, so it needs no privilege.

ORDERING (matches home_directory.sidebar_entries + the static seed):
  1. real DIRECTORIES  (alphabetical), EXCEPT Desktop (Thunar's built-in place already provides
     it at the same path -- adding ours would duplicate it, same reason sidebar.py skips it).
  2. regular FILES     (alphabetical).
  3. SYMLINKS          (alphabetical), each bookmarked at its RESOLVED target, EXCEPT "Trash".
  4. "Trash" LAST      (it is a symlink but the spec pins it to the very end).
There is NO "Home Directory" bookmark: the user deleted it from the sidebar (there is a Home
toolbar button), so the list starts straight at the directories. Hidden entries (dotfiles) are
skipped -- the curated convenience symlinks (Cache/Config/...) are NON-hidden names, so the
surfaced set matches the intent without dumping every dotfile.
"""

from __future__ import annotations

from . import home_directory

# The live user's home (matches openbox.HOME / the airootfs /home/main tree). The script itself
# uses the runtime "$HOME", so it is correct for any user that inherited the config via skel.
HOME = "/home/main"

# The sync helper -- a root-owned system script next to the other /usr/local/lib/azarch tools.
# It acts on the INVOKING user's $HOME (no privilege needed).
SYNC_SCRIPT_DEST = "/usr/local/lib/azarch/azarch-sidebar-sync"

# The bookmarks file it regenerates (the same path the static seed writes).
GTK_BOOKMARKS_PATH = f"{HOME}/.config/gtk-3.0/bookmarks"

# No "Home Directory" bookmark -- the user deleted it from the sidebar (see the module docstring);
# the regenerated file starts straight at the directories. The built-in username Home stays
# hidden via settings.HIDDEN_BOOKMARKS[file:///home/main].

# The Desktop entry is skipped (Thunar's built-in place already provides it -- see sidebar.py).
SKIP_NAMES = ("Desktop",)

# The Trash shortcut name, pinned to the very end of the ordering (home_directory.TRASH_LINK_NAME).
TRASH_NAME = home_directory.TRASH_LINK_NAME

# How often --watch re-checks the home dir mtime (seconds). Small enough to feel instant, large
# enough to be free.
WATCH_INTERVAL_SECS = 2


def sync_script() -> str:
    """Return the azarch-sidebar-sync POSIX-sh helper. Regenerates the GTK bookmarks from the
    live top-level home contents in the required order (dirs -> files -> symlinks -> Trash last),
    symlinks resolved. `--watch` polls a cheap signature of the home listing and regenerates on
    change (an add/remove/retarget, caught even within the same clock second).

    Pure POSIX sh + coreutils (ls/readlink/realpath/stat/printf/sort) -- all in `base`/coreutils
    on the ISO, no inotify-tools. The bookmark URI for a symlink is `realpath -m` of the link
    (so the location bar shows the real target); for a dir/file it is the entry path. Every
    non-blank line is a bookmark (the GTK format has no comments), so the file carries none."""
    skip_case = "|".join(SKIP_NAMES)          # e.g. "Desktop"
    trash = TRASH_NAME
    interval = WATCH_INTERVAL_SECS
    return f"""\
#!/bin/sh
# azarch-sidebar-sync -- regenerate ~/.config/gtk-3.0/bookmarks from the CURRENT top-level home
# contents so anything the user adds to $HOME shows up in Thunar's sidebar (PROMPT). Generated
# by packages/thunar/live_sidebar (edit the Python, not this file). Order: real dirs ->
# files -> symlinks -> "Trash" last; symlink bookmarks point at their resolved target. Runs as
# the invoking user on their own $HOME (no privilege). `--watch` polls the home dir mtime.
set -u

BM="$HOME/.config/gtk-3.0/bookmarks"

# file:// URI for an absolute path (paths here are plain home paths: no spaces/URL-encoding).
uri() {{ printf 'file://%s' "$1"; }}

regen() {{
    dirs=""; files=""; links=""; trash=""
    # Enumerate NON-hidden top-level entries of $HOME (the convenience symlinks are non-hidden).
    # `ls -1` on the plain names; guard the empty-dir case.
    for name in $(cd "$HOME" 2>/dev/null && ls -1 2>/dev/null); do
        # Skip entries Thunar's built-in places already provide (Desktop).
        case "$name" in
            {skip_case}) continue ;;
        esac
        path="$HOME/$name"
        if [ -L "$path" ]; then
            # A symlink -> bookmark its RESOLVED target so the location bar shows the real path.
            target=$(realpath -m -- "$path" 2>/dev/null || printf '%s' "$path")
            line="$(uri "$target") $name"
            if [ "$name" = "{trash}" ]; then
                trash="$line"                 # pin Trash to the very end
            else
                links="$links$line
"
            fi
        elif [ -d "$path" ]; then
            dirs="$dirs$(uri "$path") $name
"
        elif [ -e "$path" ]; then
            files="$files$(uri "$path") $name
"
        fi
    done
    # Sort each group alphabetically by label (field 2). Emit: dirs, files, links, then Trash
    # last (NO "Home Directory" -- the user deleted it from the sidebar). `sort` on empty input
    # is a no-op. Write atomically via a temp file.
    tmp="$BM.azarch.$$"
    mkdir -p "$(dirname "$BM")"
    if {{
        [ -n "$dirs" ]  && printf '%s' "$dirs"  | sort -k2
        [ -n "$files" ] && printf '%s' "$files" | sort -k2
        [ -n "$links" ] && printf '%s' "$links" | sort -k2
        [ -n "$trash" ] && printf '%s\\n' "$trash"
        # Force a success exit for the group: the last `[ -n ... ] && printf` above is FALSE
        # (returns 1) whenever that group is empty (e.g. no Trash symlink), which would
        # otherwise make the whole block "fail" and skip the mv below, leaving no bookmarks.
        true
    }} > "$tmp" 2>/dev/null; then
        mv -f "$tmp" "$BM" 2>/dev/null || rm -f "$tmp" 2>/dev/null
    else
        rm -f "$tmp" 2>/dev/null
    fi
}}

# A cheap signature of the top-level home listing: the entry names plus a type marker (dir /
# symlink / other), sorted. Detecting change via this (not the dir mtime) reliably catches an
# add/remove/retarget even WITHIN the same clock second (mtime has 1s granularity on many
# filesystems, so an mtime compare can miss a fast change) -- and it also skips a needless
# rewrite when nothing changed (so the sidebar does not flicker every poll). `ls -1` is guarded
# for the empty-dir case; the per-entry test picks L/d/f.
home_sig() {{
    cd "$HOME" 2>/dev/null || {{ echo ""; return; }}
    for name in $(ls -1 2>/dev/null); do
        if [ -L "$name" ]; then t=L; elif [ -d "$name" ]; then t=d; else t=f; fi
        # also fold in a symlink's target so a re-pointed link triggers a refresh.
        if [ "$t" = L ]; then
            printf '%s:%s>%s\\n' "$t" "$name" "$(readlink -- "$name" 2>/dev/null)"
        else
            printf '%s:%s\\n' "$t" "$name"
        fi
    done | sort
}}

regen
if [ "${{1:-}}" = "--watch" ]; then
    last=$(home_sig)
    while :; do
        sleep {interval}
        now=$(home_sig)
        if [ "$now" != "$last" ]; then
            last="$now"
            regen
        fi
    done
fi
"""


_EXEC = 0o755


def emit_plan() -> list[dict]:
    """Return the emit plan for the live-sidebar sync helper: a single root-owned executable
    system script. (It is wired into session startup by packages/openbox's autostart.)"""
    return [
        {
            "builder": sync_script,
            "dest": SYNC_SCRIPT_DEST,
            "mode": _EXEC,
            "owner": "root",
        },
    ]
