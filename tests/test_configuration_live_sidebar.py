"""modifications.thunar.live_sidebar -- the runtime GTK-bookmarks sync (PROMPT: additions to
the home dir must show up in Thunar's sidebar automatically).

Why these tests matter: the sidebar is otherwise STATIC (a build-time file), so "anything the
user adds shows up" needs a runtime helper. These pin: the required ORDER (dirs -> files ->
symlinks -> Trash last), that symlink bookmarks resolve to their targets, that the helper is
wired into session startup (both live + installed autostart), and -- by actually RUNNING the
generated shell script against a fixture home -- that its enumeration/ordering is correct and it
tracks additions.
"""

from __future__ import annotations

import os
import subprocess

from modifications import home_directory
from modifications import openbox
from modifications.thunar import live_sidebar, sidebar


# --- static seed ordering (home_directory.sidebar_entries) ------------------

def test_static_sidebar_order_is_dirs_then_symlinks_then_trash_last():
    # PROMPT: directories -> files -> symbolic links -> "Trash" LAST. The curated set has real
    # dirs (DIRECTORIES) then symlinks (LINKS), with Trash pinned to the very end.
    labels = [label for label, _ in home_directory.sidebar_entries()]
    # every real directory comes before every symlink.
    last_dir_idx = max(labels.index(d) for d in home_directory.DIRECTORIES)
    link_names = [n for n, _ in home_directory.LINKS]
    first_link_idx = min(labels.index(n) for n in link_names)
    assert last_dir_idx < first_link_idx, labels
    # Trash is dead last.
    assert labels[-1] == home_directory.TRASH_LINK_NAME, labels


def test_static_sidebar_bookmarks_put_trash_last_and_no_home():
    bm = sidebar.gtk_bookmarks().splitlines()
    # NO "Home Directory" bookmark anywhere (the user deleted it from the sidebar).
    assert not any(ln.endswith(" Home Directory") for ln in bm)
    assert not any(".home-directory" in ln for ln in bm)
    assert bm[-1].endswith(" Trash")                  # Trash last
    # Trash resolves to the real trash files dir (resolved-path behaviour).
    assert bm[-1].startswith("file:///home/main/.local/share/Trash/files ")


# --- the sync helper string + wiring ----------------------------------------

def test_sync_script_is_wired_into_both_autostarts():
    # The --watch helper is launched from the SHARED autostart block, so it runs on the LIVE
    # and the INSTALLED session (additions tracked on both).
    for au in (openbox.openbox_autostart(), openbox.openbox_autostart_installed()):
        assert live_sidebar.SYNC_SCRIPT_DEST in au
        assert "--watch" in au


def test_sync_path_lock_step_with_openbox():
    # openbox holds the path as a constant (to avoid importing thunar); it must not drift.
    assert openbox.THUNAR_SIDEBAR_SYNC == live_sidebar.SYNC_SCRIPT_DEST
    assert live_sidebar.SYNC_SCRIPT_DEST == "/usr/local/lib/azarch/azarch-sidebar-sync"


def test_sync_helper_emitted_root_owned_executable():
    plan = live_sidebar.emit_plan()
    e = next(x for x in plan if x["dest"] == live_sidebar.SYNC_SCRIPT_DEST)
    assert e["owner"] == "root"
    assert e["mode"] == 0o755
    # the whole thunar plan includes it too.
    from modifications import thunar
    assert live_sidebar.SYNC_SCRIPT_DEST in {x["dest"] for x in thunar.emit_plan()}


def test_sync_script_is_valid_posix_sh():
    script = live_sidebar.sync_script()
    assert script.startswith("#!/bin/sh")
    # `sh -n` parses without executing -- catches a syntax slip in the generated script.
    r = subprocess.run(["sh", "-n"], input=script, text=True,
                       stderr=subprocess.PIPE)
    assert r.returncode == 0, r.stderr


# --- FUNCTIONAL: run the generated script against a fixture home -------------

def _run_sync(tmp_home, *args):
    """Write the generated script and run it with HOME=tmp_home; return the bookmarks lines."""
    script = tmp_home / "azarch-sidebar-sync"
    script.write_text(live_sidebar.sync_script())
    env = dict(os.environ, HOME=str(tmp_home))
    subprocess.run(["sh", str(script), *args], env=env, timeout=20, check=False)
    bm = tmp_home / ".config/gtk-3.0/bookmarks"
    return bm.read_text().splitlines() if bm.exists() else []


def test_functional_ordering_dirs_files_symlinks_trash_last(tmp_path):
    # Build a realistic home: real dirs, real files, symlinks (incl Trash + a user-added one),
    # a dotfile (skipped), Desktop (skipped -- built-in provides it).
    for d in ("Desktop", "Downloads", "Documents", ".cache", ".config",
              ".local/share/Trash/files", "ZebraDir", "AppleDir"):
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    (tmp_path / "notes.txt").write_text("")
    (tmp_path / ".bashrc").write_text("")
    (tmp_path / ".hidden_file").write_text("")
    os.symlink(".cache", tmp_path / "Cache")
    os.symlink(".config", tmp_path / "Config")
    os.symlink(".local/share/Trash/files", tmp_path / "Trash")
    os.symlink("Downloads", tmp_path / "MyLink")   # a user-added symlink

    lines = _run_sync(tmp_path)
    labels = [ln.split(" ", 1)[1] for ln in lines]
    # NO "Home Directory" bookmark (deleted from the sidebar); the list starts at the dirs.
    assert "Home Directory" not in labels
    assert not any(".home-directory" in ln for ln in lines)
    # Desktop skipped, .hidden_file skipped.
    assert "Desktop" not in labels
    assert ".hidden_file" not in labels
    # Order groups: dirs (alpha) < files < symlinks < Trash last.
    def idx(lbl):
        return labels.index(lbl)
    # dirs before files before symlinks.
    assert idx("AppleDir") < idx("Documents") < idx("Downloads") < idx("ZebraDir")
    assert idx("ZebraDir") < idx("notes.txt")               # last dir before first file
    assert idx("notes.txt") < idx("Cache")                  # file before first symlink
    assert idx("Cache") < idx("Config") < idx("MyLink")     # symlinks alpha
    assert labels[-1] == "Trash"                            # Trash dead last
    # symlink bookmarks resolve to their targets (location bar shows the real path).
    cache_line = next(ln for ln in lines if ln.endswith(" Cache"))
    assert cache_line.startswith(f"file://{tmp_path}/.cache ")
    mylink_line = next(ln for ln in lines if ln.endswith(" MyLink"))
    assert mylink_line.startswith(f"file://{tmp_path}/Downloads ")


def test_functional_bookmarks_have_no_comment_lines(tmp_path):
    (tmp_path / "Downloads").mkdir()
    lines = _run_sync(tmp_path)
    for ln in lines:
        assert ln.startswith("file://"), ln   # every line is a bookmark (GTK format)


def test_functional_addition_is_tracked_by_watch(tmp_path):
    # Prove --watch regenerates when a new top-level entry appears (the live requirement).
    (tmp_path / "Downloads").mkdir()
    script = tmp_path / "azarch-sidebar-sync"
    script.write_text(live_sidebar.sync_script())
    env = dict(os.environ, HOME=str(tmp_path))
    proc = subprocess.Popen(["sh", str(script), "--watch"], env=env)
    try:
        import time
        bm = tmp_path / ".config/gtk-3.0/bookmarks"
        # Wait for the INITIAL regen to land (Popen+sh startup has variance; poll, don't assume).
        deadline = time.time() + 8
        while time.time() < deadline and not bm.exists():
            time.sleep(0.2)
        assert bm.exists(), "initial regen never wrote the bookmarks file"
        assert "NewFolderByUser" not in bm.read_text()
        (tmp_path / "NewFolderByUser").mkdir()   # user adds a folder
        # poll for the regeneration (interval is WATCH_INTERVAL_SECS).
        deadline = time.time() + live_sidebar.WATCH_INTERVAL_SECS + 8
        appeared = False
        while time.time() < deadline:
            if "NewFolderByUser" in bm.read_text():
                appeared = True
                break
            time.sleep(0.3)
        assert appeared, "watch did not pick up the added folder"
    finally:
        proc.terminate()
        proc.wait(timeout=5)
