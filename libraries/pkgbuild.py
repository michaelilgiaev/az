"""Az'arch OWN package recipes, authored as configuration-as-Python.

Everything the ISO installs that is NOT in the official Arch repositories is
built from recipes WE write and maintain here -- never from the AUR or any
community source. Like the rest of azarch.config, each artifact (the PKGBUILDs
and their companion files) is held as a Python string and emitted into the build
tree by compiler.py; the emitted files are then consumed by `makepkg`, the official
Arch build tool, which produces *.pkg.tar.zst dropped into the ISO's offline
repo. No AUR helper (yay/paru/...) is used.

Two packages are built. Neither is in an official Arch repo, so both are built
in EVERY tier; --full-compile only changes the recipe librewolf uses:

  calamares   -- the graphical system installer (Manjaro-style). It USED to be an
                 official Arch package (extra/calamares), but Arch DROPPED it --
                 it is now AUR-only, and this project never builds from the AUR.
                 So it is compiled from OUR own recipe below in BOTH tiers: a
                 moderate C++/CMake build (minutes), with the release tarball
                 verified by the pinned sha256 (makepkg aborts on mismatch;
                 upstream ships no detached .sig for it). recipe_dirs() emits it
                 unconditionally now.

  librewolf   -- the privacy-hardened Firefox fork. A from-source Firefox build
                 takes 1.5-3+ hours and ~16 GB RAM, so there are TWO recipes:
                   * DEFAULT tier (`compile.sh`)          -> pkgbuild_librewolf()
                     repackages LibreWolf's official prebuilt tarball, verified by
                     BOTH a pinned sha256 AND its OpenPGP signature.
                   * FULL tier   (`compile.sh --full-compile`) -> pkgbuild_librewolf_src()
                     compiles LibreWolf from Firefox source via LibreWolf's bsys6
                     build harness.
                 recipe_dirs(full_compile) picks which pair of recipes to emit.

Pinned upstream facts (versions, URLs, checksums, signing key) live as the
constants below -- the single source of truth. All checksums were obtained by
downloading the real artifacts and hashing them, and are re-checked by makepkg
at build time (it aborts on mismatch). See update notes at the bottom.
"""

from __future__ import annotations

# The calamares package recipe (its pinned facts, the three Az'arch source patches,
# and the PKGBUILD text) lives in its own module -- the patch-authoring is large and
# self-contained. Re-exported here so the public surface stays flat: callers/tests use
# pkgbuild.CALAMARES_VERSION, pkgbuild.calamares_defaults_patch(),
# pkgbuild.pkgbuild_calamares(), etc. unchanged, and recipe_dirs() below assembles the
# calamares recipe dir from these names.
from pkgbuild_calamares import (  # noqa: F401  (re-exported for the public API)
    CALAMARES_DEFAULTS_PATCH_NAME,
    CALAMARES_FINISH_BUTTONS_PATCH_NAME,
    CALAMARES_REGION_KEYBOARD_PATCH_NAME,
    CALAMARES_SHA256,
    CALAMARES_VERSION,
    calamares_defaults_patch,
    calamares_finish_buttons_patch,
    calamares_region_keyboard_patch,
    pkgbuild_calamares,
)

# ---------------------------------------------------------------------------
# Pinned upstream facts (single source of truth). Calamares' pinned facts moved to
# pkgbuild_calamares.py (imported above) with the rest of its recipe.
# ---------------------------------------------------------------------------
# LibreWolf: upstream tag is "153.0.1-1"; pacman-legal pkgver is "153.0.1.1".
LIBREWOLF_VERSION = "153.0.1-1"
LIBREWOLF_PKGVER = "153.0.1.1"
# sha256 from upstream's published .sha256sum, re-verified by download + hash.
LIBREWOLF_SHA256 = "7b56e06071ece9e711a1c811e64129a3a14775c5fe00a4b777e5cbb0b087b5b5"
# LibreWolf release signing key -- the PRIMARY key fingerprint of
# "LibreWolf Maintainers <gpg@librewolf.net>". makepkg's validpgpkeys=() must list
# the PRIMARY key, NOT the signing subkey: the tarball's detached .sig is made by
# an ed25519 *subkey* (915585A1C36690B1 / 230FE8E0...C36690B1), and makepkg maps a
# signing subkey back to its primary and requires THAT primary to be in
# validpgpkeys. Pinning the subkey fingerprint here made makepkg abort with
# "invalid public key 662E3CDD...2B12EF16" (the primary it actually needs). Verify
# on update: `gpg --list-packets <tarball>.sig` shows the signing subkey keyid;
# `gpg --recv-keys <that keyid>` then shows the primary under `pub`.
LIBREWOLF_PGP_KEY = "662E3CDD6FE329002D0CA5BB40339DD82B12EF16"

# Thunar: pinned to the SAME version Arch's extra/ ships (so it is a drop-in replacement of the
# stock binary, no feature/behaviour drift) -- the only change is the Az'arch symlink-resolve
# patch below. sha256 of the official XFCE release tarball (archive.xfce.org), download + hash.
THUNAR_VERSION = "4.20.9"
THUNAR_SHA256 = "eb09869ce93b12ed285678967f55f243c833f2baf2fb10c9844ac7648d9270cb"
THUNAR_RESOLVE_SYMLINK_PATCH_NAME = "azarch-thunar-resolve-symlink.patch"


# ---------------------------------------------------------------------------
# librewolf -- shared companion files (used by BOTH tiers)
# ---------------------------------------------------------------------------
def librewolf_desktop() -> str:
    return """\
[Desktop Entry]
Name=LibreWolf
GenericName=Web Browser
Comment=Browse the web (Az'arch build, sessions/cookies persist)
Exec=/opt/librewolf/librewolf %u
Icon=librewolf
Terminal=false
Type=Application
MimeType=text/html;text/xml;application/xhtml+xml;application/xml;application/vnd.mozilla.xul+xml;application/rss+xml;application/rdf+xml;image/gif;image/jpeg;image/png;x-scheme-handler/http;x-scheme-handler/https;x-scheme-handler/ftp;x-scheme-handler/chrome;video/webm;application/x-xpinstall;
StartupNotify=true
StartupWMClass=librewolf
Categories=Network;WebBrowser;
Keywords=Internet;WWW;Browser;Web;Explorer;
Actions=new-window;new-private-window;

[Desktop Action new-window]
Name=Open a New Window
Exec=/opt/librewolf/librewolf --new-window %u

[Desktop Action new-private-window]
Name=Open a New Private Window
Exec=/opt/librewolf/librewolf --private-window %u
"""


# NOTE on the LibreWolf AutoConfig override (librewolf.overrides.cfg): it is NO LONGER
# a package companion file. LibreWolf's compiled AutoConfig loader reads it from the
# user's PROFILE dir (~/.config/librewolf/librewolf/), never from /opt, so shipping it
# in the package did nothing. It is delivered as a HOME file (mirrored into /etc/skel)
# by packages/librewolf.emit_plan(), which owns both its content AND its location. This
# recipe therefore neither generates nor installs it.


# ---------------------------------------------------------------------------
# librewolf -- DEFAULT tier (repackage the verified upstream tarball)
# ---------------------------------------------------------------------------
def pkgbuild_librewolf() -> str:
    dl = f"https://codeberg.org/api/packages/librewolf/generic/librewolf/{LIBREWOLF_VERSION}"
    tar = f"librewolf-{LIBREWOLF_VERSION}-linux-x86_64-package.tar.xz"
    return f"""\
# Maintainer: Az'arch <https://github.com/michaelilgiaev/azarch>
#
# =============================================================================
# Az'arch OWN PKGBUILD -- librewolf (DEFAULT tier: repackage verified upstream)
# =============================================================================
# NOT a community/AUR recipe. Written + maintained by the Az'arch project.
# Generated by packages.pkgbuild.
#
# A from-source LibreWolf/Firefox compile takes 1.5-3+ hours and needs ~16 GB
# RAM. To keep the DEFAULT `compile.sh` build fast, this recipe repackages
# LibreWolf's OFFICIAL prebuilt generic-Linux tarball, verified TWO ways:
#   1. pinned sha256sum (from upstream's published .sha256sum), and
#   2. detached OpenPGP signature (.sig) against the LibreWolf release key.
# For an all-self-compiled build use `compile.sh --full-compile`, which selects
# the source recipe instead.
#
# SOURCE (fully auditable):
#   Build system : https://codeberg.org/librewolf/bsys6
#   Website      : https://librewolf.net/
#   Tarball      : {dl}/{tar}
#   Signature    : {dl}/{tar}.sig   (key {LIBREWOLF_PGP_KEY})
#   Checksum src : {dl}/{tar}.sha256sum
#   Mirror note  : dl.librewolf.net is the upstream CDN; Codeberg's package API
#                  hosts the same files (same sha256) and is the active mirror.
#   License      : MPL-2.0
# The tarball is built by LibreWolf from Firefox source + LibreWolf's public
# patch set, so the lineage traces to scrutinizable source even in this path.
#
# AZ'ARCH CUSTOMISATION: LibreWolf clears cookies + history on shutdown by
# default; Az'arch relaxes that (sessions/cookies persist) + hides the bookmarks
# toolbar via LibreWolf's supported AutoConfig override. That override is delivered
# as a HOME file at the profile path LibreWolf actually reads (NOT packaged here --
# see packages/librewolf); this recipe is otherwise stock LibreWolf.
# =============================================================================

pkgname=librewolf
pkgver={LIBREWOLF_PKGVER}
_lwver={LIBREWOLF_VERSION}
pkgrel=1
pkgdesc="Privacy-hardened Firefox fork, session/cookie persistence (Az'arch build)"
arch=('x86_64')
url="https://librewolf.net/"
license=('MPL-2.0')
depends=('gtk3' 'libxt' 'mime-types' 'dbus' 'ffmpeg' 'nss' 'ttf-font'
         'libpulse' 'libnotify' 'pciutils')
options=('!strip')

_dl="{dl}"
source=(
  "librewolf-${{_lwver}}-linux-x86_64-package.tar.xz::${{_dl}}/librewolf-${{_lwver}}-linux-x86_64-package.tar.xz"
  "librewolf-${{_lwver}}-linux-x86_64-package.tar.xz.sig::${{_dl}}/librewolf-${{_lwver}}-linux-x86_64-package.tar.xz.sig"
  'librewolf.desktop'
)
# Tarball: pinned sha256 (+ GPG). .sig: GPG-checked (SKIP sha). Local .desktop:
# shipped in-repo, reviewed in packages.pkgbuild (SKIP sha). The AutoConfig override
# is NOT packaged (LibreWolf reads it from the profile dir, not /opt) -- it ships as a
# home file via packages/librewolf.emit_plan().
sha256sums=('{LIBREWOLF_SHA256}' 'SKIP' 'SKIP')
validpgpkeys=('{LIBREWOLF_PGP_KEY}')

package() {{
  # Tarball extracts to a top-level librewolf/ dir (Firefox-style layout).
  install -d "$pkgdir/opt"
  cp -a "$srcdir/librewolf" "$pkgdir/opt/librewolf"

  install -d "$pkgdir/usr/bin"
  ln -s /opt/librewolf/librewolf "$pkgdir/usr/bin/librewolf"

  install -Dm644 "$srcdir/librewolf.desktop" \\
    "$pkgdir/usr/share/applications/librewolf.desktop"

  local icon="$srcdir/librewolf/browser/chrome/icons/default/default128.png"
  [[ -f "$icon" ]] && install -Dm644 "$icon" \\
    "$pkgdir/usr/share/icons/hicolor/128x128/apps/librewolf.png"

  # NOTE: the Az'arch persistence/bookmarks override is NOT installed here. LibreWolf's
  # AutoConfig loader reads librewolf.overrides.cfg from the user's PROFILE dir
  # (~/.config/librewolf/librewolf/), never from /opt, so it is delivered as a home file
  # by packages/librewolf.emit_plan() (compiler.py) instead.
}}
"""


# ---------------------------------------------------------------------------
# librewolf -- FULL tier (compile from Firefox source via bsys6)
# ---------------------------------------------------------------------------
def pkgbuild_librewolf_src() -> str:
    return f"""\
# Maintainer: Az'arch <https://github.com/michaelilgiaev/azarch>
#
# =============================================================================
# Az'arch OWN PKGBUILD -- librewolf (FULL-COMPILE tier: build from source)
# =============================================================================
# NOT a community/AUR recipe. Written + maintained by the Az'arch project.
# Generated by packages.pkgbuild. Selected ONLY by `compile.sh --full-compile`.
#
# ///////////////////////////////////////////////////////////////////////////
#  HEAVY BUILD WARNING: a from-source LibreWolf/Firefox compile takes 1.5-3+
#  hours on a strong multi-core machine and needs ~16 GB RAM + tens of GB disk.
#  The default `compile.sh` (repackage tier) exists to avoid this.
# ///////////////////////////////////////////////////////////////////////////
#
# SOURCE (fully auditable):
#   Build system : https://codeberg.org/librewolf/bsys6   (tag {LIBREWOLF_VERSION})
#   which fetches Mozilla Firefox source (release 153.0) + LibreWolf's public
#   patch set/settings, all in the codeberg repos.
#   License      : MPL-2.0
#
# INTEGRITY: bsys6 verifies the Firefox source it downloads against Mozilla's
# published checksums as part of its own build. We pin bsys6 by git tag.
# =============================================================================

pkgname=librewolf
pkgver={LIBREWOLF_PKGVER}
_lwver={LIBREWOLF_VERSION}
pkgrel=1
pkgdesc="Privacy-hardened Firefox fork built FROM SOURCE, persistence (Az'arch build)"
arch=('x86_64')
url="https://librewolf.net/"
license=('MPL-2.0')
depends=('gtk3' 'libxt' 'mime-types' 'dbus' 'ffmpeg' 'nss' 'ttf-font'
         'libpulse' 'libnotify' 'pciutils')
# The Firefox build toolchain -- the bulk of what makes the full compile heavy.
makedepends=('rust' 'clang' 'llvm' 'lld' 'nodejs' 'cbindgen' 'nasm' 'yasm'
             'python' 'python-setuptools' 'unzip' 'zip' 'gawk' 'perl' 'wget'
             'mercurial' 'git' 'make' 'pkgconf' 'gtk3' 'nss' 'gcc' 'which'
             'mesa' 'libpulse' 'dbus-glib' 'alsa-lib')
options=('!strip' '!lto' '!debug')

source=(
  "librewolf-bsys6::git+https://codeberg.org/librewolf/bsys6.git#tag=${{_lwver}}"
  'librewolf.desktop'
)
# The AutoConfig override is NOT packaged (LibreWolf reads it from the profile dir, not
# /opt) -- it ships as a home file via packages/librewolf.emit_plan().
sha256sums=('SKIP' 'SKIP')

build() {{
  cd "$srcdir/librewolf-bsys6"
  # bsys6's documented top-level targets: fetch Firefox source + LibreWolf
  # patches/settings, build, then produce the generic-linux package tree.
  #
  # `make fetch` is the ONLY network step. On an OFFLINE --full-compile rerun the
  # Az'arch build sets AZARCH_OFFLINE=1 and passes makepkg --noextract, so this
  # same bsys6 tree (already populated by the prior online run's `make fetch`) is
  # reused as-is: we skip the fetch and go straight to build. If the tree were
  # gone (a wiped cache) `make build` fails loudly here -- we never silently go
  # back online. On the normal online run AZARCH_OFFLINE is unset and `make fetch`
  # populates the tree as before.
  if [[ -z "${{AZARCH_OFFLINE:-}}" ]]; then make fetch; fi
  # -j caps parallel compile jobs so the Firefox build (bsys6 -> mach) does not
  # pin every core for hours. AZARCH_JOBS is exported by makepkg (= cores -
  # reserved); it defaults to 1 if unset so an isolated recipe run stays safe.
  make build -j"${{AZARCH_JOBS:-1}}"
  make package
}}

package() {{
  cd "$srcdir/librewolf-bsys6"
  # Locate the produced package tree / tarball (bsys6 emits under its own dir).
  local tree
  tree="$(find . -maxdepth 4 -type d -name librewolf -path '*obj*' 2>/dev/null | head -1)"
  if [[ -z "$tree" ]]; then
    local tarball
    tarball="$(find . -maxdepth 3 -name 'librewolf-*.tar.xz' 2>/dev/null | head -1)"
    [[ -n "$tarball" ]] || {{ echo "librewolf-src: could not locate build output"; return 1; }}
    bsdtar -xf "$tarball" -C "$srcdir"
    tree="$srcdir/librewolf"
  fi

  install -d "$pkgdir/opt"
  cp -a "$tree" "$pkgdir/opt/librewolf"

  install -d "$pkgdir/usr/bin"
  ln -s /opt/librewolf/librewolf "$pkgdir/usr/bin/librewolf"

  install -Dm644 "$srcdir/librewolf.desktop" \\
    "$pkgdir/usr/share/applications/librewolf.desktop"

  local icon="$pkgdir/opt/librewolf/browser/chrome/icons/default/default128.png"
  [[ -f "$icon" ]] && install -Dm644 "$icon" \\
    "$pkgdir/usr/share/icons/hicolor/128x128/apps/librewolf.png"

  # NOTE: the Az'arch override is NOT installed here -- LibreWolf reads it from the
  # profile dir, not /opt, so packages/librewolf.emit_plan() (compiler.py) delivers it as
  # a home file. See packages/librewolf.
}}
"""


# ---------------------------------------------------------------------------
# thunar -- source patch: show the fully-resolved (symlink-dereferenced) path
# ---------------------------------------------------------------------------
# The user wants Thunar's location bar / window title to ALWAYS show the real
# filesystem path, even when a directory is reached through a symlink (e.g. the
# convenience link ~/Trash -> ~/.local/share/Trash/files created by
# packages/thunar/home_directory): "I WANT FULL ACTUAL PATHS, /home/main/.local/
# share/Trash/files/". The sidebar bookmarks already point at resolved targets
# (packages/thunar/sidebar), so the shortcut route is correct -- but
# navigating the symlink DIRECTLY (double-clicking it in the folder view / typing
# its path) kept the symlink path.
#
# WHY A SOURCE PATCH. Upstream added the `misc-resolve-links` preference that does
# exactly this in Thunar 4.21.6; it is ABSENT from the 4.20.x series Arch ships
# (verified: `strings /usr/bin/thunar` on 4.20.9 has no misc-resolve-links, and the
# 4.20 source prints g_file_get_path() of the as-requested GFile with no
# canonicalisation). There is NO config lever on 4.20, so the only way to get the
# behaviour on the shipped version is to patch it in. We pin the SAME version Arch
# ships (4.20.9) so this is a drop-in binary replacement whose ONLY change is this
# patch. packages/thunar/settings still ships misc-resolve-links=true too, so
# the day Arch moves to >=4.21.6 the upstream pref takes over and this patch (which
# would then fail to apply and abort the build, loudly) is removed.
#
# THE PATCH. thunar_window_set_current_directory() is the single chokepoint every
# directory change flows through. When the requested directory is a symlink, we
# realpath() it and re-enter with a ThunarFile for the canonical target, so the
# path bar, window title and history all show the real path. Guarded to symlinks
# only; no-ops if resolution fails. VERIFIED: the patched 4.20.9 tree builds clean
# (autotools) and the binary links realpath.
def thunar_resolve_symlink_patch() -> str:
    r"""Unified diff (-p1) applied to the extracted thunar-4.20.9 source in the recipe's
    prepare(): make thunar_window_set_current_directory() canonicalise a symlinked directory
    (realpath + re-enter) so the location bar / title show the real path. See the block comment
    above for why this lives in a source patch (4.20 has no misc-resolve-links pref).

    Assembled line-by-line (not one triple-quoted literal) for the SAME reason
    calamares_defaults_patch() is: a unified diff's blank CONTEXT lines are a single leading
    space, which a triple-quoted literal makes invisible and an editor trivially strips --
    silently breaking `patch`. Every context line's leading space is explicit here. The hunk
    headers were generated by `diff -u` against the pinned 4.20.9 tarball and verified to apply
    with `patch -p1` (and the result compiles + links). Regenerate the same way on a version
    bump; a drift makes `patch` fail LOUDLY (build aborts) rather than dropping the fix."""
    lines = [
        "--- a/thunar/thunar-window.c",
        "+++ b/thunar/thunar-window.c",
        "@@ -21,6 +21,8 @@",
        " ",
        " #ifdef HAVE_CONFIG_H",
        ' #include "config.h"',
        "+#include <stdlib.h> /* Az'arch realpath */",
        "+#include <string.h> /* Az'arch strcmp */",
        " #endif",
        " ",
        " #ifdef HAVE_UNISTD_H",
        "@@ -5529,6 +5531,39 @@",
        "   _thunar_return_if_fail (THUNAR_IS_WINDOW (window));",
        "   _thunar_return_if_fail (current_directory == NULL || THUNAR_IS_FILE (current_directory));",
        " ",
        "+  /* Az'arch: ALWAYS show the FULLY-RESOLVED (symlink-dereferenced) path. Thunar 4.20 has no",
        "+   * misc-resolve-links pref (that arrived in 4.21.6), so navigating a symlink such as",
        "+   * ~/Trash -> ~/.local/share/Trash/files would otherwise keep the symlink path in the",
        "+   * location bar and window title. When the requested directory is a symlink, canonicalise it",
        "+   * with realpath() and re-enter with a ThunarFile for the real target, so every surface (path",
        "+   * bar, title, history) shows the actual path -- matching what the sidebar bookmarks already",
        "+   * do. Guarded to symlinks only, and no-ops if resolution fails or already matches. */",
        "+  if (current_directory != NULL && thunar_file_is_symlink (current_directory))",
        "+    {",
        "+      GFile *az_gfile = thunar_file_get_file (current_directory);",
        "+      gchar *az_path  = (az_gfile != NULL) ? g_file_get_path (az_gfile) : NULL;",
        "+      if (az_path != NULL)",
        "+        {",
        "+          char *az_real = realpath (az_path, NULL);",
        "+          if (az_real != NULL && strcmp (az_real, az_path) != 0)",
        "+            {",
        "+              GFile      *az_canon = g_file_new_for_path (az_real);",
        "+              ThunarFile *az_rfile = thunar_file_get (az_canon, NULL);",
        "+              g_object_unref (az_canon);",
        "+              if (az_rfile != NULL)",
        "+                {",
        "+                  thunar_window_set_current_directory (window, az_rfile);",
        "+                  g_object_unref (az_rfile);",
        "+                  free (az_real);",
        "+                  g_free (az_path);",
        "+                  return;",
        "+                }",
        "+            }",
        "+          free (az_real);",
        "+          g_free (az_path);",
        "+        }",
        "+    }",
        "+",
        "   /* check if we already display the requested directory */",
        "   if (G_UNLIKELY (window->current_directory == current_directory))",
        "     return;",
    ]
    return "\n".join(lines) + "\n"


def pkgbuild_thunar() -> str:
    return f"""\
# Maintainer: Az'arch <https://github.com/michaelilgiaev/azarch>
#
# =============================================================================
# Az'arch OWN PKGBUILD -- thunar  (generated by packages.pkgbuild)
# =============================================================================
# NOT a community/AUR recipe. Written + maintained by the Az'arch project.
#
# Thunar is the Xfce file manager. Az'arch ships it as the default file manager
# and needs ONE behaviour change the shipped 4.20 series cannot be configured to
# do: always show the fully-resolved (symlink-dereferenced) path in the location
# bar/title (the misc-resolve-links pref only exists in Thunar >= 4.21.6). This
# recipe rebuilds the SAME version Arch's extra/ ships ({THUNAR_VERSION}) -- a
# drop-in replacement -- with a single source patch that adds that resolution.
#
# SOURCE (fully auditable):
#   Project : https://gitlab.xfce.org/xfce/thunar
#   Tarball : https://archive.xfce.org/src/xfce/thunar/{THUNAR_VERSION[:THUNAR_VERSION.rindex('.')]}/thunar-{THUNAR_VERSION}.tar.bz2
#   License : GPL-2.0-or-later
#
# INTEGRITY: pinned sha256 below (download + sha256sum). makepkg aborts on
# mismatch. The patch is shipped in-repo (SKIP -- a local file, reviewed in
# packages.pkgbuild).
#
# FROM SOURCE IN EVERY TIER: a moderate autotools C build (a couple of minutes).
# Built and dropped into the offline repo so pacstrap installs OUR thunar instead
# of extra/'s. The pkgver MATCHES extra/ so pacman treats it as the same package
# (our repo is ordered first, so ours wins).
# =============================================================================

pkgname=thunar
pkgver={THUNAR_VERSION}
# pkgrel=2 (extra/thunar is -1): our repo is appended AFTER [extra] on an ONLINE build
# (pacman.append_local_repo lists the local repo last), so pacstrap would pick extra/'s
# UNPATCHED thunar for the same version. A higher pkgrel makes OURS strictly newer, so pacman
# selects it regardless of repo order (and on an OFFLINE build [extra] is dropped, so ours wins
# anyway). If extra ever ships thunar-4.20.9-2+ or a newer pkgver, bump THUNAR_VERSION/this rel
# in lock-step (the pinned sha256 already forces a conscious version update).
pkgrel=2
pkgdesc="Modern file manager for Xfce (Az'arch build: resolves symlink paths)"
arch=('x86_64')
url="https://gitlab.xfce.org/xfce/thunar"
license=('GPL-2.0-or-later')
groups=('xfce4')

# Runtime deps mirror extra/thunar's Depends On (pacman -Si thunar), so the built
# package needs exactly what the stock one does.
depends=(
  'desktop-file-utils' 'libexif' 'hicolor-icon-theme' 'libnotify'
  'pcre2' 'libgudev' 'exo' 'libxfce4util' 'libxfce4ui'
)
# Build deps: the -dev headers/tools the autotools build needs. gettext/intltool
# for the translations, xfce4-dev-tools for the xdt macros (the release tarball
# already carries a generated ./configure, but the tools are cheap insurance).
makedepends=('gtk3' 'gettext' 'intltool' 'xfce4-dev-tools' 'gobject-introspection')
optdepends=(
  'gvfs: trash support, mounting with GIO'
  'tumbler: thumbnails'
  'thunar-volman: automanagement of removable devices'
)
options=('!emptydirs')

source=(
  "https://archive.xfce.org/src/xfce/thunar/{THUNAR_VERSION[:THUNAR_VERSION.rindex('.')]}/thunar-${{pkgver}}.tar.bz2"
  '{THUNAR_RESOLVE_SYMLINK_PATCH_NAME}'
)
sha256sums=('{THUNAR_SHA256}' 'SKIP')

prepare() {{
  cd "thunar-${{pkgver}}"
  # Az'arch: always show the resolved (symlink-dereferenced) path in the location
  # bar/title -- the 4.20 series has no misc-resolve-links pref (added upstream in
  # 4.21.6), so it is patched in. -p1 from the source root; the pinned tarball
  # guarantees the context matches, so a failure here (e.g. after a version bump)
  # aborts the build LOUDLY instead of silently dropping the fix.
  patch -p1 < "$srcdir/{THUNAR_RESOLVE_SYMLINK_PATCH_NAME}"
}}

build() {{
  cd "thunar-${{pkgver}}"
  # Match a stock Thunar build. gtk-doc/apidocs off (extra deps, pointless on the
  # ISO). The tarball ships a generated ./configure, so no autogen is needed.
  ./configure \\
    --prefix=/usr \\
    --sysconfdir=/etc \\
    --libexecdir=/usr/lib \\
    --localstatedir=/var \\
    --disable-static \\
    --disable-gtk-doc \\
    --disable-gtk-doc-html \\
    --disable-silent-rules
  # -j caps parallel compile jobs (AZARCH_JOBS is exported by makepkg, = cores -
  # reserved, default 1) so the build does not pin the whole machine.
  make -j"${{AZARCH_JOBS:-1}}"
}}

package() {{
  cd "thunar-${{pkgver}}"
  make DESTDIR="$pkgdir" install
}}
"""


# ---------------------------------------------------------------------------
# Recipe emission plan: (dirname, {filename: content}) tuples.
# compiler.py iterates this to write each recipe dir into the build tree, then the
# makepkg stage builds each and drops the result into the offline repo.
# ---------------------------------------------------------------------------
def recipe_dirs(full_compile: bool) -> list[tuple[str, dict[str, str]]]:
    """Which recipes to emit. BOTH calamares and librewolf are built in EVERY
    tier now -- neither is in an official Arch repo (librewolf never was;
    calamares was dropped from extra/ and is AUR-only). --full-compile only
    changes the RECIPE, not the set:

      calamares : always compiled from source (pinned-sha256 Codeberg tarball,
                  a moderate C++/CMake build of minutes). There is no prebuilt
                  Arch binary to fall back to anymore, so both tiers use the
                  same source recipe.
      librewolf : default = repackage the verified upstream binary tarball;
                  --full-compile = compile from Firefox source (1.5-3+ hours)."""
    # The .desktop is the ONLY companion file the package ships now. The AutoConfig
    # override (librewolf.overrides.cfg) is NOT packaged: LibreWolf reads it from the
    # user's PROFILE dir, not /opt, so it is delivered as a home file by
    # packages/librewolf.emit_plan() (compiler.py) instead -- shipping it under /opt did
    # nothing. See packages/librewolf.
    lw_common = {
        "librewolf.desktop": librewolf_desktop(),
    }
    calamares = ("calamares", {
        "PKGBUILD": pkgbuild_calamares(),
        CALAMARES_DEFAULTS_PATCH_NAME: calamares_defaults_patch(),
        CALAMARES_REGION_KEYBOARD_PATCH_NAME: calamares_region_keyboard_patch(),
        CALAMARES_FINISH_BUTTONS_PATCH_NAME: calamares_finish_buttons_patch(),
    })
    # thunar: rebuilt (same version as extra/) with the symlink-resolve patch, in EVERY tier --
    # the patched location-bar behaviour is not optional. Built from source like calamares.
    thunar = ("thunar", {
        "PKGBUILD": pkgbuild_thunar(),
        THUNAR_RESOLVE_SYMLINK_PATCH_NAME: thunar_resolve_symlink_patch(),
    })
    if full_compile:
        librewolf = ("librewolf", {"PKGBUILD": pkgbuild_librewolf_src(), **lw_common})
        return [calamares, thunar, librewolf]
    librewolf = ("librewolf", {"PKGBUILD": pkgbuild_librewolf(), **lw_common})
    # Default tier: repackage librewolf, but calamares + thunar are still built from source.
    return [calamares, thunar, librewolf]


# ---------------------------------------------------------------------------
# Updating versions:
#   1. Bump CALAMARES_VERSION / LIBREWOLF_VERSION / LIBREWOLF_PKGVER above.
#      LIBREWOLF_VERSION is the upstream tag (e.g. "153.0.1-1");
#      LIBREWOLF_PKGVER is the pacman-legal form (dots only, e.g. "153.0.1.1").
#   2. Refresh the pinned sha256 from Codeberg's package API:
#      https://codeberg.org/api/packages/librewolf/generic/librewolf/<tag>/
#        librewolf-<tag>-linux-x86_64-package.tar.xz.sha256sum
#   3. If LibreWolf rotates its signing key, update LIBREWOLF_PGP_KEY.
#   4. Rebuild with FORCE_ONLINE=1 so the new sources are fetched.
# ---------------------------------------------------------------------------
