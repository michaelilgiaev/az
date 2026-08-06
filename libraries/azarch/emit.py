"""Emit contract: write configuration-as-Python content out as real files in the ISO tree.

The configuration modules (``azarch.configuration.*``) hold each artifact's content as a
Python string. These helpers place that content on disk with the right mode,
and copy the few verbatim data files. This is the seam between "configuration as data"
(the strings) and "build logic" (where they go).
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from . import paths


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, text: str, mode: int = 0o644) -> Path:
    """Write a generated configuration file, creating parent dirs. Normalizes to a single
    trailing newline (the archiso/pacman/systemd parsers all expect one)."""
    path = Path(path)
    _ensure_parent(path)
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")
    os.chmod(path, mode)
    return path


def write_exec(path: Path, text: str) -> Path:
    """Write a script and make it executable (0o755)."""
    return write_text(path, text, mode=0o755)


def copy_data(rel: str, dest: Path, mode: int | None = None) -> Path:
    """Copy a verbatim file from libraries/packages/<rel> to dest.

    (Historically libraries/data/; the tree was consolidated under
    libraries/packages/. The function name is kept for call-site stability.)"""
    src = paths.PACKAGESDIR / rel
    dest = Path(dest)
    _ensure_parent(dest)
    shutil.copy2(src, dest)
    if mode is not None:
        os.chmod(dest, mode)
    return dest


def copy_asset(rel: str, dest: Path, mode: int | None = None) -> Path:
    """Copy a verbatim file from assets/<rel> to dest (binaries, scripts, images)."""
    src = paths.ASSETSDIR / rel
    dest = Path(dest)
    _ensure_parent(dest)
    shutil.copy2(src, dest)
    if mode is not None:
        os.chmod(dest, mode)
    return dest


def copy_pkg_file(rel: str, dest: Path, mode: int | None = None) -> Path:
    """Copy a verbatim file shipped inside the azarch package (libraries/azarch/<rel>).

    Used for payload the user keeps beside the package rather than under assets/
    -- currently the vendored ckbcomp (a Python 3 port of the upstream Perl ckbcomp).
    """
    src = paths.PKGDIR / rel
    dest = Path(dest)
    _ensure_parent(dest)
    shutil.copy2(src, dest)
    if mode is not None:
        os.chmod(dest, mode)
    return dest


def copy_tree(src: Path, dest: Path) -> None:
    """Recursively copy src/* into dest (like `cp -r src/. dest/`)."""
    src = Path(src)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dest / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True, symlinks=True)
        else:
            shutil.copy2(item, target)


def link(target: str, linkname: Path) -> None:
    """Create/replace a symlink linkname -> target (for systemd .wants links)."""
    linkname = Path(linkname)
    _ensure_parent(linkname)
    if linkname.is_symlink() or linkname.exists():
        linkname.unlink()
    linkname.symlink_to(target)


def mkdir(path: Path) -> Path:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path
