"""Filesystem layout for the build.

Mirrors the directory scheme the old compile.sh used, so the Docker bind mounts
(cache/ output/ logs/) and the on-disk artifacts land in exactly the same places:

  REPODIR/                 repo root (where compile.sh lives)
    libraries/             the COMPILER's own modules (flat) + build payload
    libraries/packages/    Az'arch's OWN packages (things WE build/ship): the pacman
                           manifest (packages.x86_64), application_menu/, pkgbuild.py,
                           azarch/, passwords/, timedate/, and the critically-modified
                           calamares/ -- all pure stdlib (no requirements.txt)
    libraries/modifications/  ONLY upstream software we modify/configure (ckbcomp,
                           fastfetch, librewolf, openbox, the per-app tweaks)
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

# libraries/paths.py -> repo root is two parents up (libraries/ then the repo root).
REPODIR = Path(__file__).resolve().parents[1]
LIBDIR = REPODIR / "libraries"
# The compiler's own modules now live flat in libraries/ (there is no separate
# `azarch` package anymore), so the compiler package dir IS libraries/ itself.
PKGDIR = LIBDIR
# Az'arch's OWN packages (the things WE build/ship, baked into the ISO): the package
# manifest (packages.x86_64), the application-menu source tree + its build wiring
# (application_menu/), our own package recipes (pkgbuild.py), and the `azarch` guest command line interface
# (the azarch/ package). Our packages are pure Python standard library, so there is NO shared
# requirements.txt here (the only one in the repo is the repo-root requirements.txt the
# compiler itself uses for its test/dev deps). Formerly libraries/data/; consolidated here.
PACKAGESDIR = LIBDIR / "packages"
# Existing UPSTREAM software that is NOT ours -- we merely modify/configure/patch it
# to fit Az'arch (ckbcomp, fastfetch, librewolf, openbox, the per-app tweaks). Anything WE
# author outright is NOT here: it is either a compiler module (flat in libraries/) or one of
# our own packages (libraries/packages/). (The critically-modified calamares install config
# is OUR package -- packages/calamares/ -- since we compile it from source and ship it.)
MODIFICATIONSDIR = LIBDIR / "modifications"
ASSETSDIR = REPODIR / "assets"

# Vendored ckbcomp: a Python 3 port of the upstream Perl ckbcomp (byte-identical
# output, no Perl in the tree). Arch does not package it (Debian/Manjaro-only), yet
# Calamares' keyboard-preview page shells out to `ckbcomp`, so we ship it in the repo
# and copy it to /usr/bin at build time. It is upstream software modified to fit the
# distribution, so it lives under libraries/modifications/ as its own directory module
# (libraries/modifications/ckbcomp/), whose ckbcomp.py holds the vendored script. It is
# emitted to /usr/bin/ckbcomp (no .py suffix there -- it is an executable script the
# keyboard page runs by name).
CKBCOMP_SRC = MODIFICATIONSDIR / "ckbcomp" / "ckbcomp.py"

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
PACKAGES_FILE = PACKAGESDIR / "packages.x86_64"
# The Az'arch application-menu package (C / GTK3): the menu source files (menu.c +
# siblings, theme.h, Makefile) live DIRECTLY here alongside application_menu.py -- the
# build wiring that COMPILES them into the daemon binary and installs it, ships the
# pure-Python launcher (launcher.py), and generates the .desktop entry. The whole menu
# is OURS, so it is a package here, not a patch.
APPLICATION_MENU_DIR = PACKAGESDIR / "application_menu"
# The Az'arch timedate package (Flask Time + Calendar home page): the app sources
# (app.py + page.py) live directly here alongside timedate.py, the build wiring that
# copies them into the airootfs, installs the launcher, and ships the systemd service.
# It is OUR package (a website we author), so it lives under libraries/packages/, not
# modifications/. Served at localhost:49154; LibreWolf's default home/new-tab page.
TIMEDATE_DIR = PACKAGESDIR / "timedate"
# The Az'arch passwords package (encrypted GPG/AES256 terminal password manager): ONE flat
# directory holding the entry script (passwords.py), the one-time setup script, every working
# module (config/cryptography/model/terminal_user_interface/...), and packaging.py (the build
# wiring that copies them into the airootfs and installs the /usr/local/bin/passwords
# launcher). A pure-Python app we author, so it lives under libraries/packages/ like timedate.
# The `passwords` command unlocks a store at ~/Vault/passwords.txt.gpg (see
# packages/passwords/config.py).
PASSWORDS_DIR = PACKAGESDIR / "passwords"
# The `azarch` guest command line interface is a Python PACKAGE now (libraries/packages/azarch/): it grew a
# `theme` subcommand (and more to come), so the single module was split into small modules
# (common, country_table, resolver, theme, sshd, command_line_interface). The single /usr/local/bin/azarch
# script that ships to the guest is reassembled from those modules by the package's
# bundle.bundle_source(); the compiler then injects the country->locale table from
# packages/calamares/locale.py between the AZARCH_CC markers (which now live in
# country_table.py). See modifications/openbox openbox.azarch_command_line_interface().
#
# This dir ALSO holds the bare-`azarch` TERMINAL UI's C sources (main.c/render.c/model.c/
# preview.c, terminal_user_interface.h + siblings, Makefile) -- there is only ONE program, `azarch`, and the UI
# is C for speed, so it lives next to the Python command line interface it drives rather than in a separate
# package. packages/azarch/terminal_user_interface_build.py is the build wiring that compiles them into the
# azarch binary; bare `azarch` execs it (see packages/azarch/terminal_user_interface.py). terminal_user_interface_build's
# _csrc_files() picks up only the C inputs, never the .py modules, so the two coexist here.
AZARCH_COMMAND_LINE_INTERFACE_DIR = PACKAGESDIR / "azarch"
# The module whose source carries the AZARCH_CC_TABLE_START/END markers (the compiler
# regenerates the COUNTRY_TABLE literal between them from the single source of truth).
AZARCH_COMMAND_LINE_INTERFACE_TABLE_MODULE = AZARCH_COMMAND_LINE_INTERFACE_DIR / "country_table.py"

# Inside the archiso profile tree, the airootfs root and the azarch payload dir
# baked into the live/installed system.
AIROOTFS = WORKDIR / "work" / "x86_64" / "airootfs"


def is_root() -> bool:
    return os.geteuid() == 0
