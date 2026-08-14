"""Home-directory LAYOUT -- the single source of truth for the user's top-level folders
and convenience symlinks (and, by reference, Thunar's sidebar shortcuts).

WHAT THIS SHIPS. A fixed set of top-level DIRECTORIES in the home directory (Desktop,
Downloads, Vault, Documents, Ignore, Music, Pictures, Projects, Videos) plus a handful of
convenience SYMLINKS that surface otherwise-hidden dot locations as plain top-level names:

    Trash  -> .local/share/Trash/files   (the XDG trash "files" dir)
    Cache  -> .cache
    Config -> .config
    Bashrc -> .bashrc
    Local  -> .local

WHY THIS IS A MODULE AND NOT JUST COMPILER CODE. The SAME list drives two things: the
directories/symlinks created on disk, AND Thunar's sidebar shortcuts (the shortcuts pane
lists exactly this set). Keeping the list here, as data, means the folder layout and the
file-manager sidebar can never drift -- modifications/thunar/ imports LAYOUT from this module
and builds ~/.config/gtk-3.0/bookmarks (the GTK bookmarks Thunar reads) from it. Add a
folder here and it appears both on disk and in the sidebar.

DIRECTORIES vs CONTENT FILES. Unlike every other modification module, this one emits no
FILE CONTENT -- directories and symlinks are not text. So it does NOT expose emit_plan()
(the builder/dest/mode/owner shape compiler._emit_apps consumes). Instead it exposes plain
data (DIRECTORIES, LINKS, TRASH_DIRS) and compiler._emit_homedir() walks it with
emit.mkdir()/emit.link(). The layout is created in BOTH /home/main (the live user) AND
/etc/skel (so a Calamares-created user inherits the same tree).

RELATIVE SYMLINK TARGETS (load-bearing). Every symlink target is RELATIVE (".cache", not
"/home/main/.cache"). This is required so the SAME link is valid under /etc/skel: an
absolute /home/main/... target would dangle in /etc/skel and, after Calamares copies skel
into /home/<newuser>, would still point at /home/main. A relative target resolves against
the link's own directory, so "Cache -> .cache" is correct in every home it lands in.

THE TRASH CHAIN. "Trash -> .local/share/Trash/files" would DANGLE unless the XDG trash
spec dirs exist. So TRASH_DIRS creates the chain (.local/share/Trash/files AND
.local/share/Trash/info -- the spec requires both; `info` holds the .trashinfo metadata)
before the symlink is made, so Trash resolves to a real directory from first login.

Pure standard library (only data + the resolved-path helper Thunar's sidebar uses).
"""

from __future__ import annotations

# The live user's home (matches openbox.HOME / the airootfs /home/main tree). The layout is
# created here for the live user AND mirrored into /etc/skel by compiler._emit_homedir.
HOME = "/home/main"

# --- The top-level directories -------------------------------------------------
# Created in the home directory (and /etc/skel). ORDER is meaningful: it is the order the
# Thunar sidebar lists them (modifications/thunar builds bookmarks from this list), so the
# folders appear in the sidebar top-to-bottom exactly as written here. Names only (no
# leading path) -- they are created directly under the home dir.
DIRECTORIES: tuple[str, ...] = (
    "Desktop",
    "Downloads",
    "Vault",
    "Documents",
    "Ignore",
    "Music",
    "Pictures",
    "Projects",
    "Videos",
)

# --- The convenience symlinks --------------------------------------------------
# name -> RELATIVE target (see the module docstring: relative so the link is valid under
# /etc/skel and in every copied-out home). Each is created directly under the home dir as
# `name -> target`, resolving against the home dir. ORDER is meaningful (sidebar order,
# after the directories above).
LINKS: tuple[tuple[str, str], ...] = (
    ("Trash", ".local/share/Trash/files"),
    ("Cache", ".cache"),
    ("Config", ".config"),
    ("Bashrc", ".bashrc"),
    ("Local", ".local"),
)

# --- The XDG trash chain -------------------------------------------------------
# The trash spec's two required dirs, created (relative to the home dir) BEFORE the
# "Trash" symlink so it resolves to a real directory instead of dangling. `files` holds the
# trashed files (the Trash symlink points here); `info` holds the matching .trashinfo
# metadata. Created in both /home/main and /etc/skel.
TRASH_DIRS: tuple[str, ...] = (
    ".local/share/Trash/files",
    ".local/share/Trash/info",
)


def resolved_home_path(rel_or_link_target: str) -> str:
    """Return the ABSOLUTE, symlink-resolved home path for a layout entry's target.

    Used by modifications/thunar to point each sidebar bookmark at the REAL location (so
    entering a shortcut shows the resolved path in Thunar's location bar, not the symlink
    path). A plain directory name like "Config" whose link target is ".config" resolves to
    "/home/main/.config"; a directory like "Downloads" resolves to "/home/main/Downloads".
    The target is relative to HOME, so this just joins it onto HOME and normalizes (no
    filesystem access -- pure string, correct for the build host and the target alike)."""
    import posixpath

    return posixpath.normpath(f"{HOME}/{rel_or_link_target}")


def sidebar_entries() -> list[tuple[str, str]]:
    """Return the sidebar shortcut list as (label, absolute_resolved_target) pairs, in
    display order: the directories first, then the symlinks (pointed at their RESOLVED
    targets). This is the single list modifications/thunar turns into the GTK bookmarks file
    and Thunar renders in the shortcuts pane -- so the sidebar and the on-disk layout are
    the same set, by construction.

    For a plain directory the target is the directory itself (Desktop ->
    /home/main/Desktop). For a symlink the target is what the link resolves to (Config ->
    /home/main/.config, Trash -> /home/main/.local/share/Trash/files), so opening the
    shortcut shows the real path rather than the /home/main/Config symlink path."""
    entries: list[tuple[str, str]] = []
    for name in DIRECTORIES:
        entries.append((name, resolved_home_path(name)))
    for name, target in LINKS:
        entries.append((name, resolved_home_path(target)))
    return entries
