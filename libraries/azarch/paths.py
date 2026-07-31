"""Filesystem layout for the build.

Mirrors the directory scheme the old compile.sh used, so the Docker bind mounts
(cache/ output/ logs/) and the on-disk artifacts land in exactly the same places:

  REPODIR/                 repo root (where compile.sh lives)
    libraries/data/        verbatim data files (packages.x86_64, big QML)
    cache/                 persistent download cache (git-ignored, survives builds)
      build/               WORKDIR on a NATIVE run: disposable mkarchiso scratch
      pkgs/                persistent package repo + synced DBs (the offline store)
      pacman-pkg/          pacstrap CacheDir injected into the profile pacman.conf
    output/                BUILDDIR: the finished .iso lands here
    logs/                  full.log + steps.log

In DOCKER the disposable WORKDIR is moved OUT of the bind-mounted cache/ to a
container-internal path (/tmp/azarch-build) so its root-owned mkarchiso scratch
dies with the container and can never leave root-owned files locked on the host
(a hard `docker kill` sends an untrappable SIGKILL that skips the handback). The
persistent stores (cache/pkgs, cache/pacman-pkg) and the ISO (output/) stay on
the bind mounts and are chowned back to the host user. See WORKDIR below.
"""

from __future__ import annotations

import os
from pathlib import Path

# libraries/azarch/paths.py -> repo root is three parents up.
REPODIR = Path(__file__).resolve().parents[2]
PKGDIR = Path(__file__).resolve().parent  # libraries/azarch (this package)

LIBDIR = REPODIR / "libraries"
DATADIR = LIBDIR / "data"
ASSETSDIR = REPODIR / "assets"

# Vendored ckbcomp Perl script. Arch does not package it (Debian/Manjaro-only),
# yet Calamares' keyboard-preview page shells out to `ckbcomp`, so we ship it in
# the repo and copy it to /usr/bin at build time. It lives beside this package
# rather than under assets/ because the user keeps it here.
CKBCOMP_SRC = PKGDIR / "ckbcomp"

CACHEDIR = REPODIR / "cache"
BUILDDIR = REPODIR / "output"
LOGDIR = REPODIR / "logs"


def in_docker() -> bool:
    return Path("/.dockerenv").exists()


# WORKDIR: the disposable mkarchiso profile + scratch tree (airootfs, the squashfs
# work/ dir, the transient sync DB). mkarchiso creates it as ROOT and mounts
# proc/sys/dev/run inside it, so its files are root-owned.
#
# In DOCKER it must live OUTSIDE the host bind mounts (cache/ output/ logs/). If it
# sat under cache/ (a bind mount), a hard `docker kill` -- which sends an
# untrappable SIGKILL, so the ownership-handback never runs -- would leave those
# root-owned files on the host, and `git clean -Xdf` / `rm -rf cache/` would then
# fail without sudo. Placing it at a container-internal path means the root-owned
# scratch dies WITH the container and never touches the host. Only the PERSISTENT
# stores (cache/pkgs, cache/pacman-pkg) and the finished ISO (output/) stay on the
# bind mounts, and those are chowned back to the host user.
#
# On a NATIVE run there are no bind mounts, so keeping it in-repo (cache/build) is
# fine and keeps everything discoverable under the repo.
if in_docker():
    WORKDIR = Path("/tmp/azarch-build")
else:
    WORKDIR = CACHEDIR / "build"

# Persistent package stores (the offline-rebuild cache).
PKG_REPO = CACHEDIR / "pkgs" / "repo"
PKG_DB = CACHEDIR / "pkgs" / "db"
PKG_SYNC_DB = PKG_DB / "sync"
LOCALREPO_INDEX = PKG_REPO / "pacstrap-azarch-repo.db"
LOCALREPO_INDEX_TAR = PKG_REPO / "pacstrap-azarch-repo.db.tar.gz"

# pacstrap's CacheDir, injected into the profile pacman.conf so the ~1200 live-ISO
# packages are reused across builds instead of re-downloaded.
PACSTRAP_CACHE = CACHEDIR / "pacman-pkg"

# Logs.
FULL_LOG = LOGDIR / "full.log"
STEPS_LOG = LOGDIR / "steps.log"

# Verbatim data files.
PACKAGES_FILE = DATADIR / "packages.x86_64"

# Inside the archiso profile tree, the airootfs root and the azarch payload dir
# baked into the live/installed system.
AIROOTFS = WORKDIR / "work" / "x86_64" / "airootfs"


def is_root() -> bool:
    return os.geteuid() == 0
