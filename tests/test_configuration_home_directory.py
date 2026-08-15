"""modifications.home_directory -- the single source of truth for the home-directory layout
(top-level folders + convenience symlinks) that Thunar's sidebar also mirrors.

Why these tests matter: compiler._emit_homedir walks this module's plain data
(DIRECTORIES/LINKS/TRASH_DIRS) with emit.mkdir()/emit.link() into BOTH /home/main and
/etc/skel, and modifications/thunar builds the GTK bookmarks Thunar reads from the SAME data.
Two invariants are load-bearing and guarded here:

  * Symlink targets must be RELATIVE -- an absolute /home/main/... target would dangle
    under /etc/skel and in a Calamares-copied /home/<newuser>.
  * The Trash symlink's target chain (.local/share/Trash/files) must be in TRASH_DIRS so
    the link does not dangle.

The exact folder/link SET is the spec (PROMPT task 1), so it is pinned literally: a
drift here silently changes both the on-disk layout and the file-manager sidebar.
"""

from __future__ import annotations

import posixpath

from modifications import home_directory as hd


def test_directory_set_is_exactly_the_spec():
    # PROMPT task 1: these nine folders, in this order (the order is the sidebar order).
    assert hd.DIRECTORIES == (
        "Desktop", "Downloads", "Vault", "Documents", "Ignore",
        "Music", "Pictures", "Projects", "Videos",
    )


def test_link_set_is_exactly_the_spec():
    # PROMPT task 1: these five convenience symlinks, name -> RELATIVE target.
    assert hd.LINKS == (
        ("Trash", ".local/share/Trash/files"),
        ("Cache", ".cache"),
        ("Config", ".config"),
        ("Bashrc", ".bashrc"),
        ("Local", ".local"),
    )


def test_every_symlink_target_is_relative():
    # Load-bearing: a relative target resolves against the link's own dir, so the same link
    # is valid in /home/main AND /etc/skel AND a copied-out home. An absolute target dangles.
    for name, target in hd.LINKS:
        assert not target.startswith("/"), f"{name} target must be relative, got {target!r}"
        assert not posixpath.isabs(target), name


def test_trash_symlink_target_is_covered_by_trash_dirs():
    # "Trash -> .local/share/Trash/files" would dangle unless the chain exists. The link
    # target must be one of the dirs TRASH_DIRS creates.
    trash_target = dict(hd.LINKS)["Trash"]
    assert trash_target in hd.TRASH_DIRS


def test_trash_chain_has_both_spec_dirs():
    # The XDG trash spec requires BOTH files/ and info/ (info holds the .trashinfo metadata).
    assert ".local/share/Trash/files" in hd.TRASH_DIRS
    assert ".local/share/Trash/info" in hd.TRASH_DIRS


def test_home_is_the_live_user_home():
    assert hd.HOME == "/home/main"


def test_resolved_home_path_joins_and_normalizes():
    # A plain directory resolves to itself under HOME.
    assert hd.resolved_home_path("Downloads") == "/home/main/Downloads"
    # A dot target (a symlink target) resolves to the real dot location, no symlink hop.
    assert hd.resolved_home_path(".config") == "/home/main/.config"
    assert hd.resolved_home_path(".local/share/Trash/files") == \
        "/home/main/.local/share/Trash/files"


def test_sidebar_entries_are_directories_then_links_resolved():
    entries = hd.sidebar_entries()
    labels = [label for label, _ in entries]
    # PROMPT ordering: directories first (in order), then the symlinks (in order), with "Trash"
    # forced to the very END (it is a symlink but pinned last). No plain files in the curated
    # set, so the order is DIRECTORIES, then non-Trash LINKS, then Trash.
    assert labels == [
        "Desktop", "Downloads", "Vault", "Documents", "Ignore",
        "Music", "Pictures", "Projects", "Videos",
        "Cache", "Config", "Bashrc", "Local",
        "Trash",
    ]
    targets = dict(entries)
    # A directory shortcut points at itself.
    assert targets["Desktop"] == "/home/main/Desktop"
    # A symlink shortcut points at the RESOLVED target (so Thunar shows the real path,
    # not the /home/main/Config symlink path) -- PROMPT task 2 "display the ACTUAL path".
    assert targets["Config"] == "/home/main/.config"
    assert targets["Cache"] == "/home/main/.cache"
    assert targets["Trash"] == "/home/main/.local/share/Trash/files"
    assert targets["Local"] == "/home/main/.local"
    # Bashrc is a FILE target (.bashrc); still resolved under HOME.
    assert targets["Bashrc"] == "/home/main/.bashrc"


def test_home_directory_symlink_backs_the_home_bookmark():
    # PROMPT batch item 4 fix: a hidden ".home-directory -> ." symlink gives the "Home Directory"
    # sidebar bookmark a DISTINCT URI so it survives Thunar hiding the built-in Home
    # (file:///home/main). The target is RELATIVE (valid under /etc/skel), and the name is
    # dot-prefixed so the live-sidebar (which skips hidden entries) never lists it as clutter.
    assert hd.HOME_DIR_SYMLINK_NAME == ".home-directory"
    assert hd.HOME_DIR_SYMLINK_TARGET == "."
    assert not hd.HOME_DIR_SYMLINK_TARGET.startswith("/")   # relative
    assert hd.HOME_DIR_BOOKMARK_URI == "file:///home/main/.home-directory"
    # distinct from the built-in Home URI (else the bookmark would be hidden with it).
    assert hd.HOME_DIR_BOOKMARK_URI != f"file://{hd.HOME}"


def test_no_absolute_paths_leak_into_layout_names():
    # Directory names and link names are bare (no leading path) -- they are created
    # directly under the home dir.
    for name in hd.DIRECTORIES:
        assert "/" not in name, name
    for name, _ in hd.LINKS:
        assert "/" not in name, name
