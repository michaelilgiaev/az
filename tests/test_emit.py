"""azarch.emit -- the seam that writes config strings to disk.

Pure filesystem behavior, exercised entirely in a pytest tmp_path. The whole
build's on-disk correctness (file modes, trailing newlines the archiso/pacman/
systemd parsers require, symlink replacement) rides on these four helpers.
"""

from __future__ import annotations

import os
import stat

from azarch import emit


def _mode(path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def test_write_text_creates_parent_dirs(tmp_path):
    target = tmp_path / "a" / "b" / "c" / "file.conf"
    emit.write_text(target, "hello")
    assert target.read_text() == "hello\n"


def test_write_text_normalizes_single_trailing_newline(tmp_path):
    # No newline in -> exactly one newline out (the parsers expect one).
    p = emit.write_text(tmp_path / "x", "no newline")
    assert p.read_text() == "no newline\n"


def test_write_text_does_not_double_the_trailing_newline(tmp_path):
    # Already has a newline -> it is NOT doubled.
    p = emit.write_text(tmp_path / "x", "has newline\n")
    assert p.read_text() == "has newline\n"


def test_write_text_default_mode_is_0644(tmp_path):
    p = emit.write_text(tmp_path / "x", "data")
    assert _mode(p) == 0o644


def test_write_text_custom_mode(tmp_path):
    p = emit.write_text(tmp_path / "x", "data", mode=0o600)
    assert _mode(p) == 0o600


def test_write_exec_is_0755(tmp_path):
    # Scripts must be executable or the ISO's [ -x ... ] guards silently skip them.
    p = emit.write_exec(tmp_path / "run.sh", "#!/bin/bash\necho hi")
    assert _mode(p) == 0o755


def test_copy_data_reads_from_datadir(tmp_path, monkeypatch):
    # copy_data resolves its source against paths.DATADIR; point DATADIR at a fake
    # source tree so no real data file is needed.
    src_root = tmp_path / "data"
    src_root.mkdir()
    (src_root / "thing.txt").write_text("payload")
    monkeypatch.setattr(emit.paths, "DATADIR", src_root)

    dest = tmp_path / "out" / "thing.txt"
    emit.copy_data("thing.txt", dest)
    assert dest.read_text() == "payload"


def test_copy_data_applies_mode_when_given(tmp_path, monkeypatch):
    src_root = tmp_path / "data"
    src_root.mkdir()
    (src_root / "s").write_text("x")
    monkeypatch.setattr(emit.paths, "DATADIR", src_root)

    dest = tmp_path / "s"
    emit.copy_data("s", dest, mode=0o755)
    assert _mode(dest) == 0o755


def test_link_replaces_an_existing_link(tmp_path):
    # emit.link must overwrite a stale symlink (systemd .wants links get re-pointed).
    link = tmp_path / "wants" / "unit"
    emit.link("target-a", link)
    assert os.readlink(link) == "target-a"
    emit.link("target-b", link)
    assert os.readlink(link) == "target-b"


def test_copy_tree_copies_files_and_subdirs(tmp_path):
    src = tmp_path / "src"
    (src / "sub").mkdir(parents=True)
    (src / "top.txt").write_text("top")
    (src / "sub" / "deep.txt").write_text("deep")

    dest = tmp_path / "dest"
    emit.copy_tree(src, dest)
    assert (dest / "top.txt").read_text() == "top"
    assert (dest / "sub" / "deep.txt").read_text() == "deep"
